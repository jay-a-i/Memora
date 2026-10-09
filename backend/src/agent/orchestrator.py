# backend/app/agents/orchestrator.py

""" Neccessary imports. """

import json
import logging

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from src.agent.state import AgentState
from src.agent.prompts import AGENT_SYSTEM_PROMPT
from src.core.config import settings
from src.core.errors import client_message
from src.tools import tool_schemas, TOOLS_MAP

logger = logging.getLogger(__name__)


""" Initializing the LLM and Binding the LLM with the available tools. """
llm = ChatOpenAI(
    model=settings.LLM,
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY,
    streaming=True,
    model_kwargs={"truncation": "auto"}
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


async def llm_node(state: AgentState):
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

    if (state.get("tool_call_count", 0) >= settings.MAX_TOOL_CALLS
            or state.get("llm_call_count", 0) >= settings.MAX_LLM_CALLS):
        return "circuit_breaker"

    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


async def tool_executor(state: AgentState, config: RunnableConfig):
    """
    A custom node to execute tools requested by the LLM.
    """

    messages = state["messages"]
    last_message = messages[-1]
    tool_responses = []

    db_session = (config or {}).get("configurable", {}).get("db_session")

    tool_calls = getattr(last_message, "tool_calls", None) or []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args") or {}
        # Some providers omit the id; LangChain requires a non-empty value to
        # pair the ToolMessage with its call.
        tool_call_id = tool_call.get("id") or f"call_{tool_name}"

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

    return {
        "messages": tool_responses,
        "tool_call_count": 1 if tool_responses else 0
    }


def circuit_breaker_node(state: AgentState):
    """
    Failsafe node when the agent gets stuck in a loop.
    """
    emergency_message = AIMessage(
        content=(
            "I apologize, but I had to stop searching because I am stuck in a "
            "loop or it is taking too many steps. Please try rephrasing your "
            "question."
        )
    )
    return {"messages": [emergency_message]}



""" Below is the Core Agentic Loop """

workflow = StateGraph(AgentState)

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

# No checkpointer: history is supplied by the caller on each request and
# persisted by the chat endpoint, so the graph stays stateless and does not
# try to serialize the live db_session carried in config["configurable"].
graph = workflow.compile()