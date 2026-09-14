import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI 
from typing import AsyncGenerator
from 

load_dotenv()

llm = ChatOpenAI(
    name="",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    streaming=True)

async def chat() -> AsyncGenerator:
    while True:
        user_msg = input("YOU: ")
