"""In-memory seed data for the mock bank.

Account ids are minted fresh on every login (see new_accounts()) rather than
being fixed constants, so a locator built from an id attribute is stale on
the very next session. That statelessness is deliberate — see
mock-bank/frontend/dashboard.html for where it bites.
"""

import secrets

from pydantic import BaseModel

USERNAME = "demo"
PASSWORD = "demo1234"


class Account(BaseModel):
    id: str
    type: str
    name: str
    balance: float


def new_accounts() -> list[Account]:
    return [
        Account(id=secrets.token_hex(8), type="checking", name="Checking", balance=2841.37),
        Account(id=secrets.token_hex(8), type="savings", name="Savings", balance=15000.00),
    ]
