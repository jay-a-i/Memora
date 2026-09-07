# backend/app/agents/state.py

import operator
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    The state of the agent's execution.
    
    The `add_messages` reducer function is critical: instead of overwriting 
    the messages list on every turn, it appends new messages (LLM responses, 
    tool outputs) to the existing list.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]

    llm_call_count: Annotated[int, operator.add]
    tool_call_count: Annotated[int, operator.add]