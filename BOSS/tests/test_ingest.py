"""Unit tests for BOSS/ingest.py.

ingest.py is the entry point the batch-ingest workflow runs, so these tests
cover the CSV/XLSX reading it delegates to mapper_agent (header-row detection,
delimiter probing, encoding fallback) plus its own response parsing and
reporting. They do not call Claude; only the local helpers are exercised.
"""

from importlib import util
import json
import tempfile
from pathlib import Path

import pytest


# Load ingest.py directly from the BOSS package directory.
MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest.py"
Spec = util.spec_from_file_location("ingest", MODULE_PATH)
ingest = util.module_from_spec(Spec)
Spec.loader.exec_module(ingest)

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "sample.csv"
SAMPLE_MAPPED_JSON = Path(__file__).resolve().parents[1] / "sample.mapped.json"


def write(tmpdir, name, text, encoding="utf-8"):
    """Write text to a file in tmpdir and return its path as a string."""
    path = Path(tmpdir) / name
    path.write_text(text, encoding=encoding)
    return str(path)


# --- load_headers: happy path -----------------------------------------------


def test_load_headers_happy_path():
    """The committed sample.csv should yield its headers and first sample values."""
    headers, samples = ingest.load_headers(str(SAMPLE_CSV))

    assert headers[0] == "client_name"
    assert "amount_due" in headers
    assert samples["client_name"][:2] == [
        "Tan Brothers Pte Ltd",
        "City Mall Management",
    ]


def test_load_headers_samples_capped_at_three():
    """Only the first 3 non-null values per column are returned as samples."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = "\n".join(f"Customer {i},{i * 100}" for i in range(1, 9))
        path = write(tmpdir, "many.csv", f"client_name,amount_due\n{rows}\n")

        headers, samples = ingest.load_headers(path)

        assert headers == ["client_name", "amount_due"]
        assert samples["client_name"] == ["Customer 1", "Customer 2", "Customer 3"]


# --- load_headers: title / metadata rows ------------------------------------


def test_load_headers_skips_title_rows():
    """A report title above the header row must not be mistaken for the headers.

    This is the case that previously raised pandas.errors.ParserError, because
    the narrow title rows have fewer fields than the real header row.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write(
            tmpdir,
            "titled.csv",
            "Quarterly Invoice Export\n"
            "Generated 2026-01-01\n"
            "client_name,invoice_no,amount\n"
            "Tan Brothers Pte Ltd,INV-1,100\n"
            "City Mall Management,INV-2,250\n",
        )

        headers, samples = ingest.load_headers(path)

        assert headers == ["client_name", "invoice_no", "amount"]
        assert samples["invoice_no"] == ["INV-1", "INV-2"]


def test_load_headers_samples_from_rows_below_old_five_row_limit():
    """Sample values are collected from deeper than the first 5 data rows.

    A sparsely populated column whose first value appears after row 5 used to
    come back with no samples at all, because only 5 rows were read.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        rows = "\n".join(f"Customer {i},{i * 100}," for i in range(1, 6))
        path = write(
            tmpdir,
            "sparse.csv",
            "client_name,amount_due,notes\n"
            f"{rows}\n"
            "Customer 6,600,late payment\n"
            "Customer 7,700,disputed\n",
        )

        headers, samples = ingest.load_headers(path)

        assert headers == ["client_name", "amount_due", "notes"]
        assert samples["notes"] == ["late payment", "disputed"]


# --- load_headers: delimiters ------------------------------------------------


@pytest.mark.parametrize(
    "delimiter, name",
    [(";", "semicolon"), ("\t", "tab"), ("|", "pipe")],
)
def test_load_headers_non_comma_delimiters(delimiter, name):
    """Semicolon/tab/pipe files must be split into columns, not read as one column.

    A comma-only reader returns a single header such as 'client_name;amount_due',
    which is silently wrong rather than an error.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        header_line = delimiter.join(["client_name", "amount_due"])
        data_line = delimiter.join(["Tan Brothers Pte Ltd", "4500.00"])
        path = write(tmpdir, f"{name}.csv", f"{header_line}\n{data_line}\n")

        headers, samples = ingest.load_headers(path)

        assert headers == ["client_name", "amount_due"]
        assert samples["client_name"] == ["Tan Brothers Pte Ltd"]


# --- load_headers: encodings -------------------------------------------------


def test_load_headers_utf8_bom():
    """A UTF-8 BOM (added by Excel's CSV export) must not corrupt the first header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write(
            tmpdir,
            "bom.csv",
            "client_name,amount_due\nTan Brothers Pte Ltd,4500\n",
            encoding="utf-8-sig",
        )

        headers, _ = ingest.load_headers(path)

        assert headers == ["client_name", "amount_due"]


def test_load_headers_cp1252_fallback():
    """Non-UTF-8 bytes must fall back to a legacy encoding instead of raising."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "cp1252.csv"
        # "José" and the € sign are not valid UTF-8 when encoded as cp1252.
        path.write_bytes(
            "client_name,notes\nJosé Lda,Café €50\n".encode("cp1252")
        )

        headers, samples = ingest.load_headers(str(path))

        assert headers == ["client_name", "notes"]
        assert samples["client_name"] == ["José Lda"]


def test_load_headers_latin1_fallback():
    """Bytes that are invalid in both UTF-8 and cp1252 still fall back to latin-1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "latin1.csv"
        path.write_bytes(b"client_name,notes\nA\x81B Ltd,note\n")

        headers, samples = ingest.load_headers(str(path))

        assert headers == ["client_name", "notes"]
        assert samples["notes"] == ["note"]


# --- load_headers: error handling -------------------------------------------


def test_load_headers_rejects_unsupported_extension():
    """A non-spreadsheet extension should fail loudly rather than be parsed as CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write(tmpdir, "notes.txt", "client_name,amount_due\nAcme,1\n")

        with pytest.raises(ValueError, match="Unsupported file extension"):
            ingest.load_headers(path)


def test_load_headers_missing_file_raises():
    """A path that does not exist must raise, not return empty headers."""
    with pytest.raises(ValueError):
        ingest.load_headers("does/not/exist.csv")


def test_load_headers_empty_file_raises():
    """An empty file has no header row to find, so it must raise."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write(tmpdir, "empty.csv", "")

        with pytest.raises(ValueError):
            ingest.load_headers(path)


# --- load_headers: XLSX ------------------------------------------------------


def test_load_headers_xlsx():
    """XLSX input is read through the same code path as CSV."""
    pytest.importorskip("openpyxl")
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "book.xlsx"
        pd.DataFrame(
            {"client_name": ["Tan Brothers Pte Ltd"], "amount_due": [4500]}
        ).to_excel(path, index=False, engine="openpyxl")

        headers, samples = ingest.load_headers(str(path))

        assert headers == ["client_name", "amount_due"]
        assert samples["client_name"] == ["Tan Brothers Pte Ltd"]


def test_load_headers_accepts_xlsm():
    """.xlsm is a supported extension (it was rejected before consolidation)."""
    assert ".xlsm" in ingest.SUPPORTED_SUFFIXES


# --- parse_mappings ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        '[{"source_column": "client_name"}]',
        '```json\n[{"source_column": "client_name"}]\n```',
        '```json\n[{"source_column": "client_name"}]\n```\n',
        '```\n[{"source_column": "client_name"}]\n```',
        '  \n[{"source_column": "client_name"}]\n  ',
    ],
)
def test_parse_mappings_tolerates_fences_and_whitespace(raw):
    """Fenced, unfenced, and trailing-newline responses must all parse."""
    assert ingest.parse_mappings(raw) == [{"source_column": "client_name"}]


def test_parse_mappings_invalid_json_raises_value_error():
    """Unparseable output raises ValueError including the raw response for debugging."""
    with pytest.raises(ValueError, match="did not return valid JSON"):
        ingest.parse_mappings("Sorry, I can't help with that.")


# --- print_mappings ----------------------------------------------------------


def test_print_mappings_handles_null_canonical_field(capsys):
    """canonical_field: null is a valid 'no match' result, not a crash.

    Previously raised TypeError: unsupported format string passed to
    NoneType.__format__.
    """
    ingest.print_mappings(
        [{"source_column": "internal_ref", "canonical_field": None, "confidence": 0.4}]
    )

    out = capsys.readouterr().out
    assert "internal_ref" in out
    assert "unmapped" in out
    assert "0.40" in out


def test_print_mappings_handles_missing_confidence(capsys):
    """A mapping with no confidence key renders as n/a instead of raising KeyError."""
    ingest.print_mappings([{"source_column": "client_name", "canonical_field": "Customer"}])

    out = capsys.readouterr().out
    assert "client_name" in out
    assert "Customer" in out
    assert "n/a" in out


def test_print_mappings_accepts_committed_sample_output(capsys):
    """The repo's own sample.mapped.json must round-trip through print_mappings.

    It has no confidence key at all, so this file used to crash the reporter.
    """
    mappings = json.loads(SAMPLE_MAPPED_JSON.read_text(encoding="utf-8"))

    ingest.print_mappings(mappings)

    out = capsys.readouterr().out
    for entry in mappings:
        assert entry["source_column"].strip() in out


def test_print_mappings_empty_list(capsys):
    """An empty mapping list prints only the table header."""
    ingest.print_mappings([])

    assert "SOURCE COLUMN" in capsys.readouterr().out
