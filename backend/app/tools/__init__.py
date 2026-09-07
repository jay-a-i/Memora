from app.tools.web_search import execute_web_search, WEB_SEARCH_SCHEMA


TOOL_SCHEMAS = [
    WEB_SEARCH_SCHEMA
]

TOOLS_MAP = {
    "web_search": execute_web_search,
}