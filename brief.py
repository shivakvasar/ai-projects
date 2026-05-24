# Standardard library imports
import os
import json
import argparse

# 3rd party imports
import anthropic
from dotenv import load_dotenv

# Setup config
load_dotenv()

# Constants
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024
OUTPUT_FILENAME = "brief_output.json"

#Functions
def clean_response(response_text):
    startswith = "```json"
    endswith = "```"
    if response_text.startswith(startswith) and response_text.endswith(endswith):
        return response_text[len(startswith):-len(endswith)].strip()
    return response_text.strip()

def save_output(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def print_output(parsed, output_format):
    if output_format == "json":
        print(json.dumps(parsed, indent=2))
        return

    def list_lines(value):
        if isinstance(value, list):
            return value
        return str(value).splitlines()

    print("Summary:")
    if output_format == "bullets":
        for line in list_lines(parsed.get("summary", "")):
            print(f"- {line}")
    else:
        print(parsed.get("summary", ""))

    print("\nRisks:")
    if output_format == "bullets":
        for line in list_lines(parsed.get("risks", "")):
            print(f"- {line}")
    else:
        print(parsed.get("risks", ""))

    print("\nActions:")
    if output_format == "bullets":
        for line in list_lines(parsed.get("actions", "")):
            print(f"- {line}")
    else:
        print(parsed.get("actions", ""))

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

#Read financial data from a Txt file
with open('financial_data.txt', 'r') as f:
    financial_data = f.read()

parser = argparse.ArgumentParser(description="Generate a financial brief")
parser.add_argument(
    "--format",
    choices=["brief", "bullets", "json"],
    default="brief",
    help="Output style: brief, bullets, or json",
)
parser.add_argument(
    "--save",
    action="store_true",
    help="Save the parsed output to a file",
)
args = parser.parse_args()


# Main Logic
message = client.messages.create(
    model=MODEL,
    max_tokens=MAX_TOKENS,
    system="You are a CFO assistant.Return only valid JSON with exactly these keys: summary, risks, actions.",
    messages=[
    {"role": "user", "content": financial_data}
    ]
)

#Parse Json response after cleaning it
response_text = message.content[0].text
response_text = clean_response(response_text)
#print("Raw Response:", response_text)
parsed = json.loads(response_text)

# Print the results
print("Summary:", parsed["summary"])
print("Risks:", parsed["risks"])
print("Actions:", parsed["actions"])
print_output(parsed, args.format)

# Save the output to a JSON file
if args.save:
    save_output(parsed, OUTPUT_FILENAME)
    print(f"Output saved to {OUTPUT_FILENAME}")