import asyncio
from openai import AsyncOpenAI


class PocketPal:
    MODEL = "local_model"

    def get_client(self) -> AsyncOpenAI | None:
        try:
            return AsyncOpenAI(
                base_url="http://192.168.29.63:8080/v1",
                api_key="not-needed",
            )
        except Exception as e:
            print(f"Error: [{e}]")
            return None

    async def chat(self, msg: str):
        client = self.get_client()
        if client is not None:
            async with client:
                # 1. Add stream=True
                stream = await client.chat.completions.create(
                    model=self.MODEL,
                    messages=[{"role": "user", "content": msg}],
                    reasoning_effort="medium",
                    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
                    stream=True,
                )

                is_thinking = False
                is_answering = False

                # 2. Loop through incoming chunks asynchronously
                async for chunk in stream:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # Stream reasoning tokens (if supported by your local model)
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        if not is_thinking:
                            print("--- THINKING ---")
                            is_thinking = True
                        print(reasoning, end="", flush=True)

                    if delta.content:
                        if not is_answering:
                            if is_thinking:
                                print("\n")  # Separate thinking from final answer
                            print("--- ANSWER ---")
                            is_answering = True
                        print(delta.content, end="", flush=True)

                print()


if __name__ == "__main__":
    asyncio.run(PocketPal().chat(msg="How many r's are in strawberry?"))
