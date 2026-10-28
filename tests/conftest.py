import pytest

from skylinee_harness.agent import AgentEngine
from skylinee_harness.audit import AuditLogger
from skylinee_harness.config import Settings
from skylinee_harness.store import Store


@pytest.fixture
def engine(tmp_path):
    settings = Settings(
        _env_file=None,
        api_key="a" * 40,
        data_dir=tmp_path / "data",
        workspace_dir=tmp_path / "workspace",
        audit_log_path=tmp_path / "audit.jsonl",
        scheduler_poll_seconds=0.1,
    )
    store = Store(settings.data_dir / "state.sqlite3")
    e = AgentEngine(settings, store, AuditLogger(settings.audit_log_path))

    async def doctor():
        return {"tools_supported": True}

    e.doctor = doctor
    yield e
    store.close()
