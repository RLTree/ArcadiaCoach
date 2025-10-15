from __future__ import annotations

import sys
import types

import pytest


class _ConfigStub:
    def __init__(self, config_file: str | None = None) -> None:
        self.config_file_name = config_file
        self._options: dict[str, str] = {}

    def set_main_option(self, key: str, value: str) -> None:
        self._options[key] = value

    def get_main_option(self, key: str) -> str:
        return self._options.get(key, "")


_alembic = types.ModuleType("alembic")
_command = types.ModuleType("alembic.command")
_config = types.ModuleType("alembic.config")
_command.upgrade = lambda config, revision: None  # type: ignore[assignment]
_config.Config = _ConfigStub  # type: ignore[attr-defined]
_alembic.command = _command  # type: ignore[attr-defined]
_alembic.config = _config  # type: ignore[attr-defined]
sys.modules["alembic"] = _alembic
sys.modules["alembic.command"] = _command
sys.modules["alembic.config"] = _config

from scripts import run_migrations as runner  # noqa: E402


class DummyConfig(_ConfigStub):
    pass


def _load_test_config(monkeypatch) -> DummyConfig:
    monkeypatch.setenv("ARCADIA_DATABASE_URL", "sqlite://")
    config = DummyConfig()
    config.set_main_option("sqlalchemy.url", "%(ARCADIA_DATABASE_URL)s")
    config.set_main_option("script_location", "alembic")
    return config


def test_resolve_database_url_prefers_env(monkeypatch) -> None:
    config = DummyConfig()
    config.set_main_option("sqlalchemy.url", "%(ARCADIA_DATABASE_URL)s")
    monkeypatch.setenv("ARCADIA_DATABASE_URL", "sqlite://")
    assert runner.resolve_database_url(config) == "sqlite://"


def test_wait_for_database_succeeds_with_sqlite(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"
    url = f"sqlite:///{db_path}"
    runner.wait_for_database(url, timeout=2, poll_interval=0.1)


def test_wait_for_database_times_out(monkeypatch) -> None:
    class DummyEngine:
        def connect(self) -> types.SimpleNamespace:
            raise runner.OperationalError("SELECT 1", {}, Exception("boom"))

        def dispose(self) -> None:
            pass

    monkeypatch.setattr(runner, "create_engine", lambda *_, **__: DummyEngine())
    with pytest.raises(RuntimeError):
        runner.wait_for_database("postgresql://example", timeout=0, poll_interval=0)


def test_run_migrations_invokes_upgrade(monkeypatch) -> None:
    config = _load_test_config(monkeypatch)

    recorded: dict[str, object] = {}

    def fake_wait(url: str, *, timeout: int, poll_interval: float) -> None:
        recorded["wait"] = (url, timeout, poll_interval)

    def fake_upgrade(cfg, revision: str) -> None:
        recorded["revision"] = revision
        recorded["config_script_location"] = cfg.get_main_option("script_location")

    monkeypatch.setattr(runner, "wait_for_database", fake_wait)
    monkeypatch.setattr(runner.command, "upgrade", fake_upgrade)

    runner.run_migrations("head", timeout=5, poll_interval=0.1, config=config)

    assert recorded["revision"] == "head"
    assert recorded["wait"][0].startswith("sqlite://")
    assert recorded["config_script_location"] is not None
