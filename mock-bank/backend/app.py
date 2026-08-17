"""FastAPI backend for the mock bank.

In-memory, session-scoped state only — no database, no persistence across
restarts. This is the target application Cowpath automates, not the product
itself; see CLAUDE.md for why it lives outside app/.
"""

import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import data
from .data import Account

app = FastAPI()

SESSION_COOKIE = "session_id"
_SESSIONS: dict[str, list[Account]] = {}

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class LoginRequest(BaseModel):
    username: str
    password: str


def _session_accounts(request: Request) -> list[Account]:
    session_id = request.cookies.get(SESSION_COOKIE)
    accounts = _SESSIONS.get(session_id) if session_id else None
    if accounts is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return accounts


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/login.html")


@app.post("/api/login")
def login(body: LoginRequest, response: Response) -> dict[str, str]:
    if body.username != data.USERNAME or body.password != data.PASSWORD:
        raise HTTPException(status_code=401, detail="invalid credentials")
    session_id = secrets.token_hex(16)
    _SESSIONS[session_id] = data.new_accounts()
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True)
    return {"status": "ok"}


@app.get("/api/accounts")
def list_accounts(request: Request) -> list[Account]:
    return _session_accounts(request)


@app.get("/api/accounts/{account_id}")
def get_account(account_id: str, request: Request) -> Account:
    for account in _session_accounts(request):
        if account.id == account_id:
            return account
    raise HTTPException(status_code=404, detail="account not found")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
