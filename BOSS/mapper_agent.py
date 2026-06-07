"""Agent loop implementing tool-calling pattern for CSV/XLSX data mapping."""

import json
import os
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Tool definitions for the agent
TOOLS = [
    {
        "name": "load_csv_headers",
        "description": (
            "Load column headers and sample values from a CSV file. "
            "Returns the first 3 sample values for each column."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the CSV file to read",
                }
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "load_xlsx_headers",
        "description": (
            "Load column headers and sample values from an Excel file. "
            "Returns the first 3 sample values for each column."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the XLSX file to read",
                }
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "map_to_canonical_fields",
        "description": (
            "Map source column headers to canonical fields using Claude. "
            "Returns JSON with source_column, canonical_field, confidence, "
            "and sample_values for each mapping."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of source column headers",
                },
                "samples": {
                    "type": "object",
                    "description": "Dict of column_name -> [sample_values]",
                },
            },
            "required": ["headers", "samples"],
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


def load_csv_headers(filepath: str) -> dict[str, Any]:
    """Simulate loading CSV headers and samples."""
    try:
        import pandas as pd

        df = pd.read_csv(filepath, nrows=5)
        headers = df.columns.tolist()
        samples = {
            col: df[col].dropna().astype(str).tolist()[:3] for col in headers
        }
        return {"headers": headers, "samples": samples, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


def load_xlsx_headers(filepath: str) -> dict[str, Any]:
    """Simulate loading XLSX headers and samples."""
    try:
        import pandas as pd

        df = pd.read_excel(filepath, nrows=5)
        headers = df.columns.tolist()
        samples = {
            col: df[col].dropna().astype(str).tolist()[:3] for col in headers
        }
        return {"headers": headers, "samples": samples, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


def map_to_canonical_fields(headers: list[str], samples: dict) -> dict[str, Any]:
    """Call Claude to map headers to canonical fields."""
    sample_text = "\n".join(
        [f"- '{h}': {samples.get(h, [])}" for h in headers]
    )
    user_message = f"Map these columns to canonical fields:\n{sample_text}"

    system_message = (
        "You are a data mapper. Given CSV headers and sample values, "
        "return a JSON array mapping each source column to a canonical field.\n"
        "Canonical fields: Customer, Job, Invoice, Payment, Task, Vendor, "
        "Supplier, SupplierID, Unknown\n"
        "Return ONLY a valid JSON array. Each item must have: "
        "source_column, canonical_field, confidence (0.0-1.0), sample_values."
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_message,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = (
                raw_text.split("\n", 1)[1]
                if "\n" in raw_text
                else raw_text[3:]
            )
        if raw_text.endswith("```"):
            raw_text = raw_text.rsplit("```", 1)[0]

        mappings = json.loads(raw_text.strip())
        return {"mappings": mappings, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


def save_mappings(filepath: str, mappings: list) -> dict[str, Any]:
    """Save mappings to a JSON file."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
        return {
            "success": True,
            "message": f"Mappings saved to {filepath}",
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return the result as a JSON string."""
    if tool_name == "load_csv_headers":
        result = load_csv_headers(tool_input["filepath"])
    elif tool_name == "load_xlsx_headers":
        result = load_xlsx_headers(tool_input["filepath"])
    elif tool_name == "map_to_canonical_fields":
        result = map_to_canonical_fields(
            tool_input["headers"], tool_input["samples"]
        )
    elif tool_name == "save_mappings":
        result = save_mappings(tool_input["filepath"], tool_input["mappings"])
    else:
        result = {"error": f"Unknown tool: {tool_name}"}

    return json.dumps(result)


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

        # Call Claude with tools
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            tools=TOOLS,
            messages=messages,
        )

        # Check if we're done (no tool use blocks)
        if response.stop_reason == "end_turn":
            # Extract the final text response
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

        # Process tool calls if present
        tool_calls_made = False
        for block in response.content:
            if block.type == "tool_use":
                tool_calls_made = True
                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                print(f"  → Tool call: {tool_name}")
                print(f"    Input: {json.dumps(tool_input, indent=2)}")

                # Execute the tool
                tool_result = process_tool_call(tool_name, tool_input)
                print(f"    Result: {tool_result}")

                # Add assistant message and tool result to conversation
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": tool_result,
                            }
                        ],
                    }
                )
                break  # Process one tool at a time; loop will call Claude again

        # If no tool calls, we're done
        if not tool_calls_made:
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

    return "Agent loop reached max iterations"


def main():
    """Demo: use the agent to map a CSV file."""
    user_request = (
        "Load the CSV file at BOSS/sample.csv, map the columns to canonical fields, "
        "and save the results to BOSS/sample.mapped.json"
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
