# backend/app/agents/orchestrator.py

""" Neccessary imports. """

import json
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage

from app.agents.state import AgentState
from app.agents.prompts import AGENT_SYSTEM_PROMPT
from app.core.config import settings
from app.tools import tool_schemas, TOOLS_MAP

""" Loading the .env Secrets. """
load_dotenv() 


""" Initializing the LLM and Binding the LLM with the available tools. """

llm = ChatOpenAI(
    model="minimax/minimax-m3:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY,
    streaming=True,
).bind_tools(
    tools=tool_schemas, 
    tool_choice="auto", 
    parallel_tool_calls=True)

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

    if state.get("tool_call_count", 0) >= 5 or state.get("llm_call_count", 0) >= 10:
        return "circuit_breaker"

    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

async def tool_executor(state: AgentState, config: dict):
    """
    A custom node to execute tools requested by the LLM.
    """

    messages = state["messages"]
    last_message = messages[-1]
    tool_responses = []
    
    db_session = config.get("configurable", {}).get("db_session")

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]
        
        try:
            tool_function = TOOLS_MAP.get(tool_name)
            
            if not tool_function:
                raise ValueError(f"Tool {tool_name} not found in registry.")
            
            raw_result = await tool_function(**tool_args, db_session=db_session)
            formatted_result = json.dumps(raw_result)
            
        except Exception as e:
            formatted_result = f"Error executing {tool_name}: {str(e)}"
            
        tool_message = ToolMessage(
            content=formatted_result,
            tool_call_id=tool_call_id,
            name=tool_name
        )
        tool_responses.append(tool_message)

    return {
            "messages": tool_responses,
            "tool_call_count": len(tool_responses)
            }

def circuit_breaker_node(state: AgentState):
    """
    Failsafe node when the agent gets stuck in a loop.
    """

    emergency_message = AIMessage(
        content="I apologize, but I had to stop searching because I am stuck in a loop or it is taking too many steps. Please try rephrasing your question."
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

graph = workflow.compile()