# backend/app/agent/orchestrator.py

""" Neccessary imports. """

import json
import logging

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from backend.app.agent.state import AgentContext, AgentState
from backend.app.agent.prompts import AGENT_SYSTEM_PROMPT
from backend.app.core.config import settings
from backend.app.core.errors import client_message
from backend.app.tools import tool_schemas, TOOLS_MAP

logger = logging.getLogger(__name__)


""" Initializing the LLM and Binding the LLM with the available tools. """
llm = ChatOpenAI(
    model=settings.LLM,
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY,
    streaming=True,
).bind_tools(
    tools=tool_schemas,
    tool_choice="auto",
    parallel_tool_calls=True)


def get_llm():
    """
    Returns the bound chat model.

    Kept as a factory so tests and scripts can substitute a stub model without
    re-running module import, which would otherwise require live API keys.
    """
    return llm


def _session_of(runtime: Runtime | None):
    """Pulls the request's DB session out of the (unserialized) run context."""
    if runtime is None:
        return None
    context = getattr(runtime, "context", None)
    if isinstance(context, AgentContext):
        return context.db_session
    if isinstance(context, dict):
        return context.get("db_session")
    return getattr(context, "db_session", None)


async def llm_node(state: AgentState, runtime: Runtime):
    """
    The core LLM node.
    This node passes the current state (conversation history + tool outputs) to the LLM.
    """

    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + list(messages)

    response = await llm.ainvoke(messages)

    return {
        "messages": [response],
        "llm_call_count": 1
    }


def decision(state: AgentState):
    """
    This function is the conditional edge
    that dicides whether to perform tool call or llm call.
    """

    last_message = state["messages"][-1]
    wants_tools = bool(getattr(last_message, "tool_calls", None))

    # The budget only applies while the agent is still working. Checking it
    # first meant that on the turn the model produced its final answer -- no
    # tool_calls -- an exhausted counter replaced that answer with the
    # circuit-breaker apology, so a legitimately long search threw away the
    # correct response it had just written.
    if not wants_tools:
        return END

    if (state.get("tool_call_count", 0) >= settings.MAX_TOOL_CALLS
            or state.get("llm_call_count", 0) >= settings.MAX_LLM_CALLS):
        return "circuit_breaker"

    return "tools"


async def tool_executor(state: AgentState, runtime: Runtime):
    """
    A custom node to execute tools requested by the LLM.
    """

    messages = state["messages"]
    last_message = messages[-1]
    tool_responses = []

    db_session = _session_of(runtime)

    # Tools here are plain coroutines rather than BaseTools, so LangChain emits
    # no on_tool_start/on_tool_end events for them. Emitting the lifecycle
    # explicitly is what lets the endpoint drop the model's pre-tool narration
    # and show tool activity in the UI.
    writer = None
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None

    tool_calls = getattr(last_message, "tool_calls", None) or []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args") or {}
        # Some providers omit the id; LangChain requires a non-empty value to
        # pair the ToolMessage with its call.
        tool_call_id = tool_call.get("id") or f"call_{tool_name}"

        if writer is not None:
            try:
                writer({"type": "tool_start", "name": tool_name,
                        "status": f"Running {tool_name}..."})
            except Exception:
                logger.debug("Could not emit tool_start for %s", tool_name)

        try:
            tool_function = TOOLS_MAP.get(tool_name)

            if not tool_function:
                raise ValueError(f"Tool {tool_name} not found in registry.")

            # db_session is injected here so tools never receive it from the
            # model, which keeps connection handling out of the tool schemas.
            raw_result = await tool_function(**tool_args, db_session=db_session)
            formatted_result = json.dumps(raw_result, default=str)

        except Exception as e:
            logger.exception("Tool %s failed", tool_name)
            # A failed statement aborts the Postgres transaction, so every
            # later query on this session would fail with
            # InFailedSQLTransactionError. Rolling back here restores the
            # session so the remaining tool calls -- and the final commit of
            # the assistant turn -- can still run.
            if db_session is not None:
                try:
                    await db_session.rollback()
                except Exception:
                    logger.warning("Could not roll back after tool failure")
            # Returned to the model as a normal result so it can recover or
            # explain the failure instead of the whole run aborting. The model
            # can echo this into its answer, so it carries the client-safe
            # summary rather than the driver's text.
            formatted_result = json.dumps(
                {"error": f"Error executing {tool_name}: {client_message(e)}"}
            )

        tool_message = ToolMessage(
            content=formatted_result,
            tool_call_id=tool_call_id,
            name=tool_name
        )
        tool_responses.append(tool_message)

        if writer is not None:
            try:
                writer({"type": "tool_end", "name": tool_name})
            except Exception:
                logger.debug("Could not emit tool_end for %s", tool_name)

    return {
        "messages": tool_responses,
        # One AIMessage can request several tools, and the cap is expressed in
        # rounds. Counting the round keeps MAX_TOOL_CALLS meaning what it says.
        "tool_call_count": 1 if tool_responses else 0
    }


def circuit_breaker_node(state: AgentState):
    """
    Failsafe node when the agent gets stuck in a loop.
    """
    messages = state["messages"]

    # Every tool call the model requested needs an answer, even when the budget
    # runs out. Leaving an AIMessage's tool_calls unanswered makes the message
    # list invalid: providers reject a request whose tool calls have no matching
    # ToolMessages. Harmless today only because the endpoint flattens history to
    # text, but the checkpointed state keeps the real message objects, so an
    # unbalanced list would be replayed verbatim on the next turn.
    answered = {
        getattr(m, "tool_call_id", None)
        for m in messages
        if isinstance(m, ToolMessage)
    }
    replies: list[ToolMessage] = []
    for message in reversed(messages):
        for call in getattr(message, "tool_calls", None) or []:
            call_id = call.get("id") or f"call_{call.get('name')}"
            if call_id in answered:
                continue
            answered.add(call_id)
            replies.append(
                ToolMessage(
                    content=json.dumps(
                        {
                            "error": (
                                "Search stopped: the agent reached its step limit "
                                "before this lookup ran."
                            )
                        }
                    ),
                    tool_call_id=call_id,
                    name=call.get("name") or "tool",
                )
            )
    replies.reverse()

    emergency_message = AIMessage(
        content=(
            "I apologize, but I had to stop searching because I am stuck in a "
            "loop or it is taking too many steps. Please try rephrasing your "
            "question."
        )
    )
    return {"messages": [*replies, emergency_message]}



""" Below is the Core Agentic Loop """

workflow = StateGraph(AgentState, context_schema=AgentContext)

workflow.add_node("agent", llm_node)
workflow.add_node("tools", tool_executor)
workflow.add_node("circuit_breaker", circuit_breaker_node)

# Adding Edges.
workflow.add_edge(START, "agent")

# Routing based on the LLM's output.
workflow.add_conditional_edges(
    "agent",
    decision,
    {
        "tools": "tools",
        "circuit_breaker": "circuit_breaker",
        END: END
    }
)

workflow.add_edge("tools", "agent")
workflow.add_edge("circuit_breaker", END) # If the circuit breaker trips, the graph ends immediately.

# Compiled without a checkpointer here on purpose. The saver owns a connection
# pool that must be opened by the application lifespan and closed at shutdown,
# and this module is imported by scripts and tests that never start the app.
# The lifespan compiles the checkpointed graph and stores it on `app.state`;
# this remains the stateless fallback for anything running outside the app.
graph = workflow.compile()


def get_graph(checkpointer=None):
    """
    Returns the graph to run, checkpointed when a saver is supplied.

    Kept as a function so the saver is bound at request time instead of import
    time. With no saver this returns the stateless graph, which behaves exactly
    as the app did before persistence existed.
    """
    if checkpointer is None:
        return graph
    return workflow.compile(checkpointer=checkpointer)
