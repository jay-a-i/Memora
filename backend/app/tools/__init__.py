# backend/app/tools/__init__.py

from .doc_inspector import DOC_INSPECTOR_SCHEMA, execute_doc_inspector
from .hybrid_search import HYBRID_SEARCH_SCHEMA, execute_hybrid_search
from .metadata_filter import METADATA_FILTER_SCHEMA, execute_metadata_filter
from .web_search import WEB_SEARCH_SCHEMA, execute_web_search

# Exported list of schemas for LLM tool binding
tool_schemas = [
    HYBRID_SEARCH_SCHEMA,
    DOC_INSPECTOR_SCHEMA,
    METADATA_FILTER_SCHEMA,
    WEB_SEARCH_SCHEMA,
]

# Exported dictionary mapping tool names to their async execution functions
TOOLS_MAP = {
    "hybrid_search": execute_hybrid_search,
    "doc_inspector": execute_doc_inspector,
    "metadata_filter": execute_metadata_filter,
    "web_search": execute_web_search,
}

__all__ = [
    "tool_schemas",
    "TOOLS_MAP",
    "HYBRID_SEARCH_SCHEMA",
    "DOC_INSPECTOR_SCHEMA",
    "METADATA_FILTER_SCHEMA",
    "WEB_SEARCH_SCHEMA",
    "execute_hybrid_search",
    "execute_doc_inspector",
    "execute_metadata_filter",
    "execute_web_search",
]
