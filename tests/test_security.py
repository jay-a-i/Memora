"""API key verification."""

import pytest

from backend.src.core.security import verify_api_hitter


async def test_valid_key_is_accepted():
    assert await verify_api_hitter("test-secret") == "test-secret"


@pytest.mark.parametrize("bad", [None, "", "wrong", "test-secre", "test-secretx"])
async def test_invalid_key_is_rejected(bad):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await verify_api_hitter(bad)
    assert exc.value.status_code == 401


async def test_missing_key_is_401_not_500():
    # auto_error=False means FastAPI no longer raises its own 403 first.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await verify_api_hitter(None)
    assert exc.value.status_code == 401
