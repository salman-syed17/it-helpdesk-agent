"""ServiceNow client: the functions the agent uses to reach the real ticket system.

Everything here talks to ServiceNow's Table API, a standard REST API where each
database table (we use "incident") has a web address you can read from and write to.

Run this file on its own to test your connection:
    python servicenow.py
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

INSTANCE = os.getenv("SERVICENOW_INSTANCE", "").rstrip("/")
USERNAME = os.getenv("SERVICENOW_USERNAME", "")
PASSWORD = os.getenv("SERVICENOW_PASSWORD", "")

TIMEOUT_SECONDS = 30

# The ticket fields we ask ServiceNow for. Fewer fields = less for the model to read.
LIST_FIELDS = "number,short_description,priority,state,category,caller_id,opened_at"
DETAIL_FIELDS = (
    "sys_id,number,short_description,description,priority,urgency,impact,state,"
    "category,caller_id,assigned_to,assignment_group,opened_at,work_notes,comments"
)

# The agent uses plain words; ServiceNow stores numbers.
STATE_CODES = {"new": "1", "in_progress": "2"}
LEVEL_CODES = {"high": "1", "medium": "2", "low": "3"}


def _request(method: str, path: str, params: dict = None, body: dict = None) -> dict:
    """Send one request to ServiceNow. Always returns a dict; errors come back
    as {"error": "..."} so the agent can read them instead of crashing."""
    if not (INSTANCE and USERNAME and PASSWORD):
        return {"error": "ServiceNow settings are missing from the .env file."}

    try:
        response = requests.request(
            method,
            f"{INSTANCE}/api/now/table/{path}",
            auth=(USERNAME, PASSWORD),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            params=params,
            json=body,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        return {"error": f"Could not reach ServiceNow: {error}"}

    if response.status_code == 401:
        return {"error": "ServiceNow rejected the username or password."}
    try:
        data = response.json()
    except ValueError:
        # A sleeping developer instance answers with a web page instead of data.
        return {
            "error": "ServiceNow did not return data. The instance may be asleep: "
            "sign in at developer.servicenow.com to wake it, then try again."
        }

    if response.status_code >= 400:
        # Pass ServiceNow's own explanation through. A 403 can mean "no
        # permission", but also "a required field is missing" or "a rule
        # blocked this change", and only the detail says which.
        error = data.get("error", {}) if isinstance(data, dict) else {}
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        detail = error.get("detail", "") if isinstance(error, dict) else ""
        text = " - ".join(part for part in (message, detail) if part)
        return {"error": f"ServiceNow refused (HTTP {response.status_code}): {text or 'no reason given'}"}
    return data


def _find_ticket(ticket_number: str, fields: str) -> dict:
    """Fetch one incident by its number (e.g. INC0010001)."""
    number = ticket_number.strip().upper()
    data = _request(
        "GET",
        "incident",
        params={
            "sysparm_query": f"number={number}",
            "sysparm_limit": 1,
            "sysparm_fields": fields,
            "sysparm_display_value": "true",  # "1 - Critical" instead of "1"
            "sysparm_exclude_reference_link": "true",
        },
    )
    if "error" in data:
        return data
    if not data.get("result"):
        return {"error": f"No ticket found with number {number}"}
    return data["result"][0]


# ---------------------------------------------------------------------------
# The actions the agent can take in ServiceNow
# ---------------------------------------------------------------------------

def lookup_ticket(ticket_number: str) -> dict:
    """Full details of one ticket, including its notes history."""
    return _find_ticket(ticket_number, DETAIL_FIELDS)


def list_open_tickets(limit: int = 10) -> dict:
    """The most urgent open tickets, highest priority first."""
    limit = max(1, min(int(limit), 25))
    data = _request(
        "GET",
        "incident",
        params={
            "sysparm_query": "active=true^ORDERBYpriority^ORDERBYopened_at",
            "sysparm_limit": limit,
            "sysparm_fields": LIST_FIELDS,
            "sysparm_display_value": "true",
            "sysparm_exclude_reference_link": "true",
        },
    )
    if "error" in data:
        return data
    return {"count": len(data["result"]), "tickets": data["result"]}


def add_work_note(ticket_number: str, note: str) -> dict:
    """Add an internal note to a ticket. Work notes are visible to IT staff only."""
    ticket = _find_ticket(ticket_number, "sys_id,number")
    if "error" in ticket:
        return ticket
    data = _request(
        "PATCH",
        f"incident/{ticket['sys_id']}",
        params={"sysparm_fields": "number"},
        body={"work_notes": f"[IT Helpdesk Agent] {note}"},
    )
    if "error" in data:
        return data
    return {"ok": True, "ticket": ticket["number"], "note_added": note}


def update_ticket(
    ticket_number: str, state: str = None, urgency: str = None, impact: str = None
) -> dict:
    """Change a ticket's state, urgency or impact. ServiceNow recalculates
    priority from urgency and impact automatically."""
    changes = {}
    if state is not None:
        if state not in STATE_CODES:
            return {"error": f"state must be one of {list(STATE_CODES)}"}
        changes["state"] = STATE_CODES[state]
    for name, value in (("urgency", urgency), ("impact", impact)):
        if value is not None:
            if value not in LEVEL_CODES:
                return {"error": f"{name} must be one of {list(LEVEL_CODES)}"}
            changes[name] = LEVEL_CODES[value]
    if not changes:
        return {"error": "Nothing to update. Give a state, urgency or impact."}

    ticket = _find_ticket(ticket_number, "sys_id,number")
    if "error" in ticket:
        return ticket
    data = _request(
        "PATCH",
        f"incident/{ticket['sys_id']}",
        params={
            "sysparm_fields": "number,state,urgency,impact,priority",
            "sysparm_display_value": "true",
        },
        body=changes,
    )
    if "error" in data:
        return data
    return {"ok": True, "ticket": data["result"]}


# Teams a ticket can be handed to. These groups exist in a standard ServiceNow
# developer instance.
ESCALATION_TEAMS = ["Service Desk", "Hardware", "Network", "Software", "Database"]


def escalate_ticket(ticket_number: str, team: str, summary: str) -> dict:
    """Hand a ticket to a human team, with a note explaining why."""
    if team not in ESCALATION_TEAMS:
        return {"error": f"team must be one of {ESCALATION_TEAMS}"}
    ticket = _find_ticket(ticket_number, "sys_id,number")
    if "error" in ticket:
        return ticket
    data = _request(
        "PATCH",
        f"incident/{ticket['sys_id']}",
        params={
            "sysparm_fields": "number,assignment_group",
            "sysparm_display_value": "true",
            "sysparm_exclude_reference_link": "true",
            # lets us set the team by its name instead of its internal id
            "sysparm_input_display_value": "true",
        },
        body={
            "assignment_group": team,
            "work_notes": f"[IT Helpdesk Agent] Escalated to {team}. {summary}",
        },
    )
    if "error" in data:
        return data
    assigned = data["result"].get("assignment_group")
    if not assigned:
        return {"error": f"ServiceNow has no group named '{team}', so the ticket was not assigned."}
    return {"ok": True, "ticket": ticket["number"], "assigned_to_team": assigned}


# The "resolution code" ServiceNow requires on a resolved ticket. The allowed
# values differ between ServiceNow releases, and an unrecognised value is
# silently dropped, so we try these in order and remember the one that works.
# \u2013 is a long dash, which newer releases use in these names.
RESOLUTION_CODES = [
    "Resolved \u2013 Permanent Fix Applied",  # 2026 releases
    "Resolved - Permanent Fix Applied",
    "Solution provided",  # 2024-2025 releases
    "Solved (Permanently)",  # older releases
]
_working_code = None  # filled in after the first successful resolve


def resolve_ticket(ticket_number: str, resolution_notes: str) -> dict:
    """Mark a ticket as resolved, recording what was done to fix it."""
    global _working_code
    if not resolution_notes.strip():
        return {"error": "resolution_notes are required to resolve a ticket."}
    ticket = _find_ticket(ticket_number, "sys_id,number")
    if "error" in ticket:
        return ticket

    codes = [_working_code] if _working_code else RESOLUTION_CODES
    data = {"error": "No resolution code to try."}
    for code in codes:
        data = _request(
            "PATCH",
            f"incident/{ticket['sys_id']}",
            params={
                "sysparm_fields": "number,state,close_code,close_notes",
                "sysparm_display_value": "true",
            },
            body={
                "state": "6",  # 6 = Resolved
                "close_code": code,
                "close_notes": f"[IT Helpdesk Agent] {resolution_notes}",
            },
        )
        # ServiceNow dropped this code as invalid: try the next one.
        if "error" in data and "Resolution code" in data["error"]:
            continue
        break

    if "error" in data:
        return data
    if "resolved" not in str(data["result"].get("state", "")).lower():
        return {
            "error": "ServiceNow accepted the request but the ticket is not "
            f"resolved (state is '{data['result'].get('state')}')."
        }
    _working_code = code
    return {"ok": True, "ticket": data["result"]}


if __name__ == "__main__":
    # Connection test: python servicenow.py
    print(f"Connecting to {INSTANCE or '(no instance set)'} ...")
    result = list_open_tickets(limit=3)
    if "error" in result:
        print("FAILED:", result["error"])
    else:
        print(f"Connected. Found {result['count']} open tickets, for example:")
        for t in result["tickets"]:
            print(f"  {t['number']}  [{t['priority']}]  {t['short_description']}")
