import asyncio


_session_locks: dict[str, asyncio.Lock] = {}


def get_session_lock(session_id: str) -> asyncio.Lock:
    """
    Return the lock associated with one conversation.

    This coordinates requests within a single running backend process.
    """
    lock = _session_locks.get(session_id)

    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock

    return lock