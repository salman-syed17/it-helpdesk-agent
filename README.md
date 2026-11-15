# IT Helpdesk Agent

An AI agent that triages and resolves IT helpdesk tickets. It reads a ticket,
decides what to do, calls tools to act on it, and escalates to a human when a
request is risky or unclear.

**Status:** Milestone 2 of 6 - the core agent loop works in the terminal with a
practice ticket queue. Real ServiceNow integration comes next.

## Run it

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    (then paste your Anthropic API key into .env)
python agent.py
```

## Roadmap

- [x] 1. Project setup
- [x] 2. Core agent loop with a practice tool
- [ ] 3. Read and update real tickets in ServiceNow
- [ ] 4. Resolve routine requests, with human approval for risky actions
- [ ] 5. Evaluation set and scoring script
- [ ] 6. Web interface, deployment, demo video
