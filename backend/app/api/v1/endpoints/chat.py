import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse


load_dotenv()
router = APIRouter()


def intialize_llm() -> None:
    llm = ChatOpenAI(
        model="minimax/minimax-m3:free",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY_JAY009294"),
        streaming=True)
