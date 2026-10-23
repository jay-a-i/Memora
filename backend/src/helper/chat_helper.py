import uuid
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.db.models.chat import ChatMessage
from src.schemas.chat_schemas import MessageRole
from src.db.models import ChatSession


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