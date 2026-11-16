# IT Helpdesk Agent

An AI agent that triages and resolves IT helpdesk tickets. It reads a ticket,
decides what to do, calls tools to act on it, and escalates to a human when a
request is risky or unclear.

**Status:** Milestone 3 of 6 - the agent reads, annotates and updates real
incidents in a ServiceNow instance from the terminal.

## Run it

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    (then fill in your Anthropic key and ServiceNow details)
python servicenow.py      (tests the ServiceNow connection)
python agent.py
```

## What it can do

| Tool | Action |
|---|---|
| `lookup_ticket` | Read one incident, including its notes history |
| `list_open_tickets` | Show the open queue, highest priority first |
| `add_work_note` | Add an internal note for IT staff |
| `update_ticket` | Change state, urgency or impact |

`agent.py` holds the agent loop and tool definitions; `servicenow.py` holds the
ServiceNow Table API calls.

## Roadmap

- [x] 1. Project setup
- [x] 2. Core agent loop with a practice tool
- [x] 3. Read and update real tickets in ServiceNow
- [ ] 4. Resolve routine requests, with human approval for risky actions
- [ ] 5. Evaluation set and scoring script
- [ ] 6. Web interface, deployment, demo video
