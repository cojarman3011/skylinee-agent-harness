from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SKYLINEE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Skylinee Agent Harness"
    ollama_base_url: str = "http://127.0.0.1:11434"
    api_key: str = ""
    model_general: str = "qwen2.5:1.5b"
    model_code: str = "deepseek-coder:1.3b"
    model_security: str = "qwen2.5:1.5b"
    request_timeout_seconds: float = Field(default=180, gt=0)
    audit_log_path: Path = Path("data/audit.jsonl")
    log_prompt_content: bool = False
    model_agent: str = "qwen3:4b"
    data_dir: Path = Path("data")
    workspace_dir: Path = Path("workspace")
    searxng_url: str = ""
    enable_terminal: bool = False
    terminal_allowlist: str = "python3,git,ls,pwd"
    max_agent_steps: int = Field(default=12, ge=1, le=40)
    max_tool_chars: int = Field(default=16000, ge=1000, le=100000)
    agent_timeout_seconds: float = Field(default=300, gt=0, le=1800)
    scheduler_poll_seconds: float = Field(default=1, ge=0.1, le=60)

    @property
    def model_map(self) -> dict[str, str]:
        return {
            "general": self.model_general,
            "code": self.model_code,
            "security": self.model_security,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
