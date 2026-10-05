# backend/app/v1/endpoints/chat.py

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.checkpointer import thread_id_for
from backend.app.agent.orchestrator import graph
from backend.app.agent.state import AgentContext
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.errors import log_and_client_message
from backend.app.core.security import verify_api_hitter
from backend.app.db.models.chat import ChatMessage, ChatSession
from backend.schemas.chat_schemas import (
    ChatHistoryResponseSchema,
    ChatMessageSchema,
    ChatRequestSchema,
    ChatSessionCreateSchema,
    ChatSessionResponseSchema,
    MessageRole,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _escape_frame_text(text: str) -> str:
    """
    Neutralizes framing tags inside replayed text.

    History is replayed verbatim into a prompt whose injection defence is
    written against named blocks. A stored message containing a closing tag
    could otherwise end `<chat_history>` early and place instructions outside
    the frame the system prompt reasons about. Angle brackets are folded rather
    than the text dropped: the content stays readable, the tag stops working.
    """
    return text.replace("<", "‹").replace(">", "›")


def _build_user_turn(history: list[ChatMessage], question: str) -> HumanMessage:
    """
    Wraps the turn in the frame the system prompt declares.

    The prompt specifies <chat_history> and <user_query> blocks; sending a bare
    question left those placeholders unfilled, so the model was told to answer
    from a context block that did not exist.
    """
    if history:
        transcript = "\n".join(
            f"{m.role}: {_escape_frame_text(m.content)}" for m in history
        )
    else:
        transcript = "(no prior messages)"

    # The live question is escaped too. It was interpolated raw, so a question
    # containing "</user_query>" closed the frame early and put the rest of the
    # text outside the one region the prompt's injection defence describes.
    content = (
        "<chat_history>\n"
        f"{transcript}\n"
        "</chat_history>\n\n"
        "<user_query>\n"
        f"{_escape_frame_text(question)}\n"
        "</user_query>"
    )
    return HumanMessage(content=content)


async def _get_or_create_session(
    db: AsyncSession, session_id: uuid.UUID
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        return session

    session = ChatSession(id=session_id, title="New Chat")
    db.add(session)
    await db.flush()
    return session


async def _load_history(
    db: AsyncSession, session_id: uuid.UUID, limit: int
) -> list[ChatMessage]:
    """
    Returns up to `limit` most recent messages, oldest first.

    Ordered by `seq`, not `created_at`: coarse platform clocks (Windows is
    ~15.6ms) let a user message and its assistant reply share a timestamp,
    which made the transcript order arbitrary.
    """
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.seq.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()  # Oldest first for the prompt's transcript.
    return messages


@router.post(
    "/stream",
    summary="Stream an agentic RAG answer over SSE",
)
async def chat_stream(
    payload: ChatRequestSchema,
    request: Request,
    db_session: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
) -> StreamingResponse:
    """
    Streams the agent's response token-by-token using Server-Sent Events (SSE).

    The agent keeps its own memory: with the Postgres checkpointer enabled,
    LangGraph restores this conversation's saved state -- prior messages, tool
    calls and their results -- and resumes from it, so only the new question is
    sent. Without a checkpointer the endpoint falls back to replaying the
    stored transcript itself.

    Either way the user and assistant turns are written to `chat_messages`,
    which is what the transcript endpoint reads.
    """
    try:
        session_uuid = uuid.UUID(str(payload.session_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{payload.session_id}' is not a valid session UUID.",
        )

    question = payload.messages[-1].content
    if not question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The final message must contain a non-empty question.",
        )

    session = await _get_or_create_session(db_session, session_uuid)

    # Persist the user's turn before streaming, and COMMIT rather than flush.
    # Tools run on this same session, and a failed tool query aborts the
    # Postgres transaction -- every later statement then fails with
    # InFailedSQLTransactionError, including the assistant-turn commit. That
    # would lose the user's question as well as the answer.
    db_session.add(
        ChatMessage(session_id=session_uuid, role=MessageRole.USER.value, content=question)
    )
    await db_session.commit()

    # The runnable is chosen once at startup by the lifespan: the graph
    # compiled with the Postgres checkpointer when it is available, otherwise
    # the stateless one. Reading it from app.state (rather than importing
    # `graph`) is what lets persistence be enabled without a code change.
    runnable = getattr(request.app.state, "graph", None) or graph
    checkpointing = bool(getattr(request.app.state, "checkpointing", False))

    # With a checkpointer the thread already holds the conversation, so passing
    # history again would replay it twice -- duplicated turns in the model's
    # context and a checkpoint that grows on every request. Only the stateless
    # fallback still needs the transcript supplied by the caller.
    if checkpointing:
        graph_input: dict = {"messages": [HumanMessage(content=question)]}
    else:
        history = await _load_history(
            db_session, session_uuid, settings.MAX_HISTORY_MESSAGES
        )
        graph_input = {"messages": [_build_user_turn(history, question)]}

    # `thread_id` is the conversation identity. With a checkpointer, LangGraph
    # reloads this thread's saved state -- messages, tool calls, tool results --
    # so the agent resumes with everything it saw in earlier cycles. Only the
    # new question is passed in; history is no longer re-sent by the caller.
    #
    # The DB session travels in `context`, not `configurable`: the checkpointer
    # serializes configurable into the stored checkpoint, and an AsyncSession is
    # neither serializable nor meaningful in a later process.
    config = {
        "configurable": {"thread_id": thread_id_for(session_uuid)},
        "context": AgentContext(db_session=db_session),
    }

    async def sse_generator() -> AsyncGenerator[str, None]:
        # Text emitted before a tool call is the model narrating ("Let me
        # search for that."), not the answer. It is streamed to the client for
        # responsiveness but discarded, so only the final turn's text is
        # persisted and re-fed as history on later requests.
        current_parts: list[str] = []

        try:
            # Two stream modes are consumed together: "messages" carries token
            # deltas from the model, and "custom" carries the tool lifecycle
            # the tool node writes directly. LangChain's own on_tool_start
            # events never fire here because these tools are plain coroutines
            # rather than BaseTools.
            async for mode, item in runnable.astream(
                graph_input,
                config=config,
                stream_mode=["messages", "custom"],
            ):
                if mode == "custom":
                    # Resets the narration buffer: text produced before a tool
                    # call is the model thinking out loud, not the answer.
                    if isinstance(item, dict) and item.get("type") == "tool_start":
                        current_parts = []
                    if isinstance(item, dict):
                        yield _sse(item)
                    continue

                if mode != "messages":
                    continue

                chunk = item[0] if isinstance(item, tuple) else item
                content = getattr(chunk, "content", None)
                # Tool-call argument deltas arrive as empty content, so
                # empty chunks are skipped rather than forwarded.
                if isinstance(content, str) and content:
                    current_parts.append(content)
                    yield _sse({"type": "chunk", "content": content})
                elif isinstance(content, list) and content:
                    text = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )
                    if text:
                        current_parts.append(text)
                        yield _sse({"type": "chunk", "content": text})

            answer = "".join(current_parts)

            # Persist the assistant turn and stamp the session as active.
            db_session.add(
                ChatMessage(
                    session_id=session_uuid,
                    role=MessageRole.ASSISTANT.value,
                    content=answer,
                )
            )
            session.updated_at = datetime.now(timezone.utc)
            await db_session.commit()

            yield _sse({"type": "done", "session_id": str(session_uuid)})
            yield "data: [DONE]\n\n"

        except Exception as e:
            # The response has already started, so the failure is reported
            # inside the stream; rolling back here keeps the partial turn. The
            # message is the client-safe summary — the exception text can carry
            # the DSN or a filesystem path, and this goes straight to a browser.
            await db_session.rollback()
            yield _sse(
                {"type": "error", "message": log_and_client_message(e, "Chat stream failed")}
            )
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx from buffering the stream into a single response.
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/sessions",
    response_model=ChatSessionResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chat session",
)
async def create_session(
    payload: ChatSessionCreateSchema,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
) -> ChatSession:
    """Starts a new conversation and returns its generated id."""
    session = ChatSession(title=payload.title or "New Chat")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get(
    "/sessions",
    response_model=list[ChatSessionResponseSchema],
    summary="List chat sessions",
)
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """Returns sessions, most recently active first."""
    # `limit` needs a lower bound as well: LIMIT -1 is a SQL error, so a
    # negative limit would surface as a 500 instead of a 4xx.
    page_limit, page_offset = max(1, min(limit, 100)), max(offset, 0)
    result = await db.execute(
        select(ChatSession)
        .order_by(ChatSession.updated_at.desc())
        .limit(page_limit)
        .offset(page_offset)
    )
    return list(result.scalars().all())


@router.get(
    "/sessions/{session_id}",
    response_model=ChatHistoryResponseSchema,
    summary="Fetch a session transcript",
)
async def get_session_history(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """Returns the stored messages for a session, oldest first."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session {session_id} not found.",
        )

    messages = await _load_history(
        db, session_id, settings.MAX_HISTORY_MESSAGES
    )
    return ChatHistoryResponseSchema(
        session_id=session_id,
        messages=[
            ChatMessageSchema(role=m.role, content=m.content) for m in messages
        ],
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """Deletes a session; its messages cascade."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session {session_id} not found.",
        )
    await db.delete(session)
    await db.commit()
    return None