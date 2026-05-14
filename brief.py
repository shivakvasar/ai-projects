import anthropic
import os
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    system="You are a CFO assistant. Return a structured exec brief.",
messages=[
{"role": "user", "content": "Summarize the key financial priorities for the quarter."}
]
)

print (message.content[0].text)
