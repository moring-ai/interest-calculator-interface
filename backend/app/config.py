"""Runtime configuration, all overridable by environment variable."""

from __future__ import annotations

import os
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

    # --- AICP governed Agent API ----------------------------------------
    #: Full invoke URL for an agent hosted on the platform, e.g.
    #: https://demo.aicp.moring.ai/api/v1/agents/calc-interest-agent/invoke
    #:
    #: Preferred over the LiteLLM route when set. A platform-hosted runtime is
    #: locked to a JWT authorizer, so the SigV4 signing that LiteLLM's
    #: bedrock/agentcore route performs is refused outright -- the platform
    #: authenticates the caller, checks per-agent authorization, and signs the
    #: AgentCore call itself. Nothing here ever holds AWS credentials.
    aicp_agent_url: str = ""
    #: Keycloak access token for the platform account. Same identity used to
    #: sign in to the dashboard.
    aicp_access_token: str = ""

    @property
    def aicp_token_url(self) -> str:
        """Where to mint an agent-scoped bearer.

        Derived from the invoke URL so only one value has to be configured;
        the platform exposes /token and /invoke as siblings on the same agent.
        """
        explicit = os.environ.get("AICP_TOKEN_URL", "").strip()
        if explicit:
            return explicit
        return self.aicp_agent_url.rstrip("/").removesuffix("/invoke") + "/token"

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
    def uses_aicp(self) -> bool:
        return bool(self.aicp_agent_url)

    @property
    def agent_configured(self) -> bool:
        if self.uses_aicp:
            return bool(self.aicp_access_token)
        return bool(self.litellm_base_url and self.agent_model)

    @property
    def tools_configured(self) -> bool:
        return bool(self.mcp_server_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
