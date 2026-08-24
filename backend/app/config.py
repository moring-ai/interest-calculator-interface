"""Runtime configuration, all overridable by environment variable."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Interest Calculator API"
    debug: bool = False

    cors_origins: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ]

    # --- LiteLLM gateway -------------------------------------------------
    #: Base URL of the LiteLLM proxy. Inside docker-compose this is the service
    #: name; running the API on the host it is localhost.
    litellm_base_url: str = "http://localhost:4000"
    #: Virtual key issued by the proxy. Not an AWS credential -- the proxy holds
    #: those, which is the point of routing through it.
    litellm_api_key: str = "sk-interest-local"
    #: Must match a `model_name` in litellm/config.yaml.
    agent_model: str = "interest-agent"
    agent_timeout_seconds: int = 180

    # --- MCP tool server -------------------------------------------------
    #: The ToolHive-hosted MCP endpoint. Empty disables the calculator routes.
    mcp_server_url: str = ""
    mcp_server_token: str = ""
    mcp_timeout_seconds: int = 60

    @property
    def agent_configured(self) -> bool:
        return bool(self.litellm_base_url and self.agent_model)

    @property
    def tools_configured(self) -> bool:
        return bool(self.mcp_server_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
