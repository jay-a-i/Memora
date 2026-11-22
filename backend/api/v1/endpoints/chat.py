import json
import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from langchain_core.messages import HumanMessage, AIMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from agent import AgentContext
from core import settings, log_and_client_message, verify_api_hitter 
from db import get_db, ChatSession, ChatMessage 

from schemas import (
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


def thread_id_for(session_id: Any) -> str:
    return str(session_id)


def _content_as_text(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )
    return ""


def _checkpoint_answer_for_turn(
    messages: list,
    turn_id: str,
) -> str | None:
    """
    Extract a completed assistant answer that belongs to this turn.

    Returns None if the turn's HumanMessage or its completed answer
    cannot be found.
    """
    turn_index = next(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, HumanMessage)
            and message.id == turn_id
        ),
        None,
    )

    if turn_index is None:
        return None

    for message in reversed(messages[turn_index + 1:]):
        if isinstance(message, AIMessage):
            # A tool-call message is not a completed user-facing answer.
            if message.tool_calls:
                return None
            
            answer = _content_as_text(message.content)
            return answer or None
        
    return None


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
    messages.reverse()
    return messages


async def _find_turn_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    turn_id: str,
    role: str,
) -> ChatMessage | None:
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.turn_id == turn_id,
            ChatMessage.role == role,
        )
    )

    return result.scalar_one_or_none()


async def _claim_user_turn(
    db: AsyncSession,
    session_id: uuid.UUID,
    turn_id: str,
    content: str,
) -> bool:
    stmt = (
        insert(ChatMessage)
        .values(
            session_id=session_id,
            role=MessageRole.USER.value,
            content=content,
            turn_id=turn_id,
        )
        .on_conflict_do_nothing(constraint="uq_chat_messages_session_turn_role")
        .returning(ChatMessage.id)
    )
    inserted_id = (await db.execute(stmt)).scalar_one_or_none()
    await db.commit()
    return inserted_id is not None


async def _store_assistant_turn(
    db: AsyncSession,
    session_id: uuid.UUID,
    turn_id: str,
    content: str,
) -> None:
    stmt = (
        insert(ChatMessage)
        .values(
            session_id=session_id,
            role=MessageRole.ASSISTANT.value,
            content=content,
            turn_id=turn_id,
        )
        .on_conflict_do_nothing(constraint="uq_chat_messages_session_turn_role")
    )
    await db.execute(stmt)


def get_session_lock(session_id: str) -> asyncio.Lock:
    """
    Return the lock associated with one conversation.

    This coordinates requests within a single running backend process.
    """

    _session_locks: dict[str, asyncio.Lock] = {}

    lock = _session_locks.get(session_id)

    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock

    return lock

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
    sent.

    Idempotency: the client should send a stable `turn_id` per logical turn.
    A retry that reuses the same `turn_id` receives 409 and never re-enters
    the graph, so no duplicate user message is persisted and no duplicate
    HumanMessage is appended to the checkpointed thread state.
    """
    try:
        session_uuid = uuid.UUID(str(payload.session_id))

        session_lock = get_session_lock(str(session_uuid))
        await session_lock.acquire()

    except (ValueError, AttributeError, TypeError):
        session_lock.release()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{payload.session_id}' is not a valid session UUID.",
        )

    if not payload.messages or not payload.messages[-1].content.strip():
        session_lock.release()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The messages input cannot be empty",
        )

    user_msg = payload.messages[-1].content
    session = await _get_or_create_session(db_session, session_uuid)

    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        session_lock.release()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Graph is None",
        )
    
    config = {
        "configurable": {
            "thread_id": thread_id_for(session_uuid)
        },
        "recursion_limit": 30
    }

    snapshot = await graph.aget_state(config)
    checkpoint_messages = list(snapshot.values.get("messages", []))

    last_checkpointed_user = next(
        (
            message
            for message in reversed(checkpoint_messages)
            if isinstance(message, HumanMessage)
        ),
        None,
    )
    run_context = AgentContext(db_session=db_session)


    # ---- Idempotency gate: MUST happen before graph.astream ----
    
    existing_user = await _find_turn_message(
        db_session,
        session_uuid,
        payload.turn_id,
        MessageRole.USER.value,
    )

    existing_assistant = await _find_turn_message(
        db_session,
        session_uuid,
        payload.turn_id,
        MessageRole.ASSISTANT.value,
    )

    graph_input = None
    resume_existing_run = False
    replay_answer: str | None = None

    if existing_user is not None:
        # Reusing a turn ID with different content is invalid.
        if existing_user.content != user_msg:
            
            session_lock.release()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This turn ID has already been used for different content.",
            )

        if existing_assistant is not None:
            # The turn completed previously. Replay the saved answer.
            replay_answer = existing_assistant.content

        elif snapshot.next:
            # There is unfinished graph work. Resume only if it belongs
            # to the same logical user turn.
            if (
                last_checkpointed_user is None
                or last_checkpointed_user.id != payload.turn_id
            ):
                session_lock.release()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Another turn is unfinished. Resume that turn "
                        "before submitting a different question."
                    ),
                )

            resume_existing_run = True

        else:
            # Recover the case where LangGraph checkpointed its final answer,
            # but the application failed before saving it to chat_messages.
            recovered_answer = _checkpoint_answer_for_turn(
                checkpoint_messages,
                payload.turn_id,
            )

            if recovered_answer is not None:
                await _store_assistant_turn(
                    db_session,
                    session_uuid,
                    payload.turn_id,
                    recovered_answer,
                )
                await db_session.commit()
                replay_answer = recovered_answer

            elif not any(
                isinstance(message, HumanMessage)
                and message.id == payload.turn_id
                for message in checkpoint_messages
            ):
                # The SQL turn exists, but the graph never checkpointed its input.
                graph_input = {
                    "messages": [
                        HumanMessage(
                            content=user_msg,
                            id=payload.turn_id,
                        )
                    ]
                }

            else:
                session_lock.release()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "The turn is in an inconsistent state. "
                        "Do not append another copy of the question."
                    ),
                )

    else:
        # New logical turn. Never append a new question to an unfinished run.
        if snapshot.next:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A previous graph execution is unfinished. "
                    "Retry that turn before submitting a new question."
                ),
            )

        is_new_turn = await _claim_user_turn(
            db_session,
            session_uuid,
            payload.turn_id,
            user_msg,
        )

        if not is_new_turn:

            session_lock.release()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This turn has already been submitted.",
            )

        graph_input = {
            "messages": [
                HumanMessage(
                    content=user_msg,
                    id=payload.turn_id,
                )
            ]
        }

    async def sse_generator() -> AsyncGenerator[str, None]:

        if replay_answer is not None:
            if replay_answer:
                yield _sse({
                    "type": "chunk",
                    "content": replay_answer,
                })

            yield _sse({"type": "done", "session_id": str(session_uuid),})
            yield "data: [DONE]\n\n"
            
            return

        current_parts: list[str] = []

        try:
            stream_input = None if resume_existing_run else graph_input

            async for mode, item in graph.astream(
                stream_input,
                config=config,
                context=run_context,
                stream_mode=["messages", "custom"],
            ):
                if mode == "custom":
                    if isinstance(item, dict) and item.get("type") == "tool_start":
                        current_parts = []
                        yield _sse(item)
                    elif isinstance(item, dict) and item.get("type") == "tool_end":
                        current_parts = []
                        yield _sse(item)
                    continue

                if mode != "messages":
                    continue

                chunk = item[0] if isinstance(item, tuple) else item
                content = getattr(chunk, "content", None)
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

            await _store_assistant_turn(
                db_session, session_uuid, payload.turn_id, answer,
            )
            session.updated_at = datetime.now(timezone.utc)
            await db_session.commit()

            yield _sse({"type": "done", "session_id": str(session_uuid)})
            yield "data: [DONE]\n\n"

        except Exception as e:
            await db_session.rollback()
            yield _sse(
                {"type": "error", "message": log_and_client_message(e, "Chat stream failed")}
            )
            yield "data: [DONE]\n\n"

        finally:
            session_lock.release()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
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

    messages = await _load_history(db, session_id, settings.MAX_HISTORY_MESSAGES)
    return ChatHistoryResponseSchema(
        session_id=session_id,
        messages=[
            ChatMessageSchema(role=m.role, content=m.content, turn_id=m.turn_id,
                ) for m in messages]
        )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
)
async def delete_session(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """Deletes a session; its messages cascade."""

    lock = get_session_lock(str(session_id))

    async with lock:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )

        session = result.scalar_one_or_none()

        if not session:
            lock.release()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found.",
            )

        checkpointer = request.app.state.checkpointer
        await checkpointer.adelete_thread(thread_id_for(session_id))

        await db.delete(session)
        await db.commit()

    return None