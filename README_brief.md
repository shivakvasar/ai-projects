# brief.py
`brief.py` is a small CLI utility that reads financial data from `financial_data.txt`, sends it to the Anthropic Claude API, and generates a structured CFO-style brief.

## What it does
- Reads raw input from `financial_data.txt`
- Sends the text to Anthropic using the configured API key
- Requests a JSON response containing exactly three keys: `summary`, `risks`, and `actions`
- Prints the results in one of three formats
- Optionally saves the parsed JSON to `brief_output.json`

## Requirements
- Python 3.8+
- `anthropic` Python package
- `python-dotenv` package
- an Anthropic API key

## Setup
1. Install dependencies: pip install anthropic python-dotenv
2. Create a `.env` file in the project root with your Anthropic API key: ANTHROPIC_API_KEY=your_api_key_here
3. Make sure `financial_data.txt` contains the financial text you want summarized.

## Usage
Run the script from the repository root: python brief.py
Print bullet-style results: python brief.py --format bullets
Print raw JSON: python brief.py --format json
Save the parsed output to `brief_output.json`: python brief.py --save

## Output
The script prints three sections:
- `Summary`
- `Risks`
- `Actions`

If `--format json` is selected, it prints the full JSON response instead.

## Notes
- The script expects the API response to be valid JSON wrapped with optional markdown code fences.
- If you want to change the model or output filename, update the `MODEL` or `OUTPUT_FILENAME` constants in `brief.py`.

## Development Setup

After cloning, activate the pre-commit hook so pytest runs before every commit:

```sh
git config core.hooksPath .githooks
```

This tells git to use the tracked `.githooks/` directory instead of `.git/hooks/`. The hook runs `pytest BOSS/tests/ -v` and blocks the commit if any test fails.
