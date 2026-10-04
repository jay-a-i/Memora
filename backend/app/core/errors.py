# backend/app/core/errors.py

"""
Turning internal failures into text that is safe to hand to a client.

Exceptions raised deep in the stack carry text that was written for a developer,
not a user: an asyncpg connection error embeds the DSN and the server hostname, a
filesystem error embeds an absolute path, and a provider error can echo back the
request that produced it. That text ends up in two places an API-key holder can
read it — `Document.error_message`, which the documents endpoints and the
`metadata_filter` tool both return, and the chat SSE stream.

So the rule is: the full detail goes to the log, and only an authored message
crosses the boundary. Code that wants to explain itself to a user raises
`SafeError`; everything else is collapsed by category.
"""

import logging

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class SafeError(Exception):
    """
    An error whose message was written for the user and may be returned as-is.

    Raise this for conditions a person can act on — an unsupported upload
    format, a document with no extractable text. Do not raise it with text that
    came from a library or a provider.
    """


class EmbeddingError(Exception):
    """
    The embedding provider rejected a request, or returned unusable vectors.

    Its message quotes the provider, so it is operator-facing only: the client
    gets the hint below. This is a distinct type rather than a `SafeError`
    precisely so the provider text cannot be returned by mistake.
    """


# Messages for failures nobody can act on. They say what broke without saying
# where, so a client learns nothing about the host's filesystem or topology.
_GENERIC = "An internal error occurred while processing this request."

_BY_CATEGORY = {
    PermissionError: "The server could not access the files it needs to complete this request.",
    FileNotFoundError: "The server could not find a file it needs to complete this request.",
    OSError: "The server could not read or write a file needed for this request.",
    SQLAlchemyError: "The request could not be completed because of a database error.",
}

# An embedding failure is the most common one by far, and it usually means a
# configuration problem rather than a transient fault.
_EMBEDDING_HINT = (
    "The document could not be embedded. Check that the embedding provider is "
    "reachable and that EMBEDDING_MODEL and EMBEDDING_DIMENSIONS are valid."
)


def client_message(exc: BaseException) -> str:
    """
    Returns text describing `exc` that is safe to persist or return to a client.

    Anything not recognized collapses to a generic string rather than falling
    through to `str(exc)`, so a new failure mode cannot start leaking by
    omission.
    """
    if isinstance(exc, SafeError):
        return str(exc)

    if isinstance(exc, EmbeddingError):
        return _EMBEDDING_HINT

    for exc_type, message in _BY_CATEGORY.items():
        if isinstance(exc, exc_type):
            return message

    return _GENERIC


def log_and_client_message(exc: BaseException, context: str) -> str:
    """
    Records `exc` with its full detail and returns the client-safe summary.

    The traceback, and therefore the DSN or path, stays in the server log where
    it is useful; the caller gets a message that carries no host detail.
    """
    logger.exception("%s: %s", context, exc)
    return client_message(exc)