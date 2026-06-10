# Ingest: CSV/XLSX Header Mapper

`ingest.py` maps CSV/XLSX column headers to canonical fields using the Claude API.

**What it does:**
- **Reads** the first few rows of a CSV or XLSX to extract column headers and sample values.
- **Sends** a compact prompt (headers + samples) to Claude and requests a JSON mapping.
- **Parses** the model response (tolerates Markdown code fences) into a list of mappings.
- **Prints** a human-readable table of `source_column`, `canonical_field`, and `confidence`.
- **Writes** the mappings to a `.mapped.json` file next to the input file (or to `--output`).

**Key files:**
- `ingest.py` ([BOSS/ingest.py](BOSS/ingest.py#L1-L201)) — main script implementing the logic.

**Requirements & setup**
- Python 3.8+
- Install dependencies:

```bash
pip install anthropic pandas python-dotenv
```

- Create a `.env` file in the project root with your Anthropic API key:

```ini
ANTHROPIC_API_KEY=your_api_key_here
```

**How it works (functions)**
- `load_headers(filepath)` — reads the input file (CSV/XLSX), returns `headers` and a `samples` dict containing up to 3 sample values per column.
- `parse_mappings(raw)` — strips optional ``` code fences and parses JSON returned by the model; raises a helpful error if parsing fails.
- `map_fields(filepath, model=..., max_tokens=...)` — builds a user message listing `headers` and sample values, calls Claude, and returns the parsed mappings.
- `print_mappings(mappings)` — prints a neat table with `SOURCE COLUMN`, `CANONICAL FIELD`, and `CONFIDENCE` (plus a visual bar).
- `main()` — CLI entry point; parses args, runs mapping, prints results, and saves the JSON output.

**System prompt**
The script defines a strict system prompt (see `ingest.py`) that enumerates the accepted canonical fields (for example: `Customer`, `Job`, `Invoice`, `Payment`, `Task`, `Vendor`, `VendorID`, `Unknown`). The model is instructed to return ONLY a JSON array with these keys for each column:

- `source_column` (string)
- `canonical_field` (string)
- `confidence` (float 0.0–1.0)
- `sample_values` (array)

If you add new column types, include them in that canonical fields list so the model can map correctly.

**Usage**

Run the script from the repository root (or the `BOSS` folder) with an input file path:

```bash
python ingest.py sample.csv
```

Optional flags:
- `--model` — override the Claude model ID
- `--max-tokens` — maximum tokens for the response (integer)
- `--output` — write mappings to a custom output path (default: `<input>.mapped.json`)

Examples:

```bash
python ingest.py sample.csv --model claude-sonnet-4-5 --max-tokens 1024
python ingest.py data/invoices.xlsx --output data/invoices.mapped.json
```

**Testing**

Unit tests for `mapper_agent.py` live in `BOSS/tests/test_mapper.py` (see `BOSS/tests/README.md`). Run from the repository root:

```bash
pytest -q BOSS/tests
```

If you are using GitHub Actions, add `ANTHROPIC_API_KEY` as a repository secret under Settings → Secrets and variables → Actions.

**Notes & troubleshooting**
- The mapper only recognizes fields listed in the system prompt; if a column is classified as `Unknown`, consider expanding the canonical field list.
- The script reads only the first few rows to infer types — make sure the sample rows include representative values (e.g., supplier IDs like `S1234`).
- If the model wraps its JSON in triple-backtick fences, `parse_mappings()` strips them before parsing.

**Additional tool: `mapper_agent.py`**

`mapper_agent.py` is an agentic mapping utility that drives Claude through a tool-calling loop to map CSV/XLSX column headers to canonical fields.

**Constants**

```python
CANONICAL_FIELDS = ("Customer", "Job", "Invoice", "Payment", "Task", "Vendor", "VendorID")
```

The seven recognised canonical field names. `save_mappings` normalises incoming values against this tuple (case-insensitive).

**Exceptions**

- `AgentLoopError(RuntimeError)` — raised by `agent_loop` if `max_iterations` is reached without a final text response from the model.

**Functions**

- `load_headers(filepath, sheet_name=None)` — reads up to 20 rows from a CSV or XLSX file, auto-detects the real header row (skipping title/metadata rows), and returns up to 3 non-null sample values per column.
  - **Encoding fallback**: tries `utf-8-sig` → `utf-8` → `cp1252` → `latin-1`; `utf-8-sig` strips the BOM that Excel adds to UTF-8 CSVs.
  - **Delimiter probing**: tests `,`, `\t`, `;`, `|` in order; uses `csv.reader` pre-scan + `names=` to NaN-pad rows narrower than the widest row, preventing `ParserError` on files with metadata rows.
  - **NA handling**: uses a custom `na_values` list that omits `"nan"`/`"NaN"`, so a column literally named `nan` is preserved as a string.
  - **Header row detection**: picks the first row where ≥50% of non-null cells are strings; falls back to the first non-sparse row for all-numeric headers (e.g. year ranges).
  - **Duplicate column names**: detected and renamed with `.1`, `.2`, … suffixes; originals listed in `duplicate_headers`.
  - **XLSX multi-sheet**: if the file has more than one sheet, returns `sheet_names` and `active_sheet`; re-call with `sheet_name=` to switch sheets.
  - Returns `{"success": False, "error": "..."}` for missing files or completely empty files.

- `inspect_column(header, sample_values)` — echoes a single column header and its sample values back as a JSON dict so the agent can reason about the mapping in the next turn.

- `save_mappings(filepath, mappings)` — writes mappings to a JSON file; creates parent directories as needed.
  - Normalises `canonical_field` casing (e.g. `"customer"` → `"Customer"`).
  - `null` canonical_field values (intentionally unmapped columns) are written as-is with no warning.
  - Returns `entries_written` (integer) so the agent can verify complete coverage.
  - Returns `warnings` for any `canonical_field` values not in `CANONICAL_FIELDS`.

- `process_tool_call(tool_name, tool_input)` — dispatches tool calls from the agent loop to the matching Python helper and returns the JSON result string.

- `agent_loop(user_message, max_iterations=50)` — drives the agentic loop: sends the user request to Claude, handles tool calls, feeds results back, and repeats until a final text response is returned. Raises `AgentLoopError` if `max_iterations` is reached.

The agent supports relative file paths and resolves them against the current working directory, the `BOSS` script directory, and the repo root.

**Agent workflow**

The system prompt instructs Claude to follow this sequence:
1. Call `load_headers()` once. If `sheet_names` is present, verify the active sheet and re-call with `sheet_name=` if needed. Note any `duplicate_headers`.
2. Call `inspect_column()` for each column (multiple calls per turn are allowed).
3. Call `save_mappings()`. Verify `entries_written` equals the header count; re-call if any columns were missed.

**Output schema per column**

```json
{
  "source_column": "client_name",
  "canonical_field": "Customer",
  "confidence": 0.95,
  "sample_values": ["Tan Brothers Pte Ltd", "City Mall Management"]
}
```

Columns that do not match any canonical field should use `null` for `canonical_field` and include a `"notes"` key explaining why.

**Testing**

33 unit tests covering the tool helpers, edge-case file formats, and the `AgentLoopError` path. No live Claude API calls are made during the test suite.

```bash
pytest -q BOSS/tests
```

**See also**
- `ingest.py` source: [BOSS/ingest.py](BOSS/ingest.py)
- `mapper_agent.py` source: [BOSS/mapper_agent.py](BOSS/mapper_agent.py)


