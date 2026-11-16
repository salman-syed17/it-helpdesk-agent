"""IT Helpdesk Agent - milestone 3: working real tickets in ServiceNow.

How an agent works, in one paragraph:
We send Claude the conversation plus a list of tools it may use. Claude either
answers in plain text, or replies "please run this tool with these inputs".
When it asks for a tool, OUR code runs it and sends the result back. We repeat
until Claude gives a final answer. That repeat is the "agent loop".
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

import servicenow

load_dotenv()  # reads ANTHROPIC_API_KEY from the .env file

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 10  # safety limit so the agent can never loop forever

client = Anthropic()

SYSTEM_PROMPT = """You are an IT helpdesk agent for a mid-sized company.
You help IT staff triage and work support tickets in ServiceNow.

Rules:
- Always look a ticket up with a tool before discussing it. Never guess what a
  ticket says, and never invent ticket numbers.
- Be concise and practical. Say what the issue is and what the next step is.
- Before you change a ticket (add a note, change state, urgency or impact),
  say what you are about to change. After the change, confirm what was done.
- Only change what you were asked to change.
- If a tool returns an error, tell the user plainly what went wrong."""


# ---------------------------------------------------------------------------
# Tools
# This list is what Claude sees. The descriptions matter: they are how the
# model decides which tool to use and when. The real work is in servicenow.py.
# ---------------------------------------------------------------------------

LEVELS = ["high", "medium", "low"]

TOOLS = [
    {
        "name": "lookup_ticket",
        "description": (
            "Get the full details of one ServiceNow incident by its number "
            "(for example INC0010001), including description, priority, state, "
            "who reported it, who it is assigned to, and its notes history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {
                    "type": "string",
                    "description": "The incident number, such as INC0010001",
                }
            },
            "required": ["ticket_number"],
        },
    },
    {
        "name": "list_open_tickets",
        "description": (
            "List open ServiceNow incidents, highest priority first. Use this "
            "to see the queue or to decide what to work on next."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many tickets to return (1-25, default 10)",
                }
            },
        },
    },
    {
        "name": "add_work_note",
        "description": (
            "Add an internal work note to an incident. Work notes are seen by "
            "IT staff only, not by the person who reported the issue. Use this "
            "to record triage findings or next steps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {"type": "string"},
                "note": {"type": "string", "description": "The note text"},
            },
            "required": ["ticket_number", "note"],
        },
    },
    {
        "name": "update_ticket",
        "description": (
            "Change an incident's state, urgency or impact. Priority is "
            "recalculated by ServiceNow from urgency and impact. This tool "
            "cannot resolve or close tickets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {"type": "string"},
                "state": {"type": "string", "enum": ["new", "in_progress"]},
                "urgency": {"type": "string", "enum": LEVELS},
                "impact": {"type": "string", "enum": LEVELS},
            },
            "required": ["ticket_number"],
        },
    },
]

# Maps a tool name to the Python function that carries it out.
TOOL_FUNCTIONS = {
    "lookup_ticket": servicenow.lookup_ticket,
    "list_open_tickets": servicenow.list_open_tickets,
    "add_work_note": servicenow.add_work_note,
    "update_ticket": servicenow.update_ticket,
}


def run_tool(name: str, tool_input: dict) -> str:
    """Run the tool Claude asked for and return the result as text."""
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(function(**tool_input))
    except Exception as error:  # report the failure to the model, don't crash
        return json.dumps({"error": str(error)})


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def run_agent(messages: list) -> str:
    """Call Claude repeatedly until it gives a final answer. Returns that answer."""
    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Keep Claude's reply in the history so it remembers what it did.
        messages.append({"role": "assistant", "content": response.content})

        # No tool requested means this is the final answer.
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        # Otherwise run every tool Claude asked for and send the results back.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  [tool] {block.name}({json.dumps(block.input)})")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": run_tool(block.name, block.input),
                    }
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
