import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    workflow_id: str = Field(..., alias="CHATKIT_WORKFLOW_ID")
    session_ttl_minutes: int = Field(30, alias="CHATKIT_SESSION_TTL_MINUTES")

    class Config:
        env_file = os.getenv("ENV_FILE", ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
