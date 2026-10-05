# backend/app/tools/web_search.py

import asyncio
import logging

from tavily import TavilyClient

from backend.app.core.config import settings
from backend.app.core.errors import client_message

logger = logging.getLogger(__name__)

WEB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "A tool that searches the live internet for up-to-date information, real-time news, current facts, "
            "and specific web references. Use this tool whenever the user asks a question about recent events, "
            "temporal data, or information outside of your static training cutoff knowledge limit. Always query "
            "using concise keywords rather than conversational sentences."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The specific keyword-based search query."
                }
            },
            "required": ["query"],
        },
    },
}

tavily_client = (
    TavilyClient(api_key=settings.TAVILY_API_KEY) if settings.TAVILY_API_KEY else None
)

MAX_RESULTS = 5
MAX_CONTENT_CHARS = 1500  # Raw page text is truncated to bound context growth.


async def execute_web_search(query: str, **kwargs) -> dict:
    """
    Executes a web search asynchronously using Tavily.
    Accepts **kwargs to safely ingest unneeded parameters like db_session.
    """
    if not query or not query.strip():
        return {"error": "Search query was empty."}

    if not tavily_client:
        return {
            "error": (
                "The 'web_search' tool is unavailable: TAVILY_API_KEY is not set. "
                "Answer from the knowledge base instead."
            )
        }

    try:
        response = await asyncio.to_thread(
            tavily_client.search,
            query=query,
            search_depth="basic",
            max_results=MAX_RESULTS,
        )

        results = []
        for item in response.get("results", []):
            content = (item.get("content") or "")[:MAX_CONTENT_CHARS]
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": content,
                }
            )

        if not results:
            return {"query": query, "results": [], "note": "No results found."}

        return {"query": query, "results": results}

    except Exception as e:
        logger.exception("Web search failed")
        return {"error": f"Failed to execute web search: {client_message(e)}"}