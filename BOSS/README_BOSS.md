(# Ingest: CSV/XLSX Header Mapper

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

**Notes & troubleshooting**
- The mapper only recognizes fields listed in the system prompt; if a column is classified as `Unknown`, consider expanding the canonical field list.
- The script reads only the first few rows to infer types — make sure the sample rows include representative values (e.g., supplier IDs like `S1234`).
- If the model wraps its JSON in triple-backtick fences, `parse_mappings()` strips them before parsing.

**Additional tool: `mapper_agent.py`**

`mapper_agent.py` is a second mapping utility that uses an agent loop and tool-calling style with Claude.

- `load_headers(filepath)` — reads up to 5 rows from the input file, extracts column headers, and returns up to 3 sample values per column.
- `inspect_column(header, sample_values)` — returns the current column data so Claude can reason about the mapping in the next turn.
- `save_mappings(filepath, mappings)` — writes the mapping results to a JSON file.
- `process_tool_call(tool_name, tool_input)` — executes the requested tool by name and returns the JSON result.
- `agent_loop(user_message, max_iterations=10)` — drives the agent: sends the user request to Claude, handles tool calls from the model, executes them, and feeds results back until a final response is returned.

The agent supports relative file paths and will resolve them against the current working directory, the `BOSS` script directory, and the repo root.

The prompt instructs Claude to use the following workflow:
1. Call `load_headers()` once.
2. Call `inspect_column()` for each column and decide the mapping.
3. Call `save_mappings()` after all columns are mapped.

The final output should be a JSON-style mapping with these fields for each source column:
- `source_column`
- `canonical_field`
- `confidence`
- `sample_values`

This file is useful when you want a more agentic workflow instead of a single CLI mapper.

**See also**
- `ingest.py` source: [BOSS/ingest.py](BOSS/ingest.py#L1-L201)
- `mapper_agent.py` source: [BOSS/mapper_agent.py](BOSS/mapper_agent.py)


