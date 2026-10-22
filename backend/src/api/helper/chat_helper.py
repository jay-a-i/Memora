import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from backend.src.db.models.chat import ChatMessage
from backend.src.schemas.chat_schemas import MessageRole


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
