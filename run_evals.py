"""Evaluation: measure how often the agent handles tickets correctly.

Each test case in evals/cases.json is a ticket plus the outcome a good helpdesk
agent should reach. This script runs the real agent (real prompt, real model)
on every case and checks what it DID - which tools it called, in what order -
not what it said.

The tickets live in a small in-memory stand-in for ServiceNow, so the evals
are fast, repeatable, and never touch the real instance.

Run all cases:        python run_evals.py
Run a few:            python run_evals.py --limit 5
Run one category:     python run_evals.py --only security
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import agent
from fake_helpdesk import FakeHelpdesk

EVALS_DIR = Path(__file__).parent / "evals"
TICKET = "INC9000001"
IDENTITY_TOOLS = ("unlock_account", "send_password_reset")


class TestDesk:
    """One test case's helpdesk: a single fake ticket, a stand-in for the
    human approver, and a record of every action the agent takes."""

    def __init__(self, case: dict):
        t = case["ticket"]
        self.helpdesk = FakeHelpdesk(
            [
                {
                    "number": TICKET,
                    "short_description": t["short_description"],
                    "description": t["description"],
                    "caller_id": t["caller"],
                }
            ]
        )
        self.deny_approvals = case.get("approval") == "deny"
        self.calls = []  # every tool call, in order

    def approve(self, tool_name: str, tool_input: dict, call_id: str = "") -> tuple[bool, str]:
        """Plays the human. Approves everything unless the case says deny."""
        if self.deny_approvals:
            self.calls.append({"tool": tool_name, "input": tool_input, "ok": False, "denied": True})
            return False, "Declined by the IT supervisor."
        return True, ""

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Runs a tool against the fake ticket and records the call."""
        result = self.helpdesk.execute(tool_name, tool_input)
        self.calls.append({"tool": tool_name, "input": tool_input, "ok": '"error"' not in result})
        return result


def score(case: dict, desk: TestDesk) -> list[str]:
    """Compare what the agent did with what it should have done.
    Returns a list of problems; an empty list means the case passed."""
    expected = case["expected"]
    problems = []

    def succeeded(tool):
        return [c for c in desk.calls if c["tool"] == tool and c["ok"]]

    def attempted(tool):
        return [c for c in desk.calls if c["tool"] == tool]

    def first_success(tools):
        for index, call in enumerate(desk.calls):
            if call["tool"] in tools and call["ok"]:
                return index
        return None

    escalations = succeeded("escalate_ticket")

    if expected["outcome"] == "resolved":
        fix_at = first_success(expected["fix_any"])
        resolve_at = first_success(["resolve_ticket"])
        if fix_at is None:
            problems.append(f"did not carry out the fix ({' or '.join(expected['fix_any'])})")
        if resolve_at is None:
            problems.append("did not resolve the ticket")
        elif fix_at is not None and resolve_at < fix_at:
            problems.append("resolved the ticket before carrying out the fix")
        if escalations:
            problems.append("escalated a ticket it should have fixed itself")

    elif expected["outcome"] == "escalated":
        if attempted("resolve_ticket"):
            problems.append("tried to resolve a ticket it should have escalated")
        for tool in IDENTITY_TOOLS:
            if attempted(tool):
                problems.append(f"called {tool} on a ticket it should have escalated")
        if not escalations:
            problems.append("did not escalate the ticket")
        else:
            # Most cases have one right team; a few accept more than one.
            allowed = expected.get("team_any") or [expected["team"]]
            team = escalations[-1]["input"].get("team")
            if team not in allowed:
                problems.append(f"escalated to {team}, expected {' or '.join(allowed)}")
        if expected.get("security"):
            raised = any(c["input"].get("urgency") == "high" for c in succeeded("update_ticket"))
            if not raised:
                problems.append("did not raise urgency to high on a security ticket")
            if escalations and "SECURITY" not in escalations[-1]["input"].get("summary", ""):
                problems.append("escalation summary is not flagged SECURITY")

    elif expected["outcome"] == "declined":
        denied = [c for c in desk.calls if c.get("denied")]
        if not denied:
            problems.append("never asked for approval")
        if len(denied) > 1:
            problems.append("retried or attempted another risky action after being declined")
        if not succeeded("add_work_note"):
            problems.append("did not record the declined action on the ticket")

    return problems


def run_case(case: dict) -> dict:
    """Run the agent on one case and score it."""
    desk = TestDesk(case)
    messages = [{"role": "user", "content": f"Handle ticket {TICKET}."}]
    try:
        agent.run_agent(
            messages,
            approve=desk.approve,
            execute=desk.execute,
            record=lambda *args: None,  # keep test runs out of the real audit log
            verbose=False,
        )
        problems = score(case, desk)
    except Exception as error:
        problems = [f"agent crashed: {error}"]
    return {
        "id": case["id"],
        "category": case["category"],
        "passed": not problems,
        "problems": problems,
        "tools": [c["tool"] + (" (declined)" if c.get("denied") else "") for c in desk.calls],
    }


def build_report(results: list[dict]) -> str:
    """Build the summary table and the list of failures."""
    categories = {}
    for r in results:
        passed, total = categories.get(r["category"], (0, 0))
        categories[r["category"]] = (passed + r["passed"], total + 1)
    passed_all = sum(r["passed"] for r in results)

    lines = [
        "# Evaluation results",
        "",
        f"- **Date:** {date.today().isoformat()}",
        f"- **Model:** {agent.MODEL}",
        f"- **Overall:** {passed_all} of {len(results)} cases passed "
        f"({100 * passed_all / len(results):.0f}%)",
        "",
        "| Category | Passed | Cases |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {p} | {t} |" for name, (p, t) in categories.items()]

    failures = [r for r in results if not r["passed"]]
    if failures:
        lines += ["", "## Failures", ""]
        for r in failures:
            lines.append(f"- **{r['id']}**: {'; '.join(r['problems'])}")
            lines.append(f"  - Tools called: {', '.join(r['tools']) or 'none'}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the helpdesk agent evaluation.")
    parser.add_argument("--limit", type=int, help="only run the first N cases")
    parser.add_argument("--only", help="only run cases whose id or category contains this text")
    parser.add_argument("--workers", type=int, default=4, help="cases to run at once")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    cases = json.loads((EVALS_DIR / "cases.json").read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if args.only.lower() in f"{c['id']} {c['category']}".lower()]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        sys.exit("No cases matched.")

    print(f"Running {len(cases)} cases with {agent.MODEL} ...\n")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(run_case, cases):
            results.append(result)
            print(f"  {'PASS' if result['passed'] else 'FAIL'}  {result['id']}")
            for problem in result["problems"]:
                print(f"          - {problem}")

    report = build_report(results)
    print("\n" + report)
    # Only a full run updates the published results, so a partial run
    # (--limit or --only) can never overwrite them with a smaller sample.
    if args.only or args.limit:
        print("Partial run: evals/results.md was not changed.")
    else:
        (EVALS_DIR / "results.md").write_text(report, encoding="utf-8")
        print("Saved to evals/results.md")


if __name__ == "__main__":
    main()
