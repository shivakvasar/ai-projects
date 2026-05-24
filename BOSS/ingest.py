# --- Imports ---------------------------------------------------------------
# Each "import" line pulls in a library so we can use its functions below.

import anthropic            # The official Claude API client.
import pandas as pd         # Library for working with tables (CSV / Excel). The "as pd" lets us type "pd" instead of "pandas".
import json                 # Built-in library for reading/writing JSON text.
import argparse             # Built-in library for parsing command-line arguments (e.g. --model foo).
from pathlib import Path    # "Path" is a modern way to handle file paths (better than plain strings).
from dotenv import load_dotenv  # Loads variables from a .env file into the environment (so the API key isn't hard-coded).

# Run load_dotenv() right at startup so anthropic.Anthropic() below can find ANTHROPIC_API_KEY.
load_dotenv()


# --- Constants -------------------------------------------------------------
# ALL_CAPS names are a Python convention meaning "this is a constant — don't change it at runtime."

MODEL = "claude-sonnet-4-5"   # Which Claude model to call. Change here to swap models everywhere.
MAX_TOKENS = 1024             # Upper limit on how many tokens (~words) Claude can return in one reply.


# Triple-quoted string ("""...""") lets us write a multi-line string.
# This is the "system prompt" — instructions Claude reads before every user message.
SYSTEM_PROMPT = """You are a data mapper. Given CSV headers and sample values, return a JSON array mapping each source column to a canonical field.

Canonical fields: Customer, Job, Invoice, Payment, Task, Vendor, Supplier, SupplierID, Unknown

Return ONLY a JSON array. No explanation. Each item must have:
- "source_column": the original header name
- "canonical_field": the best matching canonical field
- "confidence": a float between 0.0 and 1.0
- "sample_values": first 3 values from that column"""


# --- Functions -------------------------------------------------------------

def load_headers(filepath: str) -> tuple[list[str], dict]:
    """Read headers and sample values from CSV or XLSX.

    The "filepath: str" syntax is a type hint — it tells readers (and tools) that
    filepath should be a string. The "-> tuple[...]" hint describes the return type.
    Type hints don't change behavior; they're documentation Python can check.
    """
    # Path(filepath).suffix grabs the file extension (e.g. ".CSV").
    # .lower() makes it lowercase so ".CSV" and ".csv" both work.
    suffix = Path(filepath).suffix.lower()

    # Pick the right pandas reader based on the extension.
    # nrows=5 says "only read the first 5 rows" — we don't need the whole file
    # just to look at column names and a few sample values.
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, nrows=5)
    elif suffix == ".csv":
        df = pd.read_csv(filepath, nrows=5)
    else:
        # "raise" stops execution and reports an error. !r prints the value with quotes
        # around it, so the user sees: Unsupported file extension: '.txt'
        raise ValueError(f"Unsupported file extension: {suffix!r}")

    # df.columns is the list of column names. .tolist() converts it to a plain Python list.
    headers = df.columns.tolist()

    # This is a "dict comprehension" — a compact way to build a dictionary.
    # For each column name `col`, the value is:
    #   df[col]          -> the column (a pandas Series)
    #   .dropna()        -> drop empty/NaN cells
    #   .astype(str)     -> convert each value to a string
    #   .tolist()[:3]    -> turn into a list, then take the first 3 items
    # Result: {"FirstName": ["Alice", "Bob", "Carol"], "Amount": ["100", "250", "75"], ...}
    samples = {col: df[col].dropna().astype(str).tolist()[:3] for col in headers}

    # Return BOTH values as a tuple. The caller unpacks with: headers, samples = load_headers(...)
    return headers, samples


def parse_mappings(raw: str) -> list[dict]:
    """Parse Claude's response, tolerating markdown code fences.

    Claude sometimes wraps JSON in ```json ... ``` fences even when told not to.
    This function strips those fences before parsing, and gives a clear error
    if the result still isn't valid JSON.
    """
    text = raw.strip()  # Remove leading/trailing whitespace and newlines.

    # If the response starts with ``` it likely has a code fence we need to remove.
    if text.startswith("```"):
        # Split on the first newline to drop the opening fence line (e.g. "```json").
        # split("\n", 1) returns at most 2 parts; [1] is everything after the first newline.
        # If there's no newline at all, just chop off the leading 3 backticks.
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]

        # If there's a closing fence, drop everything from the last ``` onward.
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]

        text = text.strip()

    # try/except lets us catch an error and respond to it instead of crashing.
    try:
        # json.loads turns a JSON string into Python objects (list of dicts here).
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Re-raise as a friendlier error that includes the raw response, so we can debug.
        # "from e" preserves the original error in the traceback.
        raise ValueError(f"Model did not return valid JSON: {e}\n---\n{raw}\n---") from e


def map_fields(filepath: str, model: str = MODEL, max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Send headers to Claude and return canonical field mappings.

    Parameters with `=` after them are optional with default values.
    Calling map_fields("foo.csv") uses MODEL and MAX_TOKENS;
    calling map_fields("foo.csv", model="claude-opus-4-7") overrides just the model.
    """
    # Tuple unpacking: load_headers returns two things; assign them to two names at once.
    headers, samples = load_headers(filepath)

    # Build the user message Claude will see. f"..." is an f-string: anything in {braces}
    # is replaced by the value of that variable/expression.
    user_message = f"File: {filepath}\n\nHeaders and sample values:\n"
    for h in headers:
        # samples.get(h, []) returns samples[h] if it exists, else an empty list as fallback.
        # += appends to the string (equivalent to: user_message = user_message + ...).
        user_message += f"- '{h}': {samples.get(h, [])}\n"

    # Create the Claude API client. It automatically reads ANTHROPIC_API_KEY from the env.
    # We instantiate it inside the function (rather than at module load) so that importing
    # this file doesn't require the API key to be set.
    client = anthropic.Anthropic()

    # The actual API call. `messages` is a list of {role, content} dicts representing the conversation.
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,                                   # Instructions Claude reads first.
        messages=[{"role": "user", "content": user_message}]    # The user turn we want a reply to.
    )

    # response.content is a list of content blocks. The first block ([0]) is the text reply.
    # .text grabs its string value. We pass it through parse_mappings() to get a Python list.
    return parse_mappings(response.content[0].text)


def print_mappings(mappings: list[dict]):
    """Pretty-print the mapping results as a table."""
    # Format spec breakdown for {variable:<30}:
    #   <    means left-align
    #   30   means pad/truncate to 30 characters wide
    # So this builds neatly aligned columns.
    print(f"\n{'SOURCE COLUMN':<30} {'CANONICAL FIELD':<18} {'CONFIDENCE'}")
    print("-" * 65)  # Multiplying a string by N repeats it N times — handy for separator lines.

    for m in mappings:
        # "█" * int(m["confidence"] * 10) -> a visual bar.
        # If confidence is 0.7, that's 0.7 * 10 = 7.0, int() truncates to 7, so "███████".
        confidence_bar = "█" * int(m["confidence"] * 10)

        # {m['confidence']:.2f} -> format as a float with 2 decimal places (e.g. 0.73).
        print(f"{m['source_column']:<30} {m['canonical_field']:<18} {m['confidence']:.2f} {confidence_bar}")
    print()  # Blank line at the end.


def main():
    """Entry point when the script is run from the command line."""
    # argparse builds a command-line interface for us — including --help automatically.
    parser = argparse.ArgumentParser(description="Map CSV/XLSX headers to canonical fields using Claude.")

    # Positional argument (no leading --). nargs="?" makes it optional; default is used if omitted.
    parser.add_argument("filepath", nargs="?", default="sample.csv", help="Path to CSV or XLSX file")

    # Optional flags (start with --). type=int converts the string the user types into an int.
    parser.add_argument("--model", default=MODEL, help="Claude model ID")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS, help="Max tokens for the response")
    parser.add_argument("--output", help="Output JSON path (default: <input>.mapped.json)")

    # parse_args() reads sys.argv and returns an object with attributes matching the flag names.
    # Note: argparse converts --max-tokens to args.max_tokens (dashes become underscores).
    args = parser.parse_args()

    print(f"Mapping fields in: {args.filepath}")
    mappings = map_fields(args.filepath, model=args.model, max_tokens=args.max_tokens)
    print_mappings(mappings)

    # `a or b` evaluates to `a` if `a` is truthy, otherwise `b`. So we use the user's --output
    # if they passed one; otherwise we derive a default from the input filename.
    # Path("data/foo.csv").with_suffix(".mapped.json") -> Path("data/foo.mapped.json").
    output_path = args.output or str(Path(args.filepath).with_suffix(".mapped.json"))

    # "with open(...) as f:" is a context manager — it guarantees the file gets closed
    # even if something goes wrong inside the block.
    with open(output_path, "w") as f:
        # json.dump writes Python data to a file as JSON. indent=2 pretty-prints it.
        json.dump(mappings, f, indent=2)
    print(f"Saved to: {output_path}")


# This idiom means "only run main() if this file is executed directly,
# not if it's imported by another file." __name__ is "__main__" only when run directly.
if __name__ == "__main__":
    main()
