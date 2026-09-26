# backend/app/v1/endpoints/chat.py

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage

from app.agents.orchestrator import graph
from app.core.database import get_db 
from app.core.security import verify_api_hitter
from schemas.chat_schemas import ChatRequestSchema


router = APIRouter()


@router.post("/stream")
async def chat_stream(
    request: ChatRequestSchema,
    db_session = Depends(get_db),
    _oauth: str = Depends(verify_api_hitter)
):

    """
    Streams the agent's response token-by-token using Server-Sent Events (SSE).
    """
    formatted_messages = []
    for msg in request.messages:
        if msg.role == "user":
            formatted_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            formatted_messages.append(AIMessage(content=msg.content))
        else:
            raise HTTPException(status_code=400, detail=f"Invalid role: {msg.role}")

    config = {
        "configurable": {
            "db_session": db_session,
            "thread_id": request.session_id # LangGraph uses this for memory tracking
        }
    }
    async def sse_generator():
        try:
            # astream_events (v2) tracks internal tool calls and LLM streams natively
            async for event in graph.astream_events(
                {"messages": formatted_messages}, 
                config=config, 
                version="v2"
            ):
                kind = event["event"]
                
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        yield f"data: {json.dumps({'chunk': content})}\n\n"
                        
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'status': f'Running {tool_name}...'})}\n\n"
                    
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")