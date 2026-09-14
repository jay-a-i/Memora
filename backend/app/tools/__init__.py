# backend/app/tools/__init__.py

from .web_search import WEB_SEARCH_SCHEMA, execute_web_search
from .hybrid_search import HYBRID_SEARCH_SCHEMA, execute_hybrid_search
from .doc_inspector import DOC_INSPECTOR_SCHEMA, execute_doc_inspector

# Exported list of schemas for LLM tool binding
tool_schemas = [
    WEB_SEARCH_SCHEMA,
    HYBRID_SEARCH_SCHEMA,
    DOC_INSPECTOR_SCHEMA,
]

# Exported dictionary mapping tool names to their async execution functions
TOOLS_MAP = {
    "web_search": execute_web_search,
    "hybrid_search": execute_hybrid_search,
    "doc_inspector": execute_doc_inspector,
}