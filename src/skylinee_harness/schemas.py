from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunInput(Strict):
    prompt: str = Field(min_length=1, max_length=24000)
    session_id: str | None = None
    skill: str | None = None


class SessionInput(Strict):
    title: str = Field(default="New session", min_length=1, max_length=120)


class ApprovalInput(Strict):
    decision: Literal["approve", "deny"]


class MemoryInput(Strict):
    text: str = Field(min_length=1, max_length=8000)


class SkillInput(Strict):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    content: str = Field(min_length=1, max_length=16000)


class ScheduleInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=24000)
    interval_seconds: int = Field(ge=60, le=31536000)
    skill: str | None = None
    enabled: bool = True


class PathArgs(Strict):
    path: str = Field(default=".", max_length=500)


class WriteArgs(PathArgs):
    content: str = Field(max_length=100000)
    overwrite: bool = False


class SearchArgs(Strict):
    query: str = Field(min_length=1, max_length=500)


class FetchArgs(Strict):
    url: str = Field(min_length=1, max_length=2000)


class CalcArgs(Strict):
    expression: str = Field(min_length=1, max_length=200)


class TailArgs(PathArgs):
    lines: int = Field(default=100, ge=1, le=500)


class TerminalArgs(Strict):
    argv: list[str] = Field(min_length=1, max_length=40)
    cwd: str = Field(default=".", max_length=500)


class EmptyArgs(Strict):
    pass
