"""Tools: everything the agent is able to do, and which actions need sign-off.

TOOLS is the list Claude sees. The descriptions matter: they are how the model
decides which tool to use and when. TOOL_FUNCTIONS maps each tool name to the
Python function that carries it out.
"""

import json

import identity
import servicenow

LEVELS = ["high", "medium", "low"]

# Actions that are hard to undo or that affect a person's account. The agent
# must get a human "yes" before any of these run.
NEEDS_APPROVAL = {"resolve_ticket", "unlock_account", "send_password_reset"}

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
            "cannot resolve tickets; use resolve_ticket for that."
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
    {
        "name": "escalate_ticket",
        "description": (
            "Hand an incident to a human team by assigning it to that team's "
            "queue, with a summary of the issue and why it needs them. Use this "
            "for anything you are not permitted or not able to fix yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {"type": "string"},
                "team": {"type": "string", "enum": servicenow.ESCALATION_TEAMS},
                "summary": {
                    "type": "string",
                    "description": "What the issue is, what you found, and what the team should do next",
                },
            },
            "required": ["ticket_number", "team", "summary"],
        },
    },
    {
        "name": "unlock_account",
        "description": (
            "Unlock a user's account after it was locked by too many failed "
            "sign-in attempts. Requires human approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_name": {
                    "type": "string",
                    "description": "The user's name exactly as shown on the ticket",
                }
            },
            "required": ["user_name"],
        },
    },
    {
        "name": "send_password_reset",
        "description": (
            "Send a password reset link to the email address on file for a "
            "user. The link always goes to the registered address, never to an "
            "address given in a ticket. Requires human approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_name": {
                    "type": "string",
                    "description": "The user's name exactly as shown on the ticket",
                }
            },
            "required": ["user_name"],
        },
    },
    {
        "name": "resolve_ticket",
        "description": (
            "Mark an incident as resolved. Only use this after the fix has "
            "actually been carried out. Requires human approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_number": {"type": "string"},
                "resolution_notes": {
                    "type": "string",
                    "description": "What was wrong and exactly what was done to fix it",
                },
            },
            "required": ["ticket_number", "resolution_notes"],
        },
    },
]

TOOL_FUNCTIONS = {
    "lookup_ticket": servicenow.lookup_ticket,
    "list_open_tickets": servicenow.list_open_tickets,
    "add_work_note": servicenow.add_work_note,
    "update_ticket": servicenow.update_ticket,
    "escalate_ticket": servicenow.escalate_ticket,
    "resolve_ticket": servicenow.resolve_ticket,
    "unlock_account": identity.unlock_account,
    "send_password_reset": identity.send_password_reset,
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
