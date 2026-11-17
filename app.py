"""Web interface for the IT Helpdesk Agent.

Run it:  streamlit run app.py

Two modes, chosen automatically:
  - Live mode: ServiceNow settings are present, so the agent works real tickets.
  - Demo mode: no ServiceNow settings (as on the public demo site), so the agent
    works practice tickets held in memory and cannot change any real system.

The agent itself is the same in both: same prompt, same loop, same approval rule.
"""

import json
import os

import streamlit as st
from dotenv import load_dotenv

st.set_page_config(page_title="IT Helpdesk Agent", layout="wide")
load_dotenv()

# On the hosting site, settings come from its "secrets" box instead of .env.
try:
    for key, value in st.secrets.items():
        if isinstance(value, str):
            os.environ.setdefault(key, value)
except Exception:
    pass  # no secrets configured, which is normal on your own computer

if not os.getenv("ANTHROPIC_API_KEY"):
    st.error("ANTHROPIC_API_KEY is not set. Add it to your .env file (or the site's secrets).")
    st.stop()

import agent  # noqa: E402  (must come after the key check above)
import audit  # noqa: E402
import tools  # noqa: E402
from fake_helpdesk import DEMO_TICKETS, FakeHelpdesk  # noqa: E402

HAS_SERVICENOW = all(
    os.getenv(name)
    for name in ("SERVICENOW_INSTANCE", "SERVICENOW_USERNAME", "SERVICENOW_PASSWORD")
)
DEMO_MODE = os.getenv("DEMO_MODE") == "1" or not HAS_SERVICENOW
MAX_DEMO_MESSAGES = 20  # per visitor, to limit API spend on the public demo

TOOL_LABELS = {
    "lookup_ticket": "Looked up a ticket",
    "list_open_tickets": "Listed open tickets",
    "add_work_note": "Added a work note",
    "update_ticket": "Updated a ticket",
    "escalate_ticket": "Escalated a ticket",
    "unlock_account": "Unlock an account",
    "send_password_reset": "Send a password reset",
    "resolve_ticket": "Resolve a ticket",
}
EXAMPLES = [
    "Show me the open tickets",
    "Handle the account lockout ticket",
    "Handle the ticket about the strange login alert",
    "Work through every open ticket",
]

# ---------------------------------------------------------------------------
# Per-visitor state. Streamlit re-runs this whole file on every click, and
# st.session_state is what survives between runs.
# ---------------------------------------------------------------------------

state = st.session_state
if "messages" not in state:
    state.messages = []  # the conversation as sent to Claude
    state.chat = []  # what is shown on screen
    state.decisions = {}  # approval answers, by tool call id
    state.sent = 0  # how many messages this visitor has sent
    state.desk = FakeHelpdesk(DEMO_TICKETS) if DEMO_MODE else None


def execute(tool_name: str, tool_input: dict) -> str:
    """Run a tool on the practice tickets (demo) or the real systems (live)."""
    if DEMO_MODE:
        return state.desk.execute(tool_name, tool_input)
    return tools.run_tool(tool_name, tool_input)


def record(tool_name: str, tool_input: dict, approval: str, result: str) -> None:
    """Show each action on the page, and in live mode write it to the audit log."""
    state.chat.append(
        {"kind": "tool", "tool": tool_name, "input": tool_input, "approval": approval, "result": result}
    )
    if not DEMO_MODE:
        audit.record(tool_name, tool_input, approval, result)


def approve(tool_name: str, tool_input: dict, call_id: str):
    """Return the visitor's answer, or None if they have not clicked yet.
    None makes the agent pause until one of the buttons below is pressed."""
    return state.decisions.get(call_id)


def advance() -> None:
    """Run the agent until it finishes or needs an approval."""
    with st.spinner("The agent is working..."):
        try:
            answer = agent.run_agent(
                state.messages, approve=approve, execute=execute, record=record, verbose=False
            )
        except Exception as error:
            state.chat.append({"kind": "error", "text": f"Something went wrong: {error}"})
            return
    if answer is not None:
        state.chat.append({"kind": "agent", "text": answer})


def waiting_for_approval() -> list:
    """Risky tool calls the agent has asked for that nobody has answered yet."""
    return [
        call
        for call in agent.pending_tool_calls(state.messages)
        if call.name in tools.NEEDS_APPROVAL and call.id not in state.decisions
    ]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    if DEMO_MODE:
        st.subheader("Demo mode")
        st.write(
            "The agent is working practice tickets held in memory. "
            "Nothing here changes a real system."
        )
        st.subheader("Ticket queue")
        for ticket in state.desk.tickets.values():
            status = ticket["state"]
            if ticket["assignment_group"]:
                status += f", assigned to {ticket['assignment_group']}"
            st.markdown(f"**{ticket['number']}** ({status})  \n{ticket['short_description']}")
    else:
        st.subheader("Live mode")
        st.write(f"Connected to ServiceNow at {os.getenv('SERVICENOW_INSTANCE')}")

    st.subheader("Try asking")
    for example in EXAMPLES:
        if st.button(example, use_container_width=True):
            state.queued = example

    st.divider()
    if st.button("Start over"):
        state.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

st.title("IT Helpdesk Agent")
st.caption(
    "Triages and resolves IT support tickets. It fixes routine requests, asks a "
    "person before any risky action, and escalates everything else."
)

for entry in state.chat:
    if entry["kind"] == "user":
        st.chat_message("user").write(entry["text"])
    elif entry["kind"] == "agent":
        st.chat_message("assistant").write(entry["text"])
    elif entry["kind"] == "error":
        st.error(entry["text"])
    else:
        label = TOOL_LABELS.get(entry["tool"], entry["tool"])
        if entry["approval"] == "approved":
            label += " (approved by you)"
        elif entry["approval"] == "denied":
            label += " (declined by you, not carried out)"
        with st.expander(f"Action: {label}"):
            st.write("Details sent:")
            st.json(entry["input"])
            st.write("Result:")
            st.json(json.loads(entry["result"]))

# Approval cards: one for each risky action the agent is asking to take.
waiting = waiting_for_approval()
for call in waiting:
    with st.container(border=True):
        st.markdown(f"**Approval needed: {TOOL_LABELS.get(call.name, call.name)}**")
        for key, value in call.input.items():
            st.markdown(f"- {key.replace('_', ' ')}: {value}")
        reason = st.text_input(
            "Reason, if you decline (optional)", key=f"reason_{call.id}"
        )
        left, right = st.columns(2)
        approved = left.button("Approve", key=f"yes_{call.id}", type="primary", use_container_width=True)
        declined = right.button("Decline", key=f"no_{call.id}", use_container_width=True)
        if approved or declined:
            state.decisions[call.id] = (approved, "" if approved else reason)
            if not waiting_for_approval():  # every card answered: carry on
                advance()
            st.rerun()

limit_reached = DEMO_MODE and state.sent >= MAX_DEMO_MESSAGES
if limit_reached:
    st.info("This demo session has reached its message limit. Use Start over to begin again.")

typed = st.chat_input(
    "Waiting for your approval above" if waiting else "Ask the agent to work a ticket",
    disabled=bool(waiting) or limit_reached,
)
prompt = typed or state.pop("queued", None)

if prompt and not waiting and not limit_reached:
    state.sent += 1
    state.messages.append({"role": "user", "content": prompt})
    state.chat.append({"kind": "user", "text": prompt})
    st.chat_message("user").write(prompt)
    advance()
    st.rerun()
