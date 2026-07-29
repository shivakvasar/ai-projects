"""On-demand exception alert: asks Claude to review one customer's jobs for anomalies.

This is meant to be triggered manually (e.g. from the "Exception Alert" GitHub
Actions workflow, via workflow_dispatch) when someone wants a quick anomaly
check for a specific customer instead of waiting for a scheduled report.
"""

# --- Imports -----------------------------------------------------------------
import argparse          # Built-in: turns "python exception_alert.py Acme --alert-type overdue"
                          # into parsed args like args.customer_name / args.alert_type.
import json
import os
from datetime import datetime, timezone
from glob import glob    # glob("incoming/*.csv") -> list of matching file paths, as strings.

import anthropic
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# --- Constants ---------------------------------------------------------------
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 2048

# Where to look for job data. Every CSV under these folders is scanned; files
# that don't have a "client_name" column (or fail to parse) are skipped rather
# than treated as an error, since not every CSV in the repo is job data.
SEARCH_DIRS = ("incoming", "BOSS")

# Dropdown-style options surfaced in the GitHub Actions "Run workflow" form.
# "general" runs a broad anomaly sweep; the rest tell Claude which category of
# problem to focus on. Keep this in sync with the `options:` list in
# .github/workflows/exception-alert.yml.
ALERT_TYPES = ("general", "overdue", "duplicate", "amount")

SYSTEM_PROMPT = """You are a back-office exceptions monitor for a facilities/services
business. You will be given every known job record for a single customer, plus an
alert_type telling you which kind of problem to prioritize:
- "overdue": jobs whose date_issued looks stale (well in the past) with no sign of
  being closed out, or invoices that appear unpaid past a reasonable window.
- "duplicate": repeated job_ref values, or near-identical jobs (same customer, date,
  amount) that look like accidental double entry.
- "amount": amount_due values that are unusually high or low compared to this
  customer's other jobs, including zero or negative amounts.
- "general": scan for all of the above, plus anything else that looks wrong
  (missing fields, inconsistent vendor/assignee data, malformed dates, etc).

Return ONLY valid JSON (no markdown fences, no commentary) with exactly these keys:
- "status": one of "clear" (nothing found) or "alert" (one or more issues found)
- "anomalies": a JSON array, one object per issue found, each with:
  - "job_ref": the job reference the issue relates to (or null if it spans jobs)
  - "severity": "low", "medium", or "high"
  - "issue": a short label for the problem (e.g. "duplicate_job_ref")
  - "detail": one sentence explaining what you found and why it's a concern
- "summary": one or two sentences summarizing the overall finding for a human reader

If no job records are provided, or nothing looks wrong, return status "clear" with an
empty anomalies array."""


def clean_response(response_text: str) -> str:
    """Strip optional ```json ... ``` fences before parsing Claude's reply as JSON."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    return text


def load_customer_jobs(customer_name: str, search_dirs=SEARCH_DIRS) -> list[dict]:
    """Collect every row across incoming/*.csv (and BOSS/*.csv) whose client_name
    matches customer_name (case-insensitive substring match, so "Acme" matches
    "Acme Facilities").

    Returns a list of plain dicts, one per matching row, with a "source_file" key
    added so a human can trace an anomaly back to the CSV it came from.
    """
    needle = customer_name.strip().lower()
    jobs: list[dict] = []

    for directory in search_dirs:
        for path in glob(os.path.join(directory, "*.csv")):
            try:
                df = pd.read_csv(path, dtype=str)
            except Exception:
                continue  # Not a readable CSV — skip it rather than failing the whole run.

            if "client_name" not in df.columns:
                continue  # Not a job file (e.g. a stray CSV with unrelated columns).

            matches = df[df["client_name"].fillna("").str.lower().str.contains(needle)]
            for row in matches.to_dict(orient="records"):
                row["source_file"] = path
                jobs.append(row)

    return jobs


def check_anomalies(customer_name: str, alert_type: str, jobs: list[dict]) -> dict:
    """Send the customer's job rows to Claude and return the parsed structured alert."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    user_message = (
        f"Customer: {customer_name}\n"
        f"alert_type: {alert_type}\n\n"
        f"Job records ({len(jobs)} total):\n{json.dumps(jobs, indent=2)}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return json.loads(clean_response(response.content[0].text))


def build_alert(customer_name: str, alert_type: str) -> dict:
    """Full pipeline: load this customer's jobs, ask Claude to check them, and
    wrap the result with the metadata a downstream consumer (e.g. the GitHub
    Actions step summary) needs.
    """
    jobs = load_customer_jobs(customer_name)

    if not jobs:
        # No matching rows — skip the API call entirely, there's nothing to check.
        result = {"status": "no_data", "anomalies": [], "summary": "No job records found for this customer."}
    else:
        result = check_anomalies(customer_name, alert_type, jobs)

    return {
        "customer_name": customer_name,
        "alert_type": alert_type,
        "jobs_checked": len(jobs),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }


def main():
    parser = argparse.ArgumentParser(description="Check one customer's jobs for anomalies using Claude.")
    parser.add_argument("customer_name", help="Customer name to check (matched case-insensitively, substring OK)")
    parser.add_argument("--alert-type", choices=ALERT_TYPES, default="general", help="Which category of anomaly to prioritize")
    parser.add_argument("--output", help="Also write the alert JSON to this file path")
    args = parser.parse_args()

    alert = build_alert(args.customer_name, args.alert_type)
    print(json.dumps(alert, indent=2))

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(alert, f, indent=2)
        print(f"\nAlert saved to: {args.output}")


if __name__ == "__main__":
    main()
