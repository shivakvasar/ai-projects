"""Unit tests for BOSS/mapper_agent.py.

These tests exercise the local tooling layer used by the Claude agent loop.
They do not call Claude itself; instead, they validate the helper functions and
error handling around the agent tool interface.
"""

from importlib import util
import json
import tempfile
from pathlib import Path

import pytest


# Load mapper_agent.py directly from the BOSS package directory.
MODULE_PATH = Path(__file__).resolve().parents[1] / "mapper_agent.py"
Spec = util.spec_from_file_location("mapper_agent", MODULE_PATH)
mapper_agent = util.module_from_spec(Spec)
Spec.loader.exec_module(mapper_agent)


def test_load_headers_happy_path():
    """Happy path: load_headers reads sample.csv and extracts headers/samples."""
    sample_csv = Path(__file__).resolve().parents[1] / "sample.csv"

    result = mapper_agent.load_headers(str(sample_csv))

    assert result["success"] is True
    assert "client_name" in result["headers"]
    assert result["headers"][0] == "client_name"
    assert result["samples"]["client_name"][:2] == [
        "Tan Brothers Pte Ltd",
        "City Mall Management",
    ]


def test_inspect_column_blank_header():
    """Empty header values should be passed through unchanged by inspect_column."""
    result = mapper_agent.inspect_column("", ["S1234", "S1235"])

    assert result["success"] is True
    assert result["header"] == ""
    assert result["sample_values"] == ["S1234", "S1235"]


def test_process_tool_call_mismatched_schema_raises_key_error():
    """A tool payload with the wrong schema should fail loudly instead of being accepted."""
    with pytest.raises(KeyError):
        mapper_agent.process_tool_call(
            "inspect_column",
            {"header": "supplier_name", "sample_value": ["S1234"]},
        )


def test_process_tool_call_missing_schema_raises_key_error():
    """A tool payload missing required schema fields should raise KeyError."""
    with pytest.raises(KeyError):
        mapper_agent.process_tool_call(
            "inspect_column",
            {"header": "supplier_name"},
        )


def test_load_headers_missing_file_returns_error():
    """load_headers should return a failure payload when the file does not exist."""
    result = mapper_agent.load_headers("does_not_exist.csv")

    assert result["success"] is False
    assert "error" in result
    assert "File not found" in result["error"]


def test_save_mappings_writes_file():
    """save_mappings should write JSON data to the target path successfully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = Path(tmpdir) / "mappings.json"
        payload = [
            {"source_column": "client_name", "canonical_field": "Customer", "confidence": 0.9, "sample_values": ["A"]}
        ]

        result = mapper_agent.save_mappings(str(target_file), payload)

        assert result["success"] is True
        assert target_file.exists()

        read_back = json.loads(target_file.read_text(encoding="utf-8"))
        assert read_back == payload


def test_save_mappings_creates_parent_directory():
    """save_mappings should create any missing parent directories automatically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = Path(tmpdir) / "new" / "nested" / "mappings.json"

        result = mapper_agent.save_mappings(str(target_file), [{"key": "value"}])

        assert result["success"] is True
        assert target_file.exists()
        assert json.loads(target_file.read_text(encoding="utf-8")) == [{"key": "value"}]


def test_save_mappings_unwritable_path_returns_error():
    """save_mappings should return an error when the destination is not writable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        readonly_dir = Path(tmpdir) / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)
        target_file = readonly_dir / "mappings.json"
        try:
            result = mapper_agent.save_mappings(str(target_file), [])
            assert result["success"] is False
            assert "error" in result
        finally:
            readonly_dir.chmod(0o755)


def test_process_tool_call_unknown_tool_returns_error():
    """process_tool_call should return an error payload for unsupported tools."""
    result = json.loads(mapper_agent.process_tool_call("unknown_tool", {}))

    assert "success" not in result
    assert "error" in result
    assert "Unknown tool" in result["error"]


def test_process_tool_call_load_headers_can_read_temp_csv():
    """process_tool_call should load headers from a temporary CSV file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "input.csv"
        input_file.write_text("col1,col2\n1,2\n3,4\n", encoding="utf-8")

        result = json.loads(
            mapper_agent.process_tool_call(
                "load_headers",
                {"filepath": str(input_file)},
            )
        )

    assert result["success"] is True
    assert result["headers"] == ["col1", "col2"]
    assert result["samples"]["col1"][:2] == ["1", "3"]


def test_process_tool_call_save_mappings_writes_json():
    """process_tool_call should persist mappings when save_mappings is invoked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = Path(tmpdir) / "mappings.json"
        mappings = [
            {
                "source_column": "client_name",
                "canonical_field": "Customer",
                "confidence": 0.95,
                "sample_values": ["Alice Co."],
            }
        ]

        result = json.loads(
            mapper_agent.process_tool_call(
                "save_mappings",
                {"filepath": str(target_file), "mappings": mappings},
            )
        )

        assert result["success"] is True
        assert target_file.exists()
        assert json.loads(target_file.read_text(encoding="utf-8")) == mappings


def test_resolve_filepath_finds_repo_relative_file():
    """_resolve_filepath should locate files relative to the repo root."""
    result = mapper_agent._resolve_filepath("sample.csv")

    assert result.exists()
    assert result.name == "sample.csv"


# --- Edge case tests for real-world spreadsheet robustness ---


def test_load_headers_semicolon_delimiter():
    """load_headers should handle semicolon-delimited CSVs (common in European exports)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        f.write_text("name;amount;date\nAlice;100;2024-01\nBob;200;2024-02\n", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert result["headers"] == ["name", "amount", "date"]
        assert result["samples"]["name"] == ["Alice", "Bob"]


def test_load_headers_tab_delimiter():
    """load_headers should handle tab-delimited CSVs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.tsv"
        f.write_text("customer\tinvoice\tamount\nAcme\tINV001\t500\n", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert result["headers"] == ["customer", "invoice", "amount"]


def test_load_headers_cp1252_encoding():
    """load_headers should fall back to cp1252 for Windows-encoded CSVs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        f.write_bytes("name,city\nAlice,M\xfcnchen\nBob,K\xf6ln\n".encode("cp1252"))

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert "name" in result["headers"]
        assert "city" in result["headers"]


def test_load_headers_utf8_bom():
    """load_headers should strip the UTF-8 BOM that Excel adds when saving as CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        # Write UTF-8 with BOM (utf-8-sig)
        f.write_text("customer,amount\nAlice,100\n", encoding="utf-8-sig")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        # Without BOM stripping, the first header would be "﻿customer"
        assert result["headers"][0] == "customer"


def test_load_headers_metadata_rows_at_top():
    """load_headers should skip title/report rows and find the real header row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        f.write_text(
            "Monthly Billing Report\n"
            "Generated 2024-01-15\n"
            "client_name,invoice_no,amount\n"
            "Alice Co,INV001,100\n"
            "Bob Ltd,INV002,200\n",
            encoding="utf-8",
        )

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert "client_name" in result["headers"]
        assert "Monthly Billing Report" not in result["headers"]
        assert result["samples"]["client_name"] == ["Alice Co", "Bob Ltd"]


def test_load_headers_duplicate_column_names():
    """load_headers should flag duplicate column names in the result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        f.write_text("name,amount,name\nAlice,100,Smith\nBob,200,Jones\n", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert "duplicate_headers" in result
        assert "name" in result["duplicate_headers"]
        # Renamed column should be accessible
        assert "name.1" in result["headers"]


def test_load_headers_sparse_column_reads_beyond_row_5():
    """load_headers should return samples for columns that are blank in the first few rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        # 6 rows with no data in 'notes', then a row with data
        lines = ["name,notes"] + ["Alice,"] * 6 + ["Bob,urgent review"]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert "notes" in result["headers"]
        assert result["samples"]["notes"] != []
        assert "urgent review" in result["samples"]["notes"]


def test_load_headers_xlsx_multiple_sheets():
    """load_headers should report available sheets and read the correct one."""
    pytest.importorskip("openpyxl")
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame({"summary": ["total", "count"]}).to_excel(
                writer, sheet_name="Summary", index=False
            )
            pd.DataFrame({"customer": ["Alice", "Bob"], "invoice": ["INV001", "INV002"]}).to_excel(
                writer, sheet_name="Data", index=False
            )

        # Default call reads first sheet but reports all sheets
        result = mapper_agent.load_headers(str(path))
        assert result["success"] is True
        assert "sheet_names" in result
        assert set(result["sheet_names"]) == {"Summary", "Data"}
        assert result["active_sheet"] == "Summary"

        # Re-call with the correct sheet
        result2 = mapper_agent.load_headers(str(path), sheet_name="Data")
        assert result2["success"] is True
        assert "customer" in result2["headers"]
        assert "invoice" in result2["headers"]


def test_load_headers_xlsx_single_sheet_no_sheet_names_key():
    """Single-sheet XLSX files should not include sheet_names in the result."""
    pytest.importorskip("openpyxl")
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "single.xlsx"
        pd.DataFrame({"customer": ["Alice"], "amount": [100]}).to_excel(
            path, index=False
        )

        result = mapper_agent.load_headers(str(path))

        assert result["success"] is True
        assert "sheet_names" not in result
        assert "customer" in result["headers"]


def test_process_tool_call_load_headers_passes_sheet_name():
    """process_tool_call should forward an optional sheet_name to load_headers."""
    pytest.importorskip("openpyxl")
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="Sheet1", index=False)
            pd.DataFrame({"vendor": ["Acme"], "vendor_id": ["V001"]}).to_excel(
                writer, sheet_name="Vendors", index=False
            )

        result = json.loads(
            mapper_agent.process_tool_call(
                "load_headers",
                {"filepath": str(path), "sheet_name": "Vendors"},
            )
        )

        assert result["success"] is True
        assert "vendor" in result["headers"]


def test_load_headers_empty_file_returns_error():
    """load_headers should return a failure payload for a completely empty file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "empty.csv"
        f.write_text("", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is False
        assert "error" in result


def test_load_headers_header_only_returns_empty_samples():
    """A file with only a header row and no data rows should succeed with empty samples."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "headers_only.csv"
        f.write_text("customer,invoice,amount\n", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert result["headers"] == ["customer", "invoice", "amount"]
        assert result["samples"]["customer"] == []


def test_load_headers_xlsx_numeric_headers_after_metadata_row():
    """load_headers should find numeric column names (e.g. years) that follow a sparse metadata row."""
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "numeric_headers.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["Q1 Sales Report"])   # sparse metadata row
        ws.append([2022, 2023, 2024])    # numeric header row
        ws.append([100, 200, 300])       # data
        ws.append([150, 250, 350])       # data
        wb.save(path)

        result = mapper_agent.load_headers(str(path))

        assert result["success"] is True
        assert result["headers"] == ["2022", "2023", "2024"]
        assert result["samples"]["2022"] == ["100", "150"]


def test_save_mappings_returns_entries_written():
    """save_mappings should include entries_written in the result so Claude can verify coverage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = Path(tmpdir) / "mappings.json"
        mappings = [
            {"source_column": "client_name", "canonical_field": "Customer"},
            {"source_column": "job_ref", "canonical_field": "Job"},
        ]

        result = mapper_agent.save_mappings(str(target_file), mappings)

        assert result["success"] is True
        assert result["entries_written"] == 2


# --- Fix #1: "nan" string column names ---


def test_header_str_preserves_literal_nan_string():
    """_header_str must NOT filter the string 'nan' — only true float/None NaN."""
    assert mapper_agent._header_str("nan") == "nan"
    assert mapper_agent._header_str("NaN") == "NaN"
    assert mapper_agent._header_str(float("nan")) == ""
    assert mapper_agent._header_str(None) == ""


def test_load_headers_nan_column_name():
    """A column literally named 'nan' should appear in headers unchanged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.csv"
        f.write_text("customer,nan,amount\nAlice,cat1,100\nBob,cat2,200\n", encoding="utf-8")

        result = mapper_agent.load_headers(str(f))

        assert result["success"] is True
        assert "nan" in result["headers"]
        assert result["samples"]["nan"] == ["cat1", "cat2"]


# --- Fix #4: AgentLoopError on timeout ---


def test_agent_loop_raises_on_max_iterations():
    """agent_loop should raise AgentLoopError rather than returning a magic string."""
    with pytest.raises(mapper_agent.AgentLoopError):
        mapper_agent.agent_loop("dummy request", max_iterations=0)


# --- Fix #5: canonical_field normalisation ---


def test_save_mappings_normalizes_canonical_field_casing():
    """save_mappings should fix wrong casing (e.g. 'customer' → 'Customer')."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "out.json"
        mappings = [
            {"source_column": "client", "canonical_field": "customer"},
            {"source_column": "ref", "canonical_field": "VENDORID"},
        ]

        result = mapper_agent.save_mappings(str(target), mappings)

        assert result["success"] is True
        saved = json.loads(target.read_text(encoding="utf-8"))
        assert saved[0]["canonical_field"] == "Customer"
        assert saved[1]["canonical_field"] == "VendorID"
        assert "warnings" not in result


def test_save_mappings_warns_on_unknown_canonical_field():
    """save_mappings should include a warnings key for values outside CANONICAL_FIELDS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "out.json"
        mappings = [{"source_column": "account_no", "canonical_field": "Account"}]

        result = mapper_agent.save_mappings(str(target), mappings)

        assert result["success"] is True
        assert "warnings" in result
        assert "Account" in result["warnings"][0]


def test_save_mappings_null_canonical_field_is_valid():
    """null canonical_field (intentionally unmapped column) should not produce a warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "out.json"
        mappings = [{"source_column": "notes", "canonical_field": None, "notes": "free text"}]

        result = mapper_agent.save_mappings(str(target), mappings)

        assert result["success"] is True
        assert "warnings" not in result


def test_save_mappings_does_not_mutate_input():
    """save_mappings should not modify the caller's mappings list in place."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "out.json"
        original = {"source_column": "client", "canonical_field": "customer"}
        mappings = [original]

        mapper_agent.save_mappings(str(target), mappings)

        assert original["canonical_field"] == "customer"  # unchanged


# --- Fix #7: confidence field preserved in saved output ---


def test_save_mappings_preserves_confidence_field():
    """save_mappings must include confidence in every saved mapping object."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "out.json"
        mappings = [
            {
                "source_column": "client_name",
                "canonical_field": "Customer",
                "confidence": 0.97,
                "reasoning": "Direct name match",
            },
            {
                "source_column": "ref_no",
                "canonical_field": "Job",
                "confidence": 0.85,
                "reasoning": "Likely a job reference number",
            },
        ]

        result = mapper_agent.save_mappings(str(target), mappings)

        assert result["success"] is True
        saved = json.loads(target.read_text(encoding="utf-8"))
        for item in saved:
            assert "confidence" in item, f"confidence missing from {item}"
        assert saved[0]["confidence"] == 0.97
        assert saved[1]["confidence"] == 0.85


def test_save_mappings_tool_schema_requires_confidence():
    """The save_mappings tool schema must define confidence as a required item field."""
    schema = next(t for t in mapper_agent.TOOLS if t["name"] == "save_mappings")
    items = schema["input_schema"]["properties"]["mappings"]["items"]
    assert "confidence" in items["properties"], "confidence not in items.properties"
    assert "confidence" in items["required"], "confidence not in items.required"
    assert "reasoning" in items["properties"], "reasoning not in items.properties"
    assert "reasoning" in items["required"], "reasoning not in items.required"
