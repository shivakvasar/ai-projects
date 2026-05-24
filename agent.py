#standard library imports
import os
import json
import argparse
#3rd party imports
import anthropic
from dotenv import load_dotenv
#Setup config
load_dotenv()
#Constants
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024
OUTPUT_FILENAME = "agent_output.json"
#functions
#main logic