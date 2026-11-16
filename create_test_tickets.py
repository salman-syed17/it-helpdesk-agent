"""Create a few realistic practice tickets in your ServiceNow instance.

Run once:  python create_test_tickets.py
It prints the new ticket numbers so you can try the agent on them. The callers
are sample employees that come with a ServiceNow developer instance.
"""

import servicenow

TICKETS = [
    {
        "short_description": "Locked out of my account",
        "description": "I typed my password wrong a few times this morning and now "
        "my account is locked. I have a client call at 11 and need to get in.",
        "caller_id": "Abel Tuter",
    },
    {
        "short_description": "Forgot my password after vacation",
        "description": "Back from two weeks off and I can't remember my password. "
        "Could you send me a reset link?",
        "caller_id": "Aileen Mottern",
    },
    {
        "short_description": "Laptop screen flickering and going black",
        "description": "My laptop display flickers constantly and goes black for a "
        "few seconds every couple of minutes. Restarting did not help.",
        "caller_id": "Alene Rabeck",
    },
    {
        "short_description": "Need access to the Finance shared drive",
        "description": "I've moved to the finance team and need access to the "
        "Finance shared drive for month-end close.",
        "caller_id": "Alissa Mountjoy",
    },
    {
        "short_description": "Account locked - and I got a strange login alert",
        "description": "My account is locked. Also, last night I got an email saying "
        "someone signed in to my account from another country, which wasn't me. "
        "Please unlock my account as soon as possible.",
        "caller_id": "Allie Pumphrey",
    },
]

if __name__ == "__main__":
    for ticket in TICKETS:
        data = servicenow._request(
            "POST",
            "incident",
            # lets us name the caller instead of using an internal id
            params={"sysparm_fields": "number", "sysparm_input_display_value": "true"},
            body=ticket,
        )
        if "error" in data:
            print("FAILED:", data["error"])
            break
        print(f"Created {data['result']['number']}: {ticket['short_description']}")
