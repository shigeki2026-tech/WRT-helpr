# -*- coding: utf-8 -*-
import json
from pathlib import Path
from types import SimpleNamespace

import app


ROOT = Path(__file__).resolve().parents[1]


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def write_config(path: Path, enabled=True, chat_id="chat-123"):
    path.write_text(
        json.dumps({
            "enabled": enabled,
            "chat_id": chat_id,
            "chat_name": "WRT報告用チャット",
            "send_mode": "powershell_graph",
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_teams_config_example_exists():
    assert (ROOT / "config" / "teams_config.example.json").is_file()


def test_teams_config_missing_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(tmp_path / "teams_config.json"))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    config = app.load_teams_config()

    assert config["enabled"] is False
    assert config["chat_id"] == ""


def test_teams_config_reads_chat_id_from_env(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(tmp_path / "teams_config.json"))
    monkeypatch.setenv("WRT_TEAMS_CHAT_ID", "env-chat-id")

    config = app.load_teams_config()

    assert config["enabled"] is True
    assert config["chat_id"] == "env-chat-id"


def test_teams_send_disabled_without_chat_id(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    write_config(config_path, enabled=True, chat_id="")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("WRT_TEAMS_CHAT_ID", raising=False)

    assert app.is_teams_send_enabled() is False


def test_empty_message_does_not_call_subprocess(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(app.subprocess, "run", fail_run)

    result = app.send_teams_message_via_powershell("   ")

    assert result["ok"] is False
    assert "本文が空" in result["message"]


def test_send_teams_message_success(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    script_path = tmp_path / "send_teams_message.ps1"
    write_config(config_path)
    script_path.write_text("# test script", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    def fake_run(args, capture_output, text, timeout):
        message_file = Path(args[-1])
        assert message_file.read_text(encoding="utf-8") == "hello teams"
        return SimpleNamespace(returncode=0, stdout="SUCCESS message-001\n", stderr="")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    result = app.send_teams_message_via_powershell("hello teams")

    assert result["ok"] is True
    assert result["message"] == "送信成功"


def test_send_teams_message_failure(monkeypatch, tmp_path):
    config_path = tmp_path / "teams_config.json"
    script_path = tmp_path / "send_teams_message.ps1"
    write_config(config_path)
    script_path.write_text("# test script", encoding="utf-8")
    monkeypatch.setattr(app, "TEAMS_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(app, "TEAMS_SEND_SCRIPT_PATH", str(script_path))

    def fake_run(args, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="ERROR denied\n", stderr="denied")

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    result = app.send_teams_message_via_powershell("hello teams")

    assert result["ok"] is False
    assert "送信失敗" in result["message"]
    assert result["stderr"] == "denied"


def test_teams_send_log_includes_preview(monkeypatch):
    original_session_state = app.st.session_state
    try:
        app.st.session_state = SessionState()
        logs = app.append_teams_send_log(
            {"ok": False, "message": "送信失敗: denied"},
            "0123456789" * 12,
            "WRT報告用チャット",
        )
    finally:
        app.st.session_state = original_session_state

    assert logs[0]["ok"] is False
    assert logs[0]["chat_name"] == "WRT報告用チャット"
    assert logs[0]["message_preview"] == "0123456789" * 10
    assert logs[0]["error_message"] == "送信失敗: denied"
