import asyncio
import json
import re
from openai import AsyncOpenAI


class PocketPal:
    MODEL = "local_model"
    BASE_URL = "http://192.168.29.63:8080/v1"

    # The model sees these descriptions in the system prompt.
    TOOL_SPECS = {
        "read_file": {
            "description": "Read the full contents of a file.",
            "parameters": {"path": "string (file path)"},
        },
        "create_file": {
            "description": "Create a NEW file with the given content. "
                           "Fails if the file already exists.",
            "parameters": {"path": "string", "content": "string"},
        },
        "write_file": {
            "description": "Write content to a file (create or overwrite).",
            "parameters": {"path": "string", "content": "string"},
        },
    }

    def __init__(self):
        self.client = AsyncOpenAI(base_url=self.BASE_URL, api_key="not-needed")
        self.system_prompt = self._build_system_prompt()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.close()

    # ---------- build the system prompt that teaches the tool format ----------
    def _build_system_prompt(self) -> str:
        lines = [
            "You are a helpful assistant with access to the following tools.",
            "When you need a tool, reply with ONLY a single JSON object inside",
            "<tool_call> and </tool_call> tags.",
            "The JSON MUST have exactly two keys: \"name\" and \"arguments\".",
            "ALL tool parameters MUST be nested under \"arguments\".",
            "",
            "CORRECT:",
            '<tool_call>{"name": "create_file", "arguments": {"path": "poem.txt", "content": "..."}}</tool_call>',
            "",
            "WRONG (do NOT do this — arguments must be nested):",
            '<tool_call>{"name": "create_file", "path": "poem.txt", "content": "..."}</tool_call>',
            "",
            "Do NOT wrap the JSON in markdown fences. Do NOT add extra text.",
            "After the tool result comes back, continue the conversation.",
            "",
            "Available tools:",
        ]
        for name, spec in self.TOOL_SPECS.items():
            params = ", ".join(f"{k}: {v}" for k, v in spec["parameters"].items())
            lines.append(f"- {name}({params}): {spec['description']}")
        return "\n".join(lines)

    # ---------- actual tools ----------
    def read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"ERROR reading {path}: {e}"

    def write_file(self, path: str, content: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"OK: wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"ERROR writing {path}: {e}"

    def create_file(self, path: str, content: str) -> str:
        import os
        if os.path.exists(path):
            return f"ERROR: {path} already exists. Use write_file to overwrite."
        try:
            with open(path, "x", encoding="utf-8") as f:  # 'x' = exclusive create
                f.write(content)
            return f"OK: created {path} ({len(content)} chars)"
        except FileExistsError:
            return f"ERROR: {path} already exists. Use write_file to overwrite."
        except Exception as e:
            return f"ERROR creating {path}: {e}"
        
    # ---------- stream one assistant turn ----------
    async def _stream_turn(self, messages):
        stream = await self.client.chat.completions.create(
            model=self.MODEL,
            messages=messages,
            stream=True,
        )
        parts = []
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                print(delta.content, end="", flush=True)
                parts.append(delta.content)
        print()
        return "".join(parts)

    # ---------- parse a <tool_call> block out of the assistant text ----------
    @staticmethod
    def _extract_tool_call(text: str):
        match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
        if not match:
            return None
        raw = match.group(1).strip()

        # Strip markdown fences if the model added them.
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        obj = None
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Small models often emit literal newlines/tabs inside strings,
            # which is invalid JSON. Repair and retry.
            try:
                repaired = (raw
                            .replace("\n", "\\n")
                            .replace("\r", "\\r")
                            .replace("\t", "\\t"))
                obj = json.loads(repaired)
            except json.JSONDecodeError:
                return None

        if not isinstance(obj, dict):
            return None
        name = obj.get("name")
        if not isinstance(name, str):
            return None

        # Preferred: {"name": ..., "arguments": {...}}
        args = obj.get("arguments")
        if not isinstance(args, dict) or not args:
            # Fallback: model flattened args onto the top level.
            args = {k: v for k, v in obj.items() if k not in ("name", "arguments")}

        return name, args

    # ---------- the agent loop ----------
    async def chat(self, msg: str, max_iterations: int = 10) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": msg},
        ]

        for _ in range(max_iterations):
            assistant_text = await self._stream_turn(messages)
            messages.append({"role": "assistant", "content": assistant_text})

            tool = self._extract_tool_call(assistant_text)
            if tool is None:
                # No tool call → this is the final answer.
                return assistant_text

            name, args = tool
            print(f"[tool call] {name}({args})")   # debug — remove once it works

            try:
                if name == "read_file":
                    result = self.read_file(**args)
                elif name == "create_file":
                    result = self.create_file(**args)
                elif name == "write_file":
                    result = self.write_file(**args)
                else:
                    result = f"ERROR: unknown tool {name!r}"
            except TypeError as e:
                expected = list(self.TOOL_SPECS.get(name, {}).get("parameters", {}))
                result = (
                    f"ERROR: bad arguments for {name}: {e}. "
                    f"Required keys: {expected}. "
                    f'Retry with: <tool_call>{{"name": "{name}", "arguments": {{...}}}}</tool_call>'
                )
            preview = result if len(result) <= 200 else result[:200] + "…"
            print(f"[tool] {name}({args})\n[result] {preview}\n")

            # Feed the result back so the model can continue.
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool `{name}` returned:\n{result}",
                }
            )

        return "Reached max_iterations without a final answer."


async def main():
    async with PocketPal() as pal:
        await pal.chat(
            "can you create a file named 'poem.txt' and write a short poem in it?"
        )


if __name__ == "__main__":
    asyncio.run(main())