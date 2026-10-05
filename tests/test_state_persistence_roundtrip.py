"""
End-to-end proof that agent state persists across runs.

These use LangGraph's InMemorySaver, which implements the same BaseCheckpointSaver
contract as AsyncPostgresSaver. That makes the persistence semantics testable
without a live database: if a second run on the same thread_id sees the first
run's messages, the checkpoint is doing the work -- and the Postgres saver is
substituted for the same interface.

The graph's LLM and tools are stubbed, so nothing here calls a provider.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.app.agent.state import AgentState


def _build_probe_graph(recorder: list):
    """
    A minimal graph with the same state schema as the real agent.

    Mirrors the shape that matters for persistence: an `add_messages` channel
    that appends, and a node that records what it saw on entry.
    """
    def remember(state: AgentState):
        recorder.append([m.content for m in state["messages"]])
        return {"messages": [AIMessage(content="ack")]}

    workflow = StateGraph(AgentState)
    workflow.add_node("remember", remember)
    workflow.add_edge(START, "remember")
    workflow.add_edge("remember", END)
    return workflow


class TestStatePersistsAcrossRuns:
    """The behaviour the whole feature exists for."""

    async def test_second_run_sees_the_first_runs_messages(self):
        recorder: list = []
        graph = _build_probe_graph(recorder).compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "conversation-1"}}

        await graph.ainvoke({"messages": [HumanMessage(content="first")]}, config)
        await graph.ainvoke({"messages": [HumanMessage(content="second")]}, config)

        # The second run's node must have observed the first run's turn. If the
        # checkpointer were absent the graph would start from nothing each time
        # and this would be just ["second"].
        assert recorder[0] == ["first"]
        assert recorder[1] == ["first", "ack", "second"]

    async def test_separate_threads_do_not_share_state(self):
        recorder: list = []
        graph = _build_probe_graph(recorder).compile(checkpointer=InMemorySaver())

        await graph.ainvoke(
            {"messages": [HumanMessage(content="alpha")]},
            {"configurable": {"thread_id": "thread-a"}},
        )
        await graph.ainvoke(
            {"messages": [HumanMessage(content="beta")]},
            {"configurable": {"thread_id": "thread-b"}},
        )

        # Two conversations must not bleed into one another; that would surface
        # to a user as their new chat opening with someone else's history.
        assert recorder[1] == ["beta"]

    async def test_restored_state_matches_a_tuple_return(self):
        graph = _build_probe_graph([]).compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "conv-tuple"}}

        await graph.ainvoke({"messages": [HumanMessage(content="q1")]}, config)
        # get_state is how a caller inspects what a thread has stored, which is
        # what makes the persistence observable to the frontend later.
        snapshot = await graph.aget_state(config)
        contents = [m.content for m in snapshot.values["messages"]]
        assert contents == ["q1", "ack"]


class TestChatSessionThreadMapping:
    """A chat session must map to exactly one thread, deterministically."""

    def test_session_uuid_drives_the_thread(self):
        from backend.app.agent.checkpointer import thread_id_for

        assert thread_id_for("6f1a5f2e-0b1a-4f0e-9a0e-2f9a1b2c3d4e") == (
            "6f1a5f2e-0b1a-4f0e-9a0e-2f9a1b2c3d4e"
        )

    async def test_two_sessions_keep_separate_agent_memory(self):
        """
        End-to-end through the real helper: same graph, two session UUIDs.
        """
        import uuid

        from backend.app.agent.checkpointer import thread_id_for

        recorder: list = []
        graph = _build_probe_graph(recorder).compile(checkpointer=InMemorySaver())

        first, second = uuid.uuid4(), uuid.uuid4()
        await graph.ainvoke(
            {"messages": [HumanMessage(content="in session one")]},
            {"configurable": {"thread_id": thread_id_for(first)}},
        )
        await graph.ainvoke(
            {"messages": [HumanMessage(content="in session two")]},
            {"configurable": {"thread_id": thread_id_for(second)}},
        )

        assert recorder[1] == ["in session two"]

    async def test_returning_to_a_session_restores_its_memory(self):
        import uuid

        from backend.app.agent.checkpointer import thread_id_for

        recorder: list = []
        graph = _build_probe_graph(recorder).compile(checkpointer=InMemorySaver())
        session = uuid.uuid4()
        config = {"configurable": {"thread_id": thread_id_for(session)}}

        await graph.ainvoke({"messages": [HumanMessage(content="turn one")]}, config)
        await graph.ainvoke({"messages": [HumanMessage(content="turn two")]}, config)

        # This is the reload case: the user reopens an old conversation and the
        # agent still has both earlier turns.
        assert recorder[1] == ["turn one", "ack", "turn two"]


class TestContextIsNotPersisted:
    """
    The DB session rides in Runtime context, which LangGraph deliberately keeps
    out of the checkpoint. If it were serialized, every save would fail.
    """

    async def test_graph_runs_with_a_context_object(self):
        from backend.app.agent.state import AgentContext

        seen: list = []

        def uses_context(state: AgentState, runtime):
            seen.append(runtime.context)
            return {"messages": [AIMessage(content="ok")]}

        workflow = StateGraph(AgentState, context_schema=AgentContext)
        workflow.add_node("n", uses_context)
        workflow.add_edge(START, "n")
        workflow.add_edge("n", END)
        graph = workflow.compile(checkpointer=InMemorySaver())

        marker = object()
        await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            {"configurable": {"thread_id": "ctx-thread"}},
            # `context` is a top-level argument. Passing it inside the config
            # dict is silently ignored, leaving every node with a None context
            # and the tools querying with no session.
            context=AgentContext(db_session=marker),
        )

        assert isinstance(seen[0], AgentContext)
        assert seen[0].db_session is marker

    async def test_context_inside_the_config_dict_is_ignored(self):
        """
        Guards the mistake this suite was written to catch: `context` nested in
        config looks plausible and type-checks, but never reaches the node.
        """
        from backend.app.agent.state import AgentContext

        seen: list = []

        workflow = StateGraph(AgentState, context_schema=AgentContext)
        workflow.add_node(
            "n", lambda s, runtime: (seen.append(runtime.context), {"messages": []})[1]
        )
        workflow.add_edge(START, "n")
        workflow.add_edge("n", END)
        graph = workflow.compile(checkpointer=InMemorySaver())

        await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            {
                "configurable": {"thread_id": "ignored-thread"},
                "context": AgentContext(db_session=object()),
            },
        )

        assert seen[0] is None

    async def test_state_written_to_the_checkpoint_excludes_the_session(self):
        from backend.app.agent.state import AgentContext

        workflow = StateGraph(AgentState, context_schema=AgentContext)
        workflow.add_node("n", lambda s: {"messages": [AIMessage(content="ok")]})
        workflow.add_edge(START, "n")
        workflow.add_edge("n", END)
        graph = workflow.compile(checkpointer=InMemorySaver())

        config = {"configurable": {"thread_id": "serialize-thread"}}
        await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            config,
            context=AgentContext(db_session=object()),
        )

        snapshot = await graph.aget_state(config)
        # Only the schema's own channels are persisted. The session is reachable
        # solely through Runtime context, so there is nothing to serialize --
        # which is what lets the save succeed at all.
        assert set(snapshot.values.keys()) == set(AgentState.__annotations__)
        assert "db_session" not in snapshot.values
