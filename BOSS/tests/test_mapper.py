"""Unit tests for BOSS/mapper_agent.py.

These tests exercise the local tooling layer used by the Claude agent loop.
They do not call Claude itself; instead, they validate the helper functions and
error handling around the agent tool interface.
"""

from importlib import util
from pathlib import Path

import pytest


# Load mapper_agent.py directly from the BOSS package directory.
# This allows us to import the module even though this test file lives in a
# nested tests/ directory under BOSS.
MODULE_PATH = Path(__file__).resolve().parents[1] / "mapper_agent.py"
Spec = util.spec_from_file_location("mapper_agent", MODULE_PATH)
mapper_agent = util.module_from_spec(Spec)
Spec.loader.exec_module(mapper_agent)


def test_load_headers_happy_path():
    """Happy path: load_headers reads sample.csv and extracts headers/samples."""
    # Use the actual sample.csv shipped in BOSS so this test reflects real data.
    sample_csv = Path(__file__).resolve().parents[1] / "sample.csv"

    result = mapper_agent.load_headers(str(sample_csv))

    # The helper should succeed and return the expected header list.
    assert result["success"] is True
    assert "client_name" in result["headers"]
    assert result["headers"][0] == "client_name"

    # The sample values should preserve the first two rows from the sample file.
    assert result["samples"]["client_name"][:2] == [
        "Tan Brothers Pte Ltd",
        "City Mall Management",
    ]


def test_inspect_column_blank_header():
    """Empty header values should be passed through unchanged by inspect_column."""
    result = mapper_agent.inspect_column("", ["S1234", "S1235"])

    # The inspect_column tool is intentionally simple and should echo the input.
    assert result["success"] is True
    assert result["header"] == ""
    assert result["sample_values"] == ["S1234", "S1235"]


def test_process_tool_call_mismatched_schema_raises_key_error():
    """A tool payload with the wrong schema should fail loudly instead of being accepted."""
    # process_tool_call is expected to bubble up a KeyError when the payload does
    # not match the expected inspect_column schema (for example, wrong field name).
    with pytest.raises(KeyError):
        mapper_agent.process_tool_call(
            "inspect_column",
            {"header": "supplier_name", "sample_value": ["S1234"]},
        )


def test_process_tool_call_missing_schema_raises_key_error():
    """A tool payload missing required schema fields should raise KeyError."""
    # Missing the required sample_values field is a different failure mode from
    # a mismatched schema name, and should still be treated as invalid input.
    with pytest.raises(KeyError):
        mapper_agent.process_tool_call(
            "inspect_column",
            {"header": "supplier_name"},
        )
