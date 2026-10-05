# backend/app/agent/state.py

import operator
from dataclasses import dataclass
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


@dataclass
class AgentContext:
    """
    Per-run resources that must never be written to the checkpoint.

    The checkpointer serializes the graph state to JSONB and BYTEA, and it also
    copies `config["configurable"]` into the stored checkpoint config. An
    AsyncSession is neither serializable nor meaningful across processes, so it
    used to travel in `configurable` -- which worked only because no checkpointer
    existed to persist it. Adding one would have turned every save into a
    failure.

    LangGraph's `context_schema` is the supported channel for this: it is
    available to nodes through `Runtime.context` and is explicitly excluded
    from persistence.
    """

    db_session: object = None


class AgentState(TypedDict):
    """
    The state of the agent's execution.

    The `add_messages` reducer is what makes the checkpointer useful: it appends
    new messages to the restored history instead of overwriting it, so each
    cycle resumes with everything the earlier cycles saw.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]

    llm_call_count: Annotated[int, operator.add]
    tool_call_count: Annotated[int, operator.add]
