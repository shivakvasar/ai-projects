"""Unit tests for BOSS/exception_alert.py.

Only the local, non-API helpers are exercised here (loading/filtering job rows,
and stripping markdown fences from a would-be Claude reply). No live Claude API
calls are made, matching the rest of the BOSS test suite.
"""

from importlib import util
from pathlib import Path

import pandas as pd
import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "exception_alert.py"
Spec = util.spec_from_file_location("exception_alert", MODULE_PATH)
exception_alert = util.module_from_spec(Spec)
Spec.loader.exec_module(exception_alert)


@pytest.fixture
def job_csv(tmp_path):
    """A small incoming/-style CSV with two customers, one of them repeated."""
    csv_dir = tmp_path / "incoming"
    csv_dir.mkdir()
    df = pd.DataFrame(
        [
            {"client_name": "Acme Facilities", "job_ref": "JOB-0001", "amount_due": "100.00"},
            {"client_name": "Acme Facilities", "job_ref": "JOB-0002", "amount_due": "9999.00"},
            {"client_name": "Other Corp", "job_ref": "JOB-0003", "amount_due": "50.00"},
        ]
    )
    df.to_csv(csv_dir / "sample.csv", index=False)
    return csv_dir


def test_load_customer_jobs_matches_case_insensitively(job_csv):
    jobs = exception_alert.load_customer_jobs("acme", search_dirs=[str(job_csv)])

    assert len(jobs) == 2
    assert all(j["client_name"] == "Acme Facilities" for j in jobs)
    assert all(j["source_file"] for j in jobs)  # traceability field is populated


def test_load_customer_jobs_no_match_returns_empty_list(job_csv):
    jobs = exception_alert.load_customer_jobs("Nonexistent Customer", search_dirs=[str(job_csv)])

    assert jobs == []


def test_load_customer_jobs_skips_csv_without_client_name_column(tmp_path):
    csv_dir = tmp_path / "incoming"
    csv_dir.mkdir()
    pd.DataFrame([{"unrelated_column": "value"}]).to_csv(csv_dir / "not_jobs.csv", index=False)

    jobs = exception_alert.load_customer_jobs("Acme", search_dirs=[str(csv_dir)])

    assert jobs == []


def test_clean_response_strips_json_code_fence():
    raw = '```json\n{"status": "clear", "anomalies": []}\n```'

    assert exception_alert.clean_response(raw) == '{"status": "clear", "anomalies": []}'


def test_clean_response_passes_through_plain_json():
    raw = '{"status": "clear", "anomalies": []}'

    assert exception_alert.clean_response(raw) == raw


def test_build_alert_skips_api_call_when_no_jobs_found(monkeypatch):
    """build_alert must not touch the network when there are no matching job rows."""
    monkeypatch.setattr(exception_alert, "load_customer_jobs", lambda customer_name: [])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("check_anomalies should not be called when there are no jobs")

    monkeypatch.setattr(exception_alert, "check_anomalies", fail_if_called)

    alert = exception_alert.build_alert("Nobody", "general")

    assert alert["status"] == "no_data"
    assert alert["jobs_checked"] == 0
