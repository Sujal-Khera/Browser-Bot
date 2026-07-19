"""
tests/test_cli_doctor.py — Tests for `python -m browserbot doctor` environment diagnostics command.

Run:
    python -m pytest tests/test_cli_doctor.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from browserbot.cli.doctor import DoctorReport, run_doctor


def test_doctor_runs_all_checks_healthy() -> None:
    """Verify that run_doctor executes and returns a report when all checks pass."""
    with patch("browserbot.cli.doctor.check_ollama", return_value=None), \
         patch("browserbot.cli.doctor.check_playwright_chromium", return_value=None):
        report = run_doctor(skip_ollama=True)
        assert isinstance(report, DoctorReport)
        assert report.total_checks > 0
        assert report.all_passed is True


def test_doctor_handles_python_version_failure() -> None:
    """Verify that run_doctor reports failure when Python version is insufficient."""
    with patch("sys.version_info", (3, 9, 0)):
        report = run_doctor(skip_ollama=True)
        assert report.all_passed is False
        assert any(c.name == "Python Version" and c.status == "FAIL" for c in report.checks)


def test_doctor_handles_missing_dependency() -> None:
    """Verify missing dependency detection and actionable recommendation generation."""
    report = DoctorReport()
    with patch("importlib.import_module", side_effect=ImportError("No module named 'fake_module'")):
        from browserbot.cli.doctor import check_imports
        check_imports(report)
        assert report.all_passed is False
        assert any("fake_module" in c.message and c.status == "FAIL" for c in report.checks)


def test_doctor_json_output(capsys) -> None:
    """Verify that --json mode outputs valid structured JSON."""
    report = run_doctor(skip_ollama=True, json_output=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "total_checks" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)


def test_doctor_server_health_check_online() -> None:
    """Verify server health check when server is running and returns 200."""
    report = DoctorReport()
    mock_res = MagicMock()
    mock_res.status = 200
    mock_res.__enter__.return_value = mock_res
    with patch("urllib.request.urlopen", return_value=mock_res):
        from browserbot.cli.doctor import check_server_health
        check_server_health(report)
        assert any(c.name == "Orchestration Server" and c.status == "OK" for c in report.checks)


def test_doctor_server_health_check_offline() -> None:
    """Verify server health check when server is offline returns a WARN with recommendation."""
    report = DoctorReport()
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        from browserbot.cli.doctor import check_server_health
        check_server_health(report)
        assert any(c.name == "Orchestration Server" and c.status == "WARN" for c in report.checks)
        warn_item = [c for c in report.checks if c.name == "Orchestration Server"][0]
        assert warn_item.recommendation is not None
        assert "python -m browserbot server" in warn_item.recommendation
