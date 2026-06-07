"""Agent loop implementing a tool-calling workflow for CSV/XLSX header mapping."""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

# Load environment variables from the .env file in the project root.
# This makes values like ANTHROPIC_API_KEY available through os.getenv().
load_dotenv()

# Create a global Anthropic Claude client once, using the API key from the env.
# All subsequent calls in this script reuse this client.
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# System prompt for the agent loop. This keeps Claude aligned to the header mapping workflow
# and the canonical fields we expect.
SYSTEM_PROMPT = """You are a data mapper. Use the available tools to load CSV/XLSX headers,
inspect individual columns, and save a final JSON mapping.

Canonical fields: Customer, Job, Invoice, Payment, Task, Vendor, VendorID

Workflow:
1. Call load_headers() once to get all columns.
2. For each column, call inspect_column() then decide the mapping.
3. After all columns are mapped, call save_mappings().

Only reason about mapping through the provided tools; do not act on data directly."""

# Tool definitions exposed to the agent. Claude may request one of these tools by name.
# Each tool includes a name, a description, and a JSON schema describing its input.
TOOLS = [
    {
        "name": "load_headers",
        "description": (
            "Load column headers and sample values from a CSV or XLSX file. "
            "Returns the first 3 sample values for each column."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the input file to read",
                }
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "inspect_column",
        "description": (
            "Return a single column header and its sample values so the agent can "
            "perform the mapping reasoning in the next turn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "header": {
                    "type": "string",
                    "description": "The column header name",
                },
                "sample_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Example values for the column",
                },
            },
            "required": ["header", "sample_values"],
        },
    },
    {
        "name": "save_mappings",
        "description": "Save the mapping results to a JSON file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to save the JSON mappings",
                },
                "mappings": {
                    "type": "array",
                    "description": "List of mapping objects",
                },
            },
            "required": ["filepath", "mappings"],
        },
    },
]

def _resolve_filepath(filepath: str) -> Path:
    """Resolve a file path relative to cwd, the script directory, or the repo root."""
    candidate = Path(filepath).expanduser()
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    for base in (script_dir, repo_root):
        resolved = base / filepath
        if resolved.exists():
            return resolved

    return candidate


# Read a file and extract the header names plus a few sample rows.
# This tool supports both CSV and XLSX files, and resolves relative paths for
# repo-root and script-relative file references.
def load_headers(filepath: str) -> dict[str, Any]:
    """Read a CSV or Excel file and return column headers plus sample values."""
    try:
        import pandas as pd

        resolved_path = _resolve_filepath(filepath)
        if not resolved_path.exists():
            return {
                "error": f"File not found: {filepath}. Tried: {resolved_path}",
                "success": False,
            }

        # Choose CSV versus Excel reading based on the file extension.
        if resolved_path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(resolved_path, nrows=5)
        else:
            df = pd.read_csv(resolved_path, nrows=5)

        # The agent only needs the first few rows for header inference.
        # This is faster and avoids loading large datasets into memory.
        headers = df.columns.tolist()
        samples = {
            col: df[col].dropna().astype(str).tolist()[:3] for col in headers
        }

        return {"headers": headers, "samples": samples, "success": True}
    except Exception as e:
        # If anything fails, return the error so the agent can continue gracefully.
        return {"error": str(e), "success": False}

# Inspect a single header and its sample values and return the same data.
# This keeps the mapping decision in the outer Claude agent loop instead of making
# a second, nested Claude call inside the tool implementation.
def inspect_column(header: str, sample_values: list[str]) -> dict[str, Any]:
    """Return a column header and its sample values for agent reasoning."""
    return {
        "header": header,
        "sample_values": sample_values,
        "success": True,
    }

# Save the final set of canonical mappings into a JSON file.
def save_mappings(filepath: str, mappings: list) -> dict[str, Any]:
    """Write the mapping results to a JSON file."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
        return {
            "success": True,
            "message": f"Mappings saved to {filepath}",
        }
    except Exception as e:
        # If writing fails, return the error instead of raising.
        return {"error": str(e), "success": False}

# Route the tool request from Claude to the local Python helper function.
def process_tool_call(tool_name: str, tool_input: dict) -> str:
    """Dispatch tool calls from the agent to the matching Python helper."""
    if tool_name == "load_headers":
        result = load_headers(tool_input["filepath"])
    elif tool_name == "inspect_column":
        result = inspect_column(
            tool_input["header"], tool_input["sample_values"]
        )
    elif tool_name == "save_mappings":
        result = save_mappings(tool_input["filepath"], tool_input["mappings"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    # Always return a JSON string so the tool result can be fed back into the agent.
    return json.dumps(result)

# Run the entire tool-calling agent loop until a final Claude response is returned.
def agent_loop(user_message: str, max_iterations: int = 10) -> str:
    """
    Run the agentic loop with tool calling.

    The agent:
    1. Receives a user message
    2. Calls Claude with available tools
    3. If Claude returns tool calls, executes them
    4. Feeds results back to Claude
    5. Repeats until Claude provides a final response (no more tool calls)

    Args:
        user_message: The initial user request
        max_iterations: Max number of loop iterations to prevent infinite loops

    Returns:
        The final text response from Claude
    """
    messages = [{"role": "user", "content": user_message}]
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"\n[Iteration {iteration}] Calling Claude...")

        # Send the current conversation history, system prompt, and tool definitions to Claude.
        # Claude may return a tool use block if it wants to call one of our tools.
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Process any tool calls returned by Claude in the current response.
        # Claude may request multiple tool invocations in a single response.
        tool_calls_made = False
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_calls_made = True
                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                print(f"  → Tool call: {tool_name}")
                print(f"    Input: {json.dumps(tool_input, indent=2)}")

                # Execute the requested tool and serialize the result.
                tool_result = process_tool_call(tool_name, tool_input)
                print(f"    Result: {tool_result}")

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": tool_result,
                    }
                )

        if tool_results:
            # Add the tool invocation message and the matching tool_result blocks.
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )

        # If Claude did not request any tool, return its text output.
        if not tool_calls_made:
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

    # If the loop reaches the maximum iteration count, return a safe fallback.
    return "Agent loop reached max iterations"

# Demonstration entry point for running the agent with a fixed sample request.
def main():
    """Demo entry point: run the agent loop with a sample request."""
    # This demo request is intentionally simple: it asks the agent to use our tools.
    user_request = (
        "Load the file at BOSS/sample.csv, inspect each column with available tools, "
        "and save the mapping results to BOSS/sample.mapped.json"
    )

    print("=" * 70)
    print("AGENT LOOP DEMO: CSV Header Mapping")
    print("=" * 70)
    print(f"\nUser Request: {user_request}\n")

    final_response = agent_loop(user_request)

    print("\n" + "=" * 70)
    print("FINAL RESPONSE:")
    print("=" * 70)
    print(final_response)


if __name__ == "__main__":
    main()
