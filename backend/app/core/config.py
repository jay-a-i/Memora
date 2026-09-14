# backend/app/core/config.py

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

"""
   Configurations class for the whole project.
"""

class Settings(BaseSettings):

    PROJECT_NAME: str = "MEMORA"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    DATABASE_URL: str 
    DB_ECHO: bool = True #Log Updates in terminal if True.
    
    OPENROUTER_API_KEY: str #One API Key for all LLMs
    TAVILY_API_KEY: str #API key required for web_search tool 

    APP_SECURITY_KEY: str #KEY required to access any api endpoints.

    model_config = SettingsConfigDict(
            env_file=".env",
            extra="ignore"
    )

"""
 Global Singleton.
"""
settings = Settings()