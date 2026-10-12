# backend/app/v1/endpoints/chat.py

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.checkpointer import thread_id_for
from src.agent.orchestrator import get_graph
from src.agent.state import AgentContext
from src.core.config import settings
from src.core.database import get_db
from src.core.errors import log_and_client_message
from src.core.security import verify_api_hitter
from src.db.models.chat import ChatMessage, ChatSession
from src.schemas.chat_schemas import (
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

    """
    try:
        session_uuid = uuid.UUID(str(payload.session_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{payload.session_id}' is not a valid session UUID.",
        )

    if not payload.messages or not payload.messages[-1].content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The messages input cannot be empty",
        )
    
    user_msg = payload.messages[-1].content
    session = await _get_or_create_session(db_session, session_uuid)
    
    db_session.add(
        ChatMessage(session_id=session_uuid, role=MessageRole.USER.value, content=user_msg)
    )
    await db_session.commit()

    graph = getattr(request.app.state, "graph", None) or get_graph()
    graph_input: dict = {"messages": [HumanMessage(content=user_msg)]}
    config = {"configurable": {"thread_id": thread_id_for(session_uuid)}}
    run_context = AgentContext(db_session=db_session)

    async def sse_generator() -> AsyncGenerator[str, None]:
        current_parts: list[str] = []

        try:
            async for mode, item in graph.astream(
                graph_input,
                config=config,
                context=run_context,
                stream_mode=["messages", "custom"],
            ):
                if mode == "custom":
                    if isinstance(item, dict) and item.get("type") == "tool_start":
                        current_parts = []
                    if isinstance(item, dict):
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
            await db_session.rollback()
            yield _sse(
                {"type": "error", "message": log_and_client_message(e, "Chat stream failed")})
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

    messages = await _load_history(db, session_id, settings.MAX_HISTORY_MESSAGES)
    return ChatHistoryResponseSchema(
        session_id=session_id,
        messages=[
            ChatMessageSchema(role=m.role, content=m.content) for m in messages]
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