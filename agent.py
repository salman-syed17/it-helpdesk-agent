"""IT Helpdesk Agent - milestone 2: the core agent loop.

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

load_dotenv()  # reads ANTHROPIC_API_KEY from the .env file

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 10  # safety limit so the agent can never loop forever

client = Anthropic()

SYSTEM_PROMPT = """You are an IT helpdesk agent for a mid-sized company.
You help employees and IT staff with support tickets.

Rules:
- Always look up a ticket with the lookup_ticket tool before discussing it.
  Never guess what a ticket says.
- Be concise and practical. Say what the issue is and what the next step is.
- If a ticket does not exist, say so plainly."""


# ---------------------------------------------------------------------------
# Tools
# For now the "ticket system" is a small dictionary. In milestone 3 this is
# replaced with real calls to ServiceNow, and the rest of the file stays the same.
# ---------------------------------------------------------------------------

PRACTICE_TICKETS = {
    "INC001": {
        "requester": "Dana Whitfield",
        "summary": "Locked out of my account after too many password attempts",
        "priority": "high",
        "status": "open",
    },
    "INC002": {
        "requester": "Marcus Oyelaran",
        "summary": "Need access to the Finance shared drive for month-end close",
        "priority": "medium",
        "status": "open",
    },
    "INC003": {
        "requester": "Priya Raman",
        "summary": "Laptop fan is very loud and the machine shuts down in meetings",
        "priority": "medium",
        "status": "open",
    },
}


def lookup_ticket(ticket_id: str) -> dict:
    """Return one ticket, or an error the model can read and react to."""
    ticket = PRACTICE_TICKETS.get(ticket_id.strip().upper())
    if ticket is None:
        return {"error": f"No ticket found with id {ticket_id}"}
    return ticket


# This is what Claude sees. The description matters: it is how the model
# decides when to use the tool.
TOOLS = [
    {
        "name": "lookup_ticket",
        "description": (
            "Look up a helpdesk ticket by its id (for example INC001). "
            "Returns the requester, summary, priority and status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The ticket id, such as INC001",
                }
            },
            "required": ["ticket_id"],
        },
    }
]

# Maps a tool name to the Python function that carries it out.
TOOL_FUNCTIONS = {"lookup_ticket": lookup_ticket}


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
    print("IT Helpdesk Agent. Try: 'What is ticket INC001 about?'  (type 'quit' to exit)\n")
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
