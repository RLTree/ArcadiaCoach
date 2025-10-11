import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: Optional[str] = Field(None, alias="OPENAI_API_KEY")
    arcadia_mcp_url: str = Field("http://127.0.0.1:8001/mcp", alias="ARCADIA_MCP_URL")
    arcadia_mcp_label: str = Field("Arcadia_Coach_Widgets", alias="ARCADIA_MCP_LABEL")
    arcadia_mcp_require_approval: str = Field("never", alias="ARCADIA_MCP_REQUIRE_APPROVAL")
    debug_endpoints: bool = Field(False, alias="ARCADIA_DEBUG_ENDPOINTS")
    arcadia_agent_model: str = Field("gpt-5", alias="ARCADIA_AGENT_MODEL")
    arcadia_agent_reasoning: str = Field("medium", alias="ARCADIA_AGENT_REASONING")
    arcadia_agent_enable_web: bool = Field(False, alias="ARCADIA_AGENT_ENABLE_WEB")

    class Config:
        env_file = os.getenv("ENV_FILE", ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    try:
        settings = Settings()  # type: ignore[arg-type]
        if settings.openai_api_key and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        return settings
    except ValidationError as exc:
        raise RuntimeError(f"Invalid backend configuration: {exc}") from exc
