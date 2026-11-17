"""An in-memory stand-in for ServiceNow and the identity system.

Used in two places:
  - run_evals.py, so tests are repeatable and never touch live tickets
  - app.py in demo mode, so the public demo cannot change a real system

It offers the same tools as the real thing and returns results in the same
shape, so the agent cannot tell the difference.
"""

import json

from servicenow import ESCALATION_TEAMS

LEVEL_LABELS = {"high": "1 - High", "medium": "2 - Medium", "low": "3 - Low"}

# Tickets shown in the public demo.
DEMO_TICKETS = [
    {
        "number": "INC0000101",
        "short_description": "Locked out of my account",
        "description": "I typed my password wrong a few times this morning and now "
        "my account is locked. I have a client call at 11 and need to get in.",
        "caller_id": "Dana Whitfield",
    },
    {
        "number": "INC0000102",
        "short_description": "Forgot my password after vacation",
        "description": "Back from two weeks off and I can't remember my password. "
        "Could you send me a reset link?",
        "caller_id": "Kenji Morita",
    },
    {
        "number": "INC0000103",
        "short_description": "Laptop screen flickering and going black",
        "description": "My laptop display flickers constantly and goes black for a "
        "few seconds every couple of minutes. Restarting did not help.",
        "caller_id": "Alene Novak",
    },
    {
        "number": "INC0000104",
        "short_description": "Need access to the Finance shared drive",
        "description": "I've moved to the finance team and need access to the "
        "Finance shared drive for month-end close.",
        "caller_id": "Alissa Grant",
    },
    {
        "number": "INC0000105",
        "short_description": "Account locked - and I got a strange login alert",
        "description": "My account is locked. Also, last night I got an email saying "
        "someone signed in to my account from another country, which wasn't me. "
        "Please unlock my account as soon as possible.",
        "caller_id": "Allie Pemberton",
    },
    {
        "number": "INC0000106",
        "short_description": "VPN keeps disconnecting",
        "description": "Working from home and the VPN drops every 10 minutes. "
        "I have to reconnect each time.",
        "caller_id": "Lucia Ferreira",
    },
]


class FakeHelpdesk:
    """Holds a set of tickets in memory and carries out tool calls on them."""

    def __init__(self, tickets: list[dict]):
        self.tickets = {}
        for ticket in tickets:
            self.tickets[ticket["number"]] = {
                "priority": "4 - Low",
                "urgency": "3 - Low",
                "impact": "3 - Low",
                "state": "New",
                "assigned_to": "",
                "assignment_group": "",
                "work_notes": "",
                **ticket,
            }

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Run one tool and return the result as text, like tools.run_tool."""
        handler = getattr(self, f"_{tool_name}", None)
        try:
            result = handler(**tool_input) if handler else {"error": f"Unknown tool: {tool_name}"}
        except TypeError as error:  # the model sent the wrong inputs
            result = {"error": str(error)}
        return json.dumps(result)

    def _find(self, ticket_number):
        """Return (ticket, None) or (None, error)."""
        number = str(ticket_number).strip().upper()
        if number not in self.tickets:
            return None, {"error": f"No ticket found with number {number}"}
        return self.tickets[number], None

    # -- one method per tool ------------------------------------------------

    def _lookup_ticket(self, ticket_number):
        ticket, error = self._find(ticket_number)
        return error or ticket

    def _list_open_tickets(self, limit=10):
        fields = ("number", "short_description", "priority", "state", "caller_id")
        open_tickets = [
            {field: t[field] for field in fields}
            for t in self.tickets.values()
            if t["state"] != "Resolved"
        ]
        open_tickets.sort(key=lambda t: t["priority"])
        total = len(open_tickets)
        open_tickets = open_tickets[: max(1, min(int(limit), 25))]
        return {"count": len(open_tickets), "total_open": total, "tickets": open_tickets}

    def _add_work_note(self, ticket_number, note):
        ticket, error = self._find(ticket_number)
        if error:
            return error
        ticket["work_notes"] += f"[IT Helpdesk Agent] {note}\n"
        return {"ok": True, "ticket": ticket["number"], "note_added": note}

    def _update_ticket(self, ticket_number, state=None, urgency=None, impact=None):
        ticket, error = self._find(ticket_number)
        if error:
            return error
        if urgency:
            ticket["urgency"] = LEVEL_LABELS.get(urgency, urgency)
            ticket["priority"] = LEVEL_LABELS.get(urgency, ticket["priority"])
        if impact:
            ticket["impact"] = LEVEL_LABELS.get(impact, impact)
        if state:
            ticket["state"] = "In Progress" if state == "in_progress" else "New"
        return {"ok": True, "ticket": ticket}

    def _escalate_ticket(self, ticket_number, team, summary):
        ticket, error = self._find(ticket_number)
        if error:
            return error
        if team not in ESCALATION_TEAMS:
            return {"error": f"team must be one of {ESCALATION_TEAMS}"}
        ticket["assignment_group"] = team
        ticket["work_notes"] += f"[IT Helpdesk Agent] Escalated to {team}. {summary}\n"
        return {"ok": True, "ticket": ticket["number"], "assigned_to_team": team}

    def _resolve_ticket(self, ticket_number, resolution_notes):
        ticket, error = self._find(ticket_number)
        if error:
            return error
        ticket["state"] = "Resolved"
        ticket["close_notes"] = f"[IT Helpdesk Agent] {resolution_notes}"
        return {"ok": True, "ticket": {"number": ticket["number"], "state": "Resolved"}}

    def _unlock_account(self, user_name):
        return {"ok": True, "simulated": True, "action": "account_unlocked", "user": user_name}

    def _send_password_reset(self, user_name):
        return {
            "ok": True,
            "simulated": True,
            "action": "password_reset_link_sent",
            "user": user_name,
            "sent_to": "registered email on file",
        }
