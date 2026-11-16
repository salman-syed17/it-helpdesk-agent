"""Identity actions: unlocking accounts and sending password resets.

IMPORTANT: this module is a SIMULATION. It does not touch any real accounts.
In a real deployment these two functions would call the company's identity
provider (for example Okta or Microsoft Entra ID). They are kept in their own
file, with the same inputs and outputs a real version would have, so that
swapping in a real provider later means changing only this file.
"""


def unlock_account(user_name: str) -> dict:
    """Unlock a user account that was locked after too many failed sign-ins."""
    return {
        "ok": True,
        "simulated": True,
        "action": "account_unlocked",
        "user": user_name,
    }


def send_password_reset(user_name: str) -> dict:
    """Send a password reset link to the email address on file for the user.
    The link goes only to the registered address, never to one given in a ticket."""
    return {
        "ok": True,
        "simulated": True,
        "action": "password_reset_link_sent",
        "user": user_name,
        "sent_to": "registered email on file",
    }
