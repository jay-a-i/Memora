"""
Client-safe error text.

Exception text from the driver and the filesystem embeds the DSN, the hostname,
and absolute paths. It reaches API clients through two routes:
`Document.error_message` (returned by the documents endpoints and by the
`metadata_filter` tool) and the chat SSE stream. These tests pin the boundary.
"""

import pytest
from sqlalchemy.exc import OperationalError

from backend.app.core.errors import SafeError, client_message

# A realistic asyncpg failure: the message names the host, the port, and the
# credentials, which is exactly what must not cross the boundary.
DSN_LEAK = (
    'connection to server at "db.internal.corp" (10.0.0.7), port 5432 failed: '
    'password authentication failed for user "memora"'
)


def test_database_errors_do_not_leak_the_dsn():
    exc = OperationalError("SELECT 1", {}, Exception(DSN_LEAK))
    message = client_message(exc)
    assert DSN_LEAK not in message
    assert "db.internal.corp" not in message
    assert "memora" not in message
    assert "10.0.0.7" not in message


def test_filesystem_errors_do_not_leak_the_path():
    exc = OSError(f"cannot write to C:\\Users\\someone\\memora\\temp_uploads\\a.md")
    message = client_message(exc)
    assert "temp_uploads" not in message
    assert "cannot write to" not in message


@pytest.mark.parametrize(
    "exc",
    [
        PermissionError(13, "Permission denied"),
        FileNotFoundError(2, "No such file"),
        ValueError("something unexpected"),
        RuntimeError("pool exhausted"),
        KeyError("missing"),
    ],
)
def test_unrecognized_errors_collapse_to_a_generic_message(exc):
    """
    Anything not explicitly recognized must fall through to the generic string.

    This is the property that stops a new failure mode from starting to leak by
    omission: there is no branch that returns str(exc).
    """
    message = client_message(exc)
    assert str(exc) not in message or not str(exc)
    assert "An internal error occurred" in message or "server" in message.lower()


def test_safe_errors_pass_through():
    """Conditions a person can act on keep their explanation."""
    exc = SafeError("Unsupported file format: .exe")
    assert client_message(exc) == "Unsupported file format: .exe"


def test_embedding_failures_name_the_cause_without_the_request():
    from backend.app.core.errors import EmbeddingError

    exc = EmbeddingError(
        "Embedding request failed for batch 2/5 using 'embed-v5.0-pro': "
        "401 Unauthorized for url https://api.cohere.com/v2/embed"
    )
    message = client_message(exc)
    assert "cohere.com" not in message
    assert "401" not in message
    assert "embed" in message.lower()


def test_embedding_batch_number_is_not_forwarded():
    """Batch counts are internal bookkeeping, not something a user acts on."""
    from backend.app.core.errors import EmbeddingError

    exc = EmbeddingError("Embedding request failed for batch 37/90 using 'x'")
    assert "37" not in client_message(exc)
    assert "90" not in client_message(exc)


def test_dimension_mismatch_is_an_embedding_error():
    """
    The mismatch message tells the operator exactly what to change, so it must
    stay in the log — but it is a provider-shaped string, so it cannot be a
    SafeError, or it would be returned verbatim.
    """
    from backend.app.core.errors import EmbeddingError, client_message as to_client

    from backend.app.services.embeddingV2 import _validate

    with pytest.raises(EmbeddingError) as exc:
        _validate([[0.0] * 768], 1536)

    assert "768" in str(exc.value)
    assert "vector(1536)" in str(exc.value)
    assert "1536" in to_client(exc.value) or "EMBEDDING_DIMENSIONS" in to_client(exc.value)


def test_tool_failure_message_is_sanitized_for_the_model():
    """
    A tool error is returned to the model as a normal result, and the model can
    repeat it to the user.
    """
    import inspect

    from backend.app.agent.orchestrator import tool_executor

    source = inspect.getsource(tool_executor)
    assert "client_message(e)" in source
    assert 'f"Error executing {tool_name}: {e}"' not in source


def test_log_and_client_message_logs_the_detail(caplog):
    """The traceback must still reach the log — that is where it is useful."""
    from backend.app.core.errors import log_and_client_message

    with caplog.at_level("ERROR"):
        message = log_and_client_message(OSError(DSN_LEAK), "Upload failed")

    assert DSN_LEAK in caplog.text
    assert DSN_LEAK not in message