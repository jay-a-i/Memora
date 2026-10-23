from langchain_core.messages import AIMessage, HumanMessage

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