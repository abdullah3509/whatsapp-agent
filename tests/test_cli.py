"""Lean smoke tests for the whatsapp-agent CLI dispatch and its send/upload/
doctor commands against a mocked HTTP layer -- not testing argparse itself.
"""
from __future__ import annotations

import json

import pytest
import responses

from tests.conftest import BASE_URL, error_body
from whatsapp_agent.cli import main


@pytest.fixture(autouse=True)
def api_key_env(monkeypatch):
    monkeypatch.setenv("WHATSAPP_API_KEY", "test-token")


class TestSendCommand:
    @responses.activate
    def test_send_prints_result_json(self, capsys):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "wamid.1"}]},
            status=200,
        )
        exit_code = main(["send", "15551234567", "hello"])
        assert exit_code == 0
        assert json.loads(capsys.readouterr().out)["messages"][0]["id"] == "wamid.1"

    @responses.activate
    def test_send_markdown_flag_converts_body(self):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        main(["send", "15551234567", "**bold**", "--markdown"])
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["text"]["body"] == "*bold*"

    @responses.activate
    def test_send_api_error_returns_1(self, capsys):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json=error_body(131009, "Missing or malformed required fields"),
            status=400,
        )
        exit_code = main(["send", "15551234567", "hello"])
        assert exit_code == 1
        assert "error:" in capsys.readouterr().err


class TestUploadCommand:
    @responses.activate
    def test_upload_prints_media_id(self, tmp_path, capsys):
        file_path = tmp_path / "doc.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake")
        responses.add(responses.POST, f"{BASE_URL}/media", json={"id": "media-123"}, status=200)
        exit_code = main(["upload", str(file_path)])
        assert exit_code == 0
        assert capsys.readouterr().out.strip() == "media-123"


class TestDoctorCommand:
    def test_doctor_reports_missing_key(self, monkeypatch, capsys):
        monkeypatch.delenv("WHATSAPP_API_KEY", raising=False)
        exit_code = main(["doctor"])
        assert exit_code == 1
        assert "WHATSAPP_API_KEY" in capsys.readouterr().err

    @responses.activate
    def test_doctor_reports_ok(self, capsys):
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        exit_code = main(["doctor"])
        assert exit_code == 0
        assert "OK" in capsys.readouterr().out

    @responses.activate
    def test_doctor_reports_rejected_token(self, capsys):
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=error_body(190, "The Authorization header is absent or malformed"),
            status=401,
        )
        exit_code = main(["doctor"])
        assert exit_code == 1
        assert "token rejected" in capsys.readouterr().err


def test_no_command_exits_nonzero():
    with pytest.raises(SystemExit):
        main([])
