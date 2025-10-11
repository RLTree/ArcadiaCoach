import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    arcadia_mcp_url: str = Field("http://127.0.0.1:8001/mcp", alias="ARCADIA_MCP_URL")
    arcadia_mcp_label: str = Field("Arcadia_Coach_Widgets", alias="ARCADIA_MCP_LABEL")
    arcadia_mcp_require_approval: str = Field("never", alias="ARCADIA_MCP_REQUIRE_APPROVAL")

    class Config:
        env_file = os.getenv("ENV_FILE", ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
