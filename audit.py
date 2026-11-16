"""Audit log: a permanent record of every action the agent takes.

Each tool call is written as one line of JSON to logs/audit.jsonl, including
whether a human approved it. In regulated settings this record is what lets you
answer "who changed this ticket, when, and who signed off?"
"""

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent / "logs" / "audit.jsonl"


def record(tool: str, tool_input: dict, approval: str, result: str) -> None:
    """Append one entry. approval is "not_required", "approved" or "denied"."""
    LOG_FILE.parent.mkdir(exist_ok=True)
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "input": tool_input,
        "approval": approval,
        "result": result,
    }
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")
