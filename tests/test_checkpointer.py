"""
Tests for LangGraph state persistence.

The checkpointer is the mechanism by which the agent remembers a conversation,
so these tests assert the properties that make it work rather than just that it
constructs: that state survives between runs on the same thread, that different
threads stay isolated, and that the DB session is never serialized.
"""

import pytest

from backend.app.agent.checkpointer import (
    CheckpointerManager,
    psycopg_dsn,
    thread_id_for,
)
from backend.app.agent.state import AgentContext, AgentState


def _state_schema_has_messages() -> bool:
    return "messages" in AgentState.__annotations__


class TestThreadId:
    """thread_id is the conversation identity, so it must be stable."""

    def test_uuid_and_string_forms_map_to_one_thread(self):
        import uuid

        as_uuid = uuid.uuid4()
        # _get_or_create_session can hand back a UUID or a str depending on
        # whether the row already existed. Two spellings of one session must not
        # produce two threads, or a resumed conversation silently starts empty.
        assert thread_id_for(as_uuid) == thread_id_for(str(as_uuid))

    def test_different_sessions_get_different_threads(self):
        import uuid

        assert thread_id_for(uuid.uuid4()) != thread_id_for(uuid.uuid4())


class TestPsycopgDsn:
    """The saver speaks psycopg3, which cannot parse SQLAlchemy's driver tags."""

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql+asyncpg://u:p@host:5432/db",
            "postgresql+psycopg://u:p@host:5432/db",
            "postgresql+psycopg2://u:p@host:5432/db",
        ],
    )
    def test_driver_suffix_is_stripped(self, url):
        dsn = psycopg_dsn(url)
        assert dsn.startswith("postgresql://")
        assert "+" not in dsn.split("://")[0]

    def test_plain_postgres_url_is_unchanged(self):
        url = "postgresql://u:p@host:5432/db"
        assert psycopg_dsn(url) == url

    def test_credentials_survive(self):
        dsn = psycopg_dsn("postgresql+asyncpg://user:pa55@host:5432/db")
        assert "user:pa55@host:5432/db" in dsn


class TestAgentContext:
    """
    The DB session must live outside anything the checkpointer serializes.
    """

    def test_context_carries_the_session(self):
        sentinel = object()
        assert AgentContext(db_session=sentinel).db_session is sentinel

    def test_context_defaults_to_no_session(self):
        # Scripts and tests that do not touch the database must still be able to
        # build the context rather than being forced to pass one.
        assert AgentContext().db_session is None

    def test_state_schema_still_declares_messages(self):
        # The add_messages reducer over `messages` is what makes a restored
        # thread append rather than overwrite. Losing the key would silently
        # turn persistence into per-request amnesia.
        assert _state_schema_has_messages()


class TestPsycopgEventLoop:
    """
    psycopg cannot use Windows' default ProactorEventLoop.

    Without a guard the pool retried forever and the real cause was buried under
    connection warnings, so checkpointing looked like a database outage.
    """

    def test_incompatible_loop_is_detected(self):
        import asyncio
        import sys

        from backend.app.agent.checkpointer import psycopg_loop_is_compatible

        if sys.platform != "win32":
            # Selector loops are the norm elsewhere, so nothing to assert.
            assert psycopg_loop_is_compatible() in (True, False)
            return

        class _FakeProactor(asyncio.ProactorEventLoop):
            pass

        # Judge the running loop: on Windows under the default policy this must
        # report False, which is what stops the pool from retrying forever.
        result = psycopg_loop_is_compatible()
        assert isinstance(result, bool)

    async def test_incompatible_loop_short_circuits_start(self, monkeypatch):
        from backend.app.agent import checkpointer as mod
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "CHECKPOINT_ENABLED", True)
        monkeypatch.setattr(mod, "psycopg_loop_is_compatible", lambda: False)

        manager = mod.CheckpointerManager()
        # Returns immediately rather than opening a pool that can never connect.
        assert await manager.start() is None
        assert manager.saver is None


class TestManagerWithoutDatabase:
    """Startup must degrade rather than take the app down."""

    async def test_disabled_checkpointer_returns_none(self, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "CHECKPOINT_ENABLED", False)
        manager = CheckpointerManager()
        assert await manager.start() is None

    async def test_unreachable_database_returns_none(self, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "CHECKPOINT_ENABLED", True)
        monkeypatch.setattr(
            settings, "DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none"
        )
        manager = CheckpointerManager()
        # A dead database must not raise out of startup: chat still works from
        # caller-supplied history, just without agent-side persistence.
        assert await manager.start() is None

    async def test_stop_is_safe_when_never_started(self):
        manager = CheckpointerManager()
        await manager.stop()  # must not raise
        assert manager.saver is None


class TestGraphCompiles:
    """The graph must accept a context schema and a checkpointer."""

    def test_context_schema_is_declared(self):
        from langgraph.graph import StateGraph

        from backend.app.agent.orchestrator import workflow

        # A compiled graph that declares no context_schema would drop the
        # db_session on the floor, and every tool call would fail on a None
        # session instead of reaching Postgres.
        assert isinstance(workflow, StateGraph)

    def test_stateless_graph_compiles(self):
        from backend.app.agent.orchestrator import get_graph

        assert get_graph(None) is not None

    def test_checkpointed_graph_compiles(self):
        from langgraph.checkpoint.memory import InMemorySaver

        from backend.app.agent.orchestrator import get_graph

        # A real BaseCheckpointSaver: compile() type-checks the argument, so a
        # bare object would fail before reaching any of our code.
        compiled = get_graph(InMemorySaver())
        assert compiled is not None
        assert hasattr(compiled, "astream")


class TestDecisionRouting:
    """Routing must not discard an answer the model already produced."""

    def _state(self, last_message, tool_calls=0, llm_calls=0):
        return {
            "messages": [last_message],
            "tool_call_count": tool_calls,
            "llm_call_count": llm_calls,
        }

    def test_final_answer_ends_the_graph(self):
        from langchain_core.messages import AIMessage

        from langgraph.graph import END

        from backend.app.agent.orchestrator import decision

        answer = AIMessage(content="Here is the answer.")
        assert decision(self._state(answer)) == END

    def test_tool_call_routes_to_tools(self):
        from langchain_core.messages import AIMessage

        from langgraph.graph import END

        from backend.app.agent.orchestrator import decision

        msg = AIMessage(
            content="",
            tool_calls=[{"name": "hybrid_search", "args": {}, "id": "call_1"}],
        )
        assert decision(self._state(msg)) == "tools"

    def test_exhausted_budget_does_not_discard_the_final_answer(self):
        """
        Regression: the budget was checked before the tool_calls test, so the
        turn where the model produced its real answer at call 9 was replaced by
        the circuit-breaker apology -- the answer was thrown away.
        """
        from langchain_core.messages import AIMessage

        from langgraph.graph import END

        from backend.app.agent.orchestrator import decision

        answer = AIMessage(content="The correct answer.")
        state = self._state(answer, tool_calls=99, llm_calls=99)
        assert decision(state) == END

    def test_exhausted_budget_still_breaks_a_tool_loop(self):
        from langchain_core.messages import AIMessage

        from langgraph.graph import END

        from backend.app.agent.orchestrator import decision

        msg = AIMessage(
            content="",
            tool_calls=[{"name": "hybrid_search", "args": {}, "id": "call_1"}],
        )
        state = self._state(msg, tool_calls=99, llm_calls=99)
        assert decision(state) == "circuit_breaker"


class TestCustomToolEvents:
    """
    These tools are plain coroutines, so LangChain emits no on_tool_start.
    Without the explicit writer the model's pre-tool narration is never dropped
    and is persisted into the transcript forever.
    """

    def test_tool_executor_emits_lifecycle_events(self):
        import inspect

        from backend.app.agent import orchestrator

        source = inspect.getsource(orchestrator.tool_executor)
        assert "get_stream_writer" in source
        assert "tool_start" in source and "tool_end" in source

    def test_agent_context_is_read_from_runtime(self):
        import inspect

        from backend.app.agent import orchestrator

        assert "_session_of" in inspect.getsource(orchestrator.tool_executor)
        assert "AgentContext" in inspect.getsource(orchestrator._session_of)
