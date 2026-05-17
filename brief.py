# Standardard library imports
import os
import json

# 3rd party imports
import anthropic
from dotenv import load_dotenv

# Setup config
load_dotenv()

# Constants
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024

#Functions
def clean_response(response_text):
    startswith = "```json"
    endswith = "```"
    if response_text.startswith(startswith) and response_text.endswith(endswith):
        return response_text[len(startswith):-len(endswith)].strip()
    return response_text.strip()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

#Read financial data from a Txt file
with open('financial_data.txt', 'r') as f:
    financial_data = f.read()

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
