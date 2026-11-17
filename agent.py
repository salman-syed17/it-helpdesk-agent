"""IT Helpdesk Agent: triages and resolves ServiceNow tickets with human approval.

How an agent works, in one paragraph:
We send Claude the conversation plus a list of tools it may use. Claude either
answers in plain text, or replies "please run this tool with these inputs".
When it asks for a tool, OUR code runs it and sends the result back. We repeat
until Claude gives a final answer. That repeat is the "agent loop".

Files:
  agent.py       this file: the instructions, the loop, and the terminal chat
  app.py         the web interface (streamlit run app.py)
  tools.py       what the agent can do, and which actions need approval
  servicenow.py  the ServiceNow ticket system
  identity.py    account unlocks and password resets (simulated)
  audit.py       a record of every action taken
  run_evals.py   measures how often the agent gets tickets right
  fake_helpdesk.py  in-memory tickets for the tests and the public demo
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

import audit
from tools import NEEDS_APPROVAL, TOOLS, run_tool

load_dotenv()  # reads the settings in the .env file

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 15  # safety limit so the agent can never loop forever

client = Anthropic()

SYSTEM_PROMPT = """You are an IT helpdesk agent for a mid-sized company.
You help IT staff triage and work support tickets in ServiceNow.

General rules:
- Always look a ticket up with a tool before discussing or acting on it. Never
  guess what a ticket says, and never invent ticket numbers.
- Be concise and practical. Say what the issue is and what you did or will do.
- Only change what you were asked to change.
- If a tool returns an error, tell the user plainly what went wrong.
- When you list tickets, say how many there are in total if the list you were
  given is only part of the queue (for example "showing 10 of 43").
- If a tool result contains "simulated": true, the action was not carried out
  on a real system. Say so in your reply and in any resolution notes, for
  example "account unlock (simulated)". Never say a simulated action really
  happened.

What you may fix yourself (routine requests):
- Account lockouts: unlock the account, then resolve the ticket.
- Forgotten or expired passwords: send a password reset link, then resolve.
Record what you did in the resolution notes.

What you must hand to a human team with escalate_ticket:
- Hardware faults (laptops, monitors, printers, phones): Hardware
- Network, VPN, Wi-Fi or email delivery problems: Network
- Software installs, licences, application errors: Software
- Database problems: Database
- Access requests (shared drives, applications, permissions): Service Desk.
  These need a manager's sign-off, which you cannot give.
- Anything security-related (phishing, malware, suspicious sign-ins, lost or
  stolen devices, possible data exposure): set urgency to high, then escalate
  to Service Desk and begin the summary with "SECURITY:". Never try to fix
  these yourself, and never unlock an account or reset a password on a ticket
  that mentions suspicious activity.
- Anything unclear or that does not fit the above: Service Desk, saying what
  information is missing.

Approval:
- Unlocking an account, sending a password reset and resolving a ticket each
  need a human's approval. The system asks for it automatically when you call
  the tool, so call the tool directly instead of asking permission in chat.
- If an action is denied, do not retry it. Add a work note saying it was
  declined, then tell the user what you did and did not do.
- Never resolve a ticket unless the fix was actually carried out."""


def ask_in_terminal(tool_name: str, tool_input: dict, call_id: str = "") -> tuple[bool, str]:
    """Ask the person at the keyboard to approve one action.
    Returns (approved, reason). Other interfaces (the web app, the automated
    tests) supply their own version of this function."""
    print("\n  +-- APPROVAL NEEDED " + "-" * 40)
    print(f"  | The agent wants to: {tool_name}")
    for key, value in tool_input.items():
        print(f"  |   {key}: {value}")
    print("  +" + "-" * 59)
    answer = input("  Approve? (y/n): ").strip().lower()
    if answer in {"y", "yes"}:
        return True, ""
    reason = input("  Reason for declining (optional): ").strip()
    return False, reason


def pending_tool_calls(messages: list) -> list:
    """Tool calls Claude has asked for that have not been answered yet."""
    if not messages or messages[-1]["role"] != "assistant":
        return []
    content = messages[-1]["content"]
    if isinstance(content, str):
        return []
    return [block for block in content if block.type == "tool_use"]


def run_agent(
    messages: list,
    approve=ask_in_terminal,
    execute=run_tool,
    record=audit.record,
    verbose=True,
):
    """Call Claude repeatedly until it gives a final answer. Returns that answer.

    The defaults are the real thing: a person approving in the terminal, real
    tools, and the real audit log. The web app (app.py) and the evaluation
    script (run_evals.py) pass in their own versions.
      approve  how to get human sign-off for risky actions
      execute  how to run a tool
      record   where to log each action
      verbose  whether to print each tool call

    Pausing: a web page cannot stop and wait for a click the way a terminal
    waits for typing. So `approve` may return None, meaning "no answer yet".
    run_agent then returns None without running anything. Once the person has
    answered, call run_agent again with the same messages and it carries on
    from where it stopped."""
    for _ in range(MAX_STEPS):
        calls = pending_tool_calls(messages)  # not empty when resuming a pause

        if not calls:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            # Keep Claude's reply in the history so it remembers what it did.
            messages.append({"role": "assistant", "content": response.content})

            # No tool requested means this is the final answer.
            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text")
            calls = pending_tool_calls(messages)

        # Step 1: get a decision for every risky action before running anything.
        decisions = {}
        for block in calls:
            if block.name in NEEDS_APPROVAL:
                decision = approve(block.name, block.input, block.id)
                if decision is None:
                    return None  # paused: waiting for a human
                decisions[block.id] = decision

        # Step 2: run the tools and send the results back to Claude.
        tool_results = []
        for block in calls:
            if verbose:
                print(f"  [tool] {block.name}({json.dumps(block.input)})")

            approval = "not_required"
            if block.id in decisions:
                approved, reason = decisions[block.id]
                approval = "approved" if approved else "denied"

            if approval == "denied":
                # The tool does NOT run. Claude is told why and must adapt.
                result = json.dumps(
                    {"denied": True, "reason": reason or "A human declined this action."}
                )
            else:
                result = execute(block.name, block.input)

            record(block.name, block.input, approval, result)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result}
            )
        messages.append({"role": "user", "content": tool_results})

    return "I stopped because I reached my step limit. Please try rephrasing."


def main() -> None:
    print("IT Helpdesk Agent. Try: 'Show me the open tickets'  (type 'quit' to exit)\n")
    messages = []
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        print(f"Agent: {run_agent(messages)}\n")


if __name__ == "__main__":
    main()
