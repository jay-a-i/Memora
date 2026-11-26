import json
import logging
import uuid
import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    Request, 
    status, 
    Query
)
from fastapi.responses import StreamingResponse

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.errors import GraphRecursionError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

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
    Extract the completed assistant answer belonging to one logical turn.

    Never inspect messages belonging to subsequent turns.
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

    end_index = len(messages)

    # Stop when the next user turn begins.
    for index in range(turn_index + 1, len(messages)):
        if isinstance(messages[index], HumanMessage):
            end_index = index
            break

    turn_messages = messages[turn_index + 1:end_index]

    last_assistant_message = next(
        (
            message
            for message in reversed(turn_messages)
            if isinstance(message, AIMessage)
        ),
        None,
    )

    if last_assistant_message is None:
        return None

    # An assistant message with outstanding tool calls isn't a final answer.
    if last_assistant_message.tool_calls:
        return None

    answer = _content_as_text(last_assistant_message.content)

    return answer or None


async def _load_history_page(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 50,
    before_seq: int | None = None,
) -> tuple[list[ChatMessage], int | None]:

    limit = max(1, min(int(limit), 100))

    stmt = select(ChatMessage).where(
        ChatMessage.session_id == session_id
    )

    if before_seq is not None:
        stmt = stmt.where(ChatMessage.seq < before_seq)

    stmt = stmt.order_by(ChatMessage.seq.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > limit

    rows = rows[:limit]
    rows.reverse()

    next_before_seq = rows[0].seq if has_more and rows else None

    return rows, next_before_seq


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


async def _find_oldest_unfinished_user_turn(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> ChatMessage | None:
    """
    Finds the oldest user message that has no corresponding assistant
    response in the same session.

    A logical turn is identified by:
        session_id + turn_id

    The assistant response must use the same turn_id.
    """

    assistant = aliased(ChatMessage)

    assistant_exists = (
        select(1)
        .select_from(assistant)
        .where(
            assistant.session_id == ChatMessage.session_id,
            assistant.turn_id == ChatMessage.turn_id,
            assistant.role == MessageRole.ASSISTANT.value,
        )
        .exists()
    )

    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == MessageRole.USER.value,
            ~assistant_exists,
        )
        .order_by(ChatMessage.seq.asc())
        .limit(1)
    )

    result = await db.execute(stmt)

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


_session_locks: dict[str, asyncio.Lock] = {}
def get_session_lock(session_id: str) -> asyncio.Lock:
    """
    Return the lock associated with one conversation.

    This coordinates requests within one backend process.
    """
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
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{payload.session_id}' is not a valid session UUID.",
        )

    session_lock = get_session_lock(str(session_uuid))
    await session_lock.acquire()

    lock_transferred_to_stream = False

    try:
        if not payload.messages or not payload.messages[-1].content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The messages input cannot be empty",
            )

        if payload.messages[-1].role != MessageRole.USER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The final message must have the user role.",
            )

        user_msg = payload.messages[-1].content


        result = await db_session.execute(
            select(ChatSession).where(ChatSession.id == session_uuid)
        )

        session = result.scalar_one_or_none()

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found."
            )

        graph = getattr(request.app.state, "graph", None)

        if graph is None:
            logger.warning("The Graph is Unvailable.")
            
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The Agent is unvailable. Please try shortly.",
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

        pending_turn = await _find_oldest_unfinished_user_turn(
            db_session,
            session_uuid,
        )

        if (
            pending_turn is not None
            and pending_turn.turn_id != payload.turn_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A previous conversation turn is unfinished. "
                    "Retry that turn before submitting a new question."
                ),
            )

        graph_input = None
        resume_existing_run = False
        replay_answer: str | None = None

        if existing_user is not None:
            # Reusing a turn ID with different content is invalid.
            if existing_user.content != user_msg:
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
            current_parts: list[str] = []

            try:
                if replay_answer is not None:
                    if replay_answer:
                        yield _sse({
                            "type": "chunk",
                            "content": replay_answer,
                        })

                    yield _sse({"type": "done", "session_id": str(session_uuid),})
                    yield "data: [DONE]\n\n"
                    return

                stream_input = None if resume_existing_run else graph_input

                async with aclosing(
                    graph.astream(
                        stream_input,
                        config=config,
                        context=run_context,
                        stream_mode=["messages", "custom"],
                    )
                ) as graph_stream:
                    
                    async for mode, item in graph_stream:

                        if mode == "custom":

                            if not isinstance(item, dict):
                                continue
                            event_type = item.get("type")

                            if event_type == "tool_start":
                                current_parts = []

                            if event_type == "tool_end":
                                current_parts = []

                            if event_type in {
                                "tool_start", 
                                "tool_end", 
                                "sources"
                            }:
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

            except asyncio.CancelledError:
                # The client disconnected or execution was cancelled.
                await db_session.rollback()

                logger.info(
                    "Chat stream cancelled for session %s, turn %s",
                    session_uuid,
                    payload.turn_id,
                )
                raise

            except GraphRecursionError:
                await db_session.rollback()

                yield _sse({
                    "type": "error",
                    "message": (
                        "The agent reached its execution-step limit. "
                        "Retry this turn to resume the unfinished execution."
                    ),
                })

                yield "data: [DONE]\n\n"
                
            except Exception as e:
                await db_session.rollback()
                yield _sse(
                    {"type": "error", "message": log_and_client_message(e, "Chat stream failed")}
                )
                yield "data: [DONE]\n\n"

            finally:
                session_lock.release()
            
        response = StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

        lock_transferred_to_stream = True
        return response

    finally:
        if not lock_transferred_to_stream:
            session_lock.release()       


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
    summary="Fetch a page of session history",
)
async def get_session_history(
    session_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before_seq: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )

    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    messages, next_cursor = await _load_history_page(
        db,
        session_id,
        limit,
        before_seq,
    )

    return ChatHistoryResponseSchema(
        session_id=session_id,
        messages=[
            ChatMessageSchema(
                role=m.role,
                content=m.content,
                turn_id=m.turn_id,
            )
            for m in messages
        ],
        next_before_seq=next_cursor,
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {session_id} not found.",
            )

        checkpointer = request.app.state.checkpointer
        await checkpointer.adelete_thread(thread_id_for(session_id))

        await db.delete(session)
        await db.commit()

    return None