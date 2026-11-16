# IT Helpdesk Agent

An AI agent that triages and resolves IT helpdesk tickets. It reads a ticket,
decides what to do, calls tools to act on it, and escalates to a human when a
request is risky or unclear.

**Status:** Milestone 4 of 6 - the agent resolves routine tickets in a real
ServiceNow instance, asks a human before any risky action, and escalates the rest.

## How it handles a ticket

| Ticket type | What the agent does |
|---|---|
| Account lockout, forgotten password | Fixes it and resolves the ticket, **after human approval** |
| Hardware, network, software, database | Escalates to the right team with a summary |
| Access requests | Escalates to Service Desk (needs a manager's sign-off) |
| Anything security-related | Raises urgency and escalates; never attempts a fix |

## Safety design

- **Human approval.** Unlocking an account, sending a password reset and
  resolving a ticket cannot run until a person says yes. The check lives in
  code (`NEEDS_APPROVAL` in `tools.py`), not in the prompt, so the model cannot
  talk its way past it. If the person says no, the action does not run and the
  agent records that on the ticket.
- **Least privilege.** The agent signs in to ServiceNow as its own machine
  account with only the `itil` role, not as an administrator.
- **Audit log.** Every tool call is written to `logs/audit.jsonl` with its
  inputs, result and approval decision.

## Run it

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env         (then fill in your Anthropic key and ServiceNow details)
python servicenow.py           (tests the ServiceNow connection)
python create_test_tickets.py  (optional: adds practice tickets)
python agent.py
```

## Project layout

| File | Purpose |
|---|---|
| `agent.py` | Instructions, the agent loop, the approval prompt, terminal chat |
| `tools.py` | Tool definitions and the list of actions that need approval |
| `servicenow.py` | ServiceNow Table API calls |
| `identity.py` | Account unlock and password reset |
| `audit.py` | Audit log |

## Known limitations

- **Identity actions are simulated.** `identity.py` returns a success message
  without touching a real account. In production it would call an identity
  provider such as Okta or Microsoft Entra ID; the functions are isolated in
  one file so that swap changes nothing else.
- Runs in a terminal for one user at a time.

## Roadmap

- [x] 1. Project setup
- [x] 2. Core agent loop with a practice tool
- [x] 3. Read and update real tickets in ServiceNow
- [x] 4. Resolve routine requests, with human approval for risky actions
- [ ] 5. Evaluation set and scoring script
- [ ] 6. Web interface, deployment, demo video
