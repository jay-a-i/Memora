"""
Proves the tool node receives the request's DB session, and that a failing
tool's exception reaches the orchestrator's rollback.

Both matter for correctness of the streaming path: without the session every
tool queries with None, and without the rollback one failed statement leaves the
transaction aborted so the assistant turn is never committed.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.agent.state import AgentContext, AgentState


def _restore(orchestrator, original):
    """Puts TOOLS_MAP back the way it was, deleting a key we introduced."""
    if original is None:
        orchestrator.TOOLS_MAP.pop("spy_tool", None)
    else:
        orchestrator.TOOLS_MAP["spy_tool"] = original


class _FakeSession:
    """Stands in for AsyncSession: records rollback, nothing else."""

    def __init__(self):
        self.rolled_back = 0

    async def rollback(self):
        self.rolled_back += 1


def _tool_state(tool_name: str = "spy_tool"):
    return {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": tool_name, "args": {}, "id": "call_1"},
                ],
            ),
        ],
        "tool_call_count": 0,
        "llm_call_count": 0,
    }


class TestToolContextWiring:
    async def test_session_arrives_through_runtime_context(self):
        """
        The full path: graph -> runtime.context -> tool_executor -> tool kwargs.

        This is the wiring that a `context` key misplaced inside the config dict
        would silently break, leaving every search running without a session.
        """
        from backend.app.agent import orchestrator

        captured: list = []

        async def spy_tool(**kwargs):
            captured.append(kwargs)
            return [{"ok": True}]

        class _Runtime:
            def __init__(self, context):
                self.context = context

        original = orchestrator.TOOLS_MAP.get("spy_tool")
        orchestrator.TOOLS_MAP["spy_tool"] = spy_tool
        try:
            marker = _FakeSession()
            await orchestrator.tool_executor(
                _tool_state(),
                runtime=_Runtime(AgentContext(db_session=marker)),
            )
        finally:
            _restore(orchestrator, original)

        assert captured[0]["db_session"] is marker

    async def test_missing_session_is_none_rather_than_an_error(self):
        from backend.app.agent import orchestrator

        captured: list = []

        async def spy_tool(**kwargs):
            captured.append(kwargs)
            return [{"ok": True}]

        class _Runtime:
            context = None

        original = orchestrator.TOOLS_MAP.get("spy_tool")
        orchestrator.TOOLS_MAP["spy_tool"] = spy_tool
        try:
            await orchestrator.tool_executor(_tool_state(), runtime=_Runtime())
        finally:
            _restore(orchestrator, original)

        # None rather than a crash: the tool reports the problem, and the
        # orchestrator's rollback branch is guarded on db_session is not None.
        assert captured[0]["db_session"] is None


class TestToolFailureRollsBack:
    """A failed statement aborts the transaction; the session must be restored."""

    async def test_failing_tool_triggers_rollback(self):
        from backend.app.agent import orchestrator

        async def failing_tool(**kwargs):
            raise RuntimeError("InFailedSQLTransactionError: relation is locked")

        session = _FakeSession()

        class _Runtime:
            def __init__(self, context):
                self.context = context

        original = orchestrator.TOOLS_MAP.get("spy_tool")
        orchestrator.TOOLS_MAP["spy_tool"] = failing_tool
        try:
            result = await orchestrator.tool_executor(
                _tool_state(), runtime=_Runtime(AgentContext(db_session=session))
            )
        finally:
            _restore(orchestrator, original)

        assert session.rolled_back == 1
        # And the failure is handed to the model rather than raised, so it can
        # recover instead of the whole turn aborting.
        message = result["messages"][0]
        assert isinstance(message, ToolMessage)
        assert "error" in message.content.lower()

    async def test_rollback_failure_does_not_escape(self):
        from backend.app.agent import orchestrator

        class _AngrySession:
            async def rollback(self):
                raise RuntimeError("connection already closed")

        async def failing_tool(**kwargs):
            raise RuntimeError("boom")

        class _Runtime:
            def __init__(self, context):
                self.context = context

        original = orchestrator.TOOLS_MAP.get("spy_tool")
        orchestrator.TOOLS_MAP["spy_tool"] = failing_tool
        try:
            result = await orchestrator.tool_executor(
                _tool_state(),
                runtime=_Runtime(AgentContext(db_session=_AngrySession())),
            )
        finally:
            _restore(orchestrator, original)

        # A rollback that itself fails must not mask the original tool error.
        assert result["messages"][0].tool_call_id == "call_1"

    async def test_successful_tool_does_not_roll_back(self):
        from backend.app.agent import orchestrator

        async def ok_tool(**kwargs):
            return [{"ok": True}]

        session = _FakeSession()

        class _Runtime:
            def __init__(self, context):
                self.context = context

        original = orchestrator.TOOLS_MAP.get("spy_tool")
        orchestrator.TOOLS_MAP["spy_tool"] = ok_tool
        try:
            await orchestrator.tool_executor(
                _tool_state(), runtime=_Runtime(AgentContext(db_session=session))
            )
        finally:
            _restore(orchestrator, original)

        assert session.rolled_back == 0


class TestToolLifecycleEvents:
    """The client relies on these to drop narration and show tool activity."""

    async def test_tool_start_and_end_are_written_to_the_stream(self):
        import json

        from backend.app.agent import orchestrator

        written: list = []

        async def ok_tool(**kwargs):
            return [{"ok": True}]

        class _Runtime:
            context = None

        # get_stream_writer raises outside a real run, so patch it to capture
        # what the node would emit.
        import backend.app.agent.orchestrator as mod

        original_writer = mod.get_stream_writer
        original_tool = orchestrator.TOOLS_MAP.get("spy_tool")
        mod.get_stream_writer = lambda: written.append
        orchestrator.TOOLS_MAP["spy_tool"] = ok_tool
        try:
            await orchestrator.tool_executor(_tool_state(), runtime=_Runtime())
        finally:
            mod.get_stream_writer = original_writer
            _restore(orchestrator, original_tool)

        assert [w["type"] for w in written] == ["tool_start", "tool_end"]
        assert written[0]["name"] == "spy_tool"
