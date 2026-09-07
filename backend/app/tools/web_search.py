import os
import asyncio
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

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

api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=api_key) if api_key else None


async def execute_web_search(query: str, **kwargs) -> dict:
    """
    Executes a web search asynchronously using Tavily.
    Accepts **kwargs to safely ingest unneeded parameters like db_session.
    """
    if not tavily_client:
        return {
            "error": "The 'web_search' tool is misconfigured. Missing TAVILY_API_KEY environment variable."
        }

    try:
        response = await asyncio.to_thread(
            tavily_client.search,
            query=query,
            search_depth="basic",
            max_results=5
        )
        
        return {
            "query": query,
            "results": response.get("results", [])
        }
    except Exception as e:
        return {
            "error": f"Failed to execute web search: {str(e)}"
        }