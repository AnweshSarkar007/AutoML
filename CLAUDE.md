# CLAUDE.md — Cowpath

Project instructions for Claude Code. Read this before any task in WORKFLOW.md.
This file is the architecture contract: WORKFLOW.md says *when*, this says *where* and *why*.
When the two disagree, stop and ask — do not guess.

---

## 1. Mission

Cowpath learns a browser workflow once, then repeats it forever without AI. **Phase 1 (discover):**
an LLM agent (Anthropic API + Playwright) is given a goal in plain English and drives a live browser
interactively against a mock banking site, one tool call at a time, until the goal is met.
**Phase 2 (compile):** the harness — not the model — turns that session into a deterministic JSON
*flow artifact*: an ordered list of steps, each carrying a **ranked locator ladder**
(`testid > role_name > label > text > css > coordinates`) harvested from the live DOM at the moment
the step succeeded. **Phase 3 (replay):** a pure Playwright engine reads that artifact and re-executes
it with **zero AI calls**, walking down the ladder rung by rung until one resolves, so the flow
survives DOM drift. A pure-function safety layer (origin allowlist, destructive-action denylist,
secret redaction) gates both the discovery and replay paths, and a human-handoff mechanism takes over
when replay genuinely cannot resolve a step.

**Design philosophy:** the model contributes the *sequence and intent*; the DOM contributes the
*selectors*. The model is never asked to emit artifact JSON. If you find yourself writing a prompt
that asks Claude for a selector or a JSON flow, you have taken a wrong turn.

---

## 2. Directory tree

Create exactly this. Every directory under `app/` has an `__init__.py`.

```
Automation ML/
├── CLAUDE.md                       # this file — the contract
├── WORKFLOW.md                     # day-by-day build plan
├── README.md                       # what/why/how-to-run (Day 0 skeleton, filled Day 7)
├── REPORT.md                       # findings, reliability numbers, tradeoffs (Day 7)
├── main.py                         # CLI: `discover` | `replay`. Thin argparse only.
├── requirements.txt                # single dependency set for the whole repo
├── .env.example                    # committed; documents every var
├── .env                            # gitignored; never read outside app/config.py
├── .gitignore
├── pyproject.toml                  # ruff + black config only (no build backend needed)
├── pytest.ini
├── Makefile
├── .github/workflows/ci.yml        # make lint → make test
├── .claude/commands/
│   ├── gate.md                     # end-of-day gate: lint, test, invariants, commit
│   └── invariants.md               # audits §4 of this file against the codebase (Day 5+)
│
├── app/                            # the product. Import root is `app`.
│   ├── __init__.py
│   ├── config.py                   # ONLY module that touches os.environ / .env
│   ├── context.py                  # RunContext, new_run_id()  — AI-free, shared
│   ├── evidence.py                 # TraceWriter, save_screenshot — AI-free, shared
│   ├── artifact/
│   │   ├── __init__.py
│   │   ├── schema.py               # pydantic v2: LocatorStrategy, Locator, StepKind, Binding, Step, Flow
│   │   └── storage.py              # save_flow / load_flow / list_flows  (only writer to artifacts/)
│   ├── replay/                     # AI-FREE ZONE (invariant I1)
│   │   ├── __init__.py
│   │   ├── errors.py               # RunResult union + internal exceptions
│   │   ├── locators.py             # ladder resolver + rung_budget() (pure where possible)
│   │   └── engine.py               # step executors AND the run_flow() loop
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── prompts.py              # SYSTEM_PROMPT (frozen string, no f-strings at module level)
│   │   ├── tools.py                # Anthropic tool schemas + handlers (harvest ladders here)
│   │   └── agent.py                # tool-use loop + compile_to_flow() compiler
│   ├── safety/
│   │   ├── __init__.py
│   │   └── policy.py               # check_navigation / check_action / redact — PURE, no I/O
│   └── intervention/
│       ├── __init__.py
│       └── handoff.py              # request_handoff() + state revalidation
│
├── mock-bank/                      # the TARGET APP. Not under app/. Not an installed package.
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── app.py                  # FastAPI: API routes + StaticFiles mount of ../frontend
│   │   └── data.py                 # in-memory seed data, session-scoped account IDs
│   └── frontend/
│       ├── login.html
│       ├── dashboard.html          # account rows: NO data-testid, ids reshuffle per session
│       ├── account.html            # detail view; 800ms artificial delay before balance renders
│       ├── app.js
│       └── styles.css
│
├── artifacts/                      # COMMITTED. Never gitignored.
│   ├── .gitkeep
│   └── get_savings_balance.json    # the reference flow (Day 4 output, hand-reviewed)
│
├── evidence/                       # COMMITTED. Never gitignored.
│   ├── .gitkeep
│   ├── reliability.md              # generated table (Day 6)
│   ├── discovery/<run_id>/
│   │   ├── trace.jsonl
│   │   ├── messages.json           # full Anthropic request/response transcript, redacted
│   │   └── steps/NNN-<step_id>.png
│   ├── replay/<run_id>/
│   │   ├── trace.jsonl
│   │   ├── result.json             # the serialized RunResult
│   │   └── steps/NNN-<step_id>.png
│   └── intervention/<run_id>-<step_id>.json
│
├── scripts/
│   └── reliability_run.py           # N replays → evidence/reliability.md
│
├── docs/
│   └── artifact-spec.md             # the full normative artifact spec (§6 here is the summary)
│
└── tests/
    ├── conftest.py                  # bank_server, page, settings, tmp_run fixtures + sys.path shim
    ├── fixtures/
    │   ├── dashboard_baseline.html  # static page the ladder resolves against
    │   ├── dashboard_drifted.html   # same page, testids removed + ids reshuffled
    │   └── flow_minimal.json        # 3-step flow for engine unit tests
    ├── test_mock_bank.py
    ├── test_schema.py
    ├── test_policy.py
    ├── test_locators.py
    ├── test_replay_is_ai_free.py    # AST walk + runtime socket block
    ├── test_replay_e2e.py           # replay artifacts/get_savings_balance.json against live bank
    ├── test_handoff.py
    └── test_reliability.py          # asserts reliability_run.py emits a well-formed table
```

### 2.1 Placement decisions worth knowing (settled — do not relitigate)

| Question | Decision | Why |
|---|---|---|
| Where does the `run_flow` loop live? | `app/replay/engine.py`, alongside the step executors. No `runner.py`. | The loop is ~60 lines and the executors are its body. Splitting them adds an import hop and a file a reviewer must cross-reference for no gain. `locators.py` and `errors.py` already carve out the parts worth isolating. |
| Shared run state for agent + replay? | Yes: `app/context.py` (`RunContext`, `new_run_id`) and `app/evidence.py` (`TraceWriter`, `save_screenshot`), both at `app/` top level. | Both paths need identical run_id/trace/screenshot semantics; duplicating them guarantees divergent evidence formats by Day 6. They sit at `app/` level (not inside either subpackage) precisely because `app/replay/` may not import from `app/agent/`. **Both must stay AI-free** (see I1). |
| Who reads `.env`? | `app/config.py` only. | Makes I4 auditable and lets `policy.py` stay pure. |
| Does mock-bank get its own `requirements.txt`? | No — shares the root one. | It is a test fixture, not a deployable. One venv, one CI install step. `fastapi`/`uvicorn` are already root deps. |
| Is `mock-bank/` importable? | Not by dotted path — the hyphen makes `mock-bank.backend` invalid Python. | Two access modes, both defined in `conftest.py`: (1) `sys.path.insert(0, ROOT / "mock-bank")` then `from backend.app import app` for `TestClient` unit tests; (2) the `bank_server` fixture spawns `python -m uvicorn backend.app:app --app-dir mock-bank --port <free>` for anything that needs a real browser. Never invent a third way. |
| `tests/conftest.py`? | Yes, one, at `tests/` root. | `bank_server`, `page`, `settings`, `tmp_run` are needed by 5+ test files. |
| Where do artifact JSON writes happen? | `app/artifact/storage.py` only. Evidence writes: `app/evidence.py` only. | Chokepoints make I4 a grep, not a code review. |

---

## 3. Makefile

GNU make, run from **Git Bash** on this machine (`make` is not in PowerShell by default; if you don't
have it, every recipe is deliberately a single copy-pasteable line). All targets `.PHONY`.
`PY ?= python`. Always invoke tools as `$(PY) -m <tool>` so it works without Scripts/ on PATH.

| Target | Command | Real from |
|---|---|---|
| `install` | `$(PY) -m pip install -r requirements.txt && $(PY) -m playwright install chromium` | Day 0 |
| `lint` | `$(PY) -m ruff check . && $(PY) -m black --check .` | Day 0 |
| `fmt` | `$(PY) -m ruff check --fix . && $(PY) -m black .` | Day 0 |
| `test` | `$(PY) -m pytest` | Day 0 (collects zero tests, still exits 0) |
| `clean` | remove `__pycache__`, `.pytest_cache`, `.ruff_cache` — **never** `artifacts/` or `evidence/` | Day 0 |
| `bank` | `$(PY) -m uvicorn backend.app:app --app-dir mock-bank --host 127.0.0.1 --port 8000` | Day 1 |
| `discover` | `$(PY) main.py discover --goal "$(GOAL)" --flow-id $(FLOW_ID)` | Day 4 |
| `replay` | `$(PY) main.py replay --flow artifacts/get_savings_balance.json` | Day 5 |
| `reliability` | `$(PY) scripts/reliability_run.py --n 20` | Day 6 |

Every not-yet-real target is `@echo "not implemented"` and **exits 0** — CI runs `make lint` then
`make test` only, so a stub must never break the build. Promote a stub to a real command in the same
commit that lands the code it invokes.

Use `127.0.0.1`, never `localhost` — on Windows the dual-stack resolution adds latency and makes
origin-allowlist string comparison ambiguous.

---

## 4. Invariants

These four are non-negotiable and are audited by `/invariants` from Day 5 onward. Each is stated so a
machine can check it. If a task in WORKFLOW.md appears to require breaking one, the task description
is wrong — stop and ask.

### I1 — Replay is provably AI-free

**Statement:** No module under `app/replay/`, nor any first-party module reachable from it, may
import `anthropic`, `openai`, or any `app.agent.*` module — directly or transitively.

**Reachable set (must all stay AI-free):** `app/replay/*`, `app/artifact/*`, `app/safety/*`,
`app/intervention/*`, `app/context.py`, `app/evidence.py`, `app/config.py`.

**How it's checked** (`tests/test_replay_is_ai_free.py`):
1. **Static:** `ast.walk` every `.py` in the reachable set, collect every `ast.Import` / `ast.ImportFrom`
   module name, follow first-party `app.*` imports transitively, and assert the closure contains no
   `anthropic`, `openai`, `app.agent`. Lazy imports inside functions count — the walk covers all nodes,
   not just module top level.
2. **Runtime:** monkeypatch `socket.socket` to raise, plus set `ANTHROPIC_API_KEY=""`, then run a full
   replay against pre-recorded fixture HTML (`file://` URLs, no network). A passing replay proves no
   outbound call was even attempted.

**Corollary for `main.py`:** import `app.agent.agent` **inside** the `discover` branch, not at module
top level, so `python main.py replay ...` never loads the Anthropic SDK.

### I2 — Public replay boundaries return `RunResult`, never raise

**Statement:** These functions must be annotated `-> RunResult` and must never propagate an exception
to their caller:
- `app.replay.engine.run_flow`
- `app.intervention.handoff.request_handoff`

`RunResult` is the closed union `Success | NeedsHuman | PolicyBlocked | Failed` (§5). All internal
failure signalling uses the exceptions in `app/replay/errors.py` (`LocatorUnresolved`,
`PolicyViolation`, `StepTimeout`, `BindingMissing`), and every one of them is caught and converted at
these two boundaries. A bare `except Exception` at each boundary converting to `Failed` is required,
not optional — an unknown crash must still be a `RunResult`.

**How it's checked:** annotation presence via AST; behaviourally, tests inject each failure class
(missing element, denied origin, absent binding, and a deliberately raising executor) and assert a
`RunResult` is returned rather than an exception raised. `main.py` maps result → exit code (§8), so a
process exit code of `1` in CI is itself an I2 violation.

### I3 — Safety policy is called on both paths, with no bypass

**Statement:** `app/safety/policy.check_navigation` runs before every navigation and
`check_action` before every click or other state-changing action, on **both** the discovery path
(agent tool handlers) and the replay path (engine executors).

**How it's checked — chokepoints.** There are exactly four functions in the repo permitted to touch
Playwright navigation/click primitives:

| Path | Navigation | Action |
|---|---|---|
| replay | `app/replay/engine._navigate` | `app/replay/engine._click` |
| discovery | `app/agent/tools._handle_navigate` | `app/agent/tools._handle_click` |

Each calls the corresponding policy function as its **first statement** and returns/raises on denial
before touching the page. The audit is a grep: `page.goto(`, `.click(`, `.press(`, `.fill(` may appear
under `app/` **only** inside those four functions. (`mock-bank/` and `tests/` are exempt.) Policy
functions are pure — no file, network, or environment access — so they are trivially unit-testable and
cannot be silently short-circuited by a config read.

### I4 — No secret ever reaches `artifacts/` or `evidence/`

**Statement:** No password, token, session cookie, API key, or full account number may appear in any
byte written under `artifacts/` or `evidence/`. `app.safety.policy.redact()` runs on every string
value before serialization, on both paths.

**How it's checked:**
1. **Chokepoint:** `open(...)` / `Path.write_*` targeting `artifacts/` or `evidence/` appears only in
   `app/artifact/storage.py` and `app/evidence.py`, and both call `redact()` on the payload before
   writing.
2. **Content sweep:** a test walks the entire `artifacts/` and `evidence/` trees and asserts (a) none of
   the current `.env` secret values appear as substrings, and (b) no match for the account-number and
   bearer-token patterns in `policy.py`.

**Redaction rules** (implemented in `policy.redact`, unit-tested in `test_policy.py`):
- Any exact substring equal to a known secret value → `«redacted:BANK_PASSWORD»` (named, so traces stay
  debuggable).
- Any dict key matching `(?i)pass|secret|token|api[_-]?key|authorization|cookie|session` → value replaced
  wholesale.
- `\b\d{6,}\b` → `••••` + last 4 digits.
- Applies recursively through dicts/lists, and to `Step.detail`, extracted output values, trace
  `detail` objects, and the discovery `messages.json` transcript.

**Screenshots:** password inputs render masked by the browser, so screenshots are safe — but any value
*read out of the DOM* (`input.value`, `textContent`) goes through `redact()` like anything else.
`env`/`input`/`extracted` bindings are stored in artifacts as **references**, never values —
`{"source":"env","key":"BANK_PASSWORD"}` — so a secret binding never puts a secret byte in the file.
`literal` bindings do store a value directly (that is the point of that source kind), which is exactly
why a `literal` binding is forbidden from being `secret` (see §6): the one binding kind that writes its
value into the artifact is the one kind I4 does not allow to carry a secret.

---

## 5. Typed results

`app/replay/errors.py`:

```python
Status = Literal["success", "needs_human", "policy_blocked", "failed"]
```

Four frozen pydantic models, each with a `status: Literal[...]` discriminator, and
`RunResult = Annotated[Success | NeedsHuman | PolicyBlocked | Failed, Field(discriminator="status")]`.
Every variant carries `run_id` and `flow_id` (added on Day 2 per WORKFLOW.md 2.2/3.4, on top of what
this section originally listed) plus `evidence_dir`, so a caller — or `scripts/reliability_run.py`
parsing `--json` output — never has to reconstruct either path from the run_id convention in §9.

| Result | Carries | Meaning |
|---|---|---|
| `Success` | `outputs: dict[str, str]`, `steps_completed`, `duration_ms`, `rung_stats: dict[str, int]` | Flow completed; `rung_stats` counts how many steps resolved at each `LocatorStrategy`, feeding Day 6's rung distribution. |
| `NeedsHuman` | `step_id`, `reason`, `tried: list[LocatorStrategy]`, `handoff_path` | Ladder exhausted on a resolvable-in-principle step. Recoverable by a human; `handoff_path` points at the `evidence/intervention/...` file (§12). |
| `PolicyBlocked` | `step_id`, `rule`, `detail` | Safety layer refused. **Never retried, never escalated to a human.** |
| `Failed` | `step_id \| None`, `error_class`, `message` | Everything else, including unexpected crashes. |

Prefer `match result:` with `typing.assert_never` in the default arm so adding a variant becomes a type
error rather than a silent fall-through. Exceptions are for *inside* a module; unions cross module
boundaries.

---

## 6. Flow artifact — canonical shape

`docs/artifact-spec.md` is normative and fuller; this is the shape to build against so Day 2 and Day 5
agree. Adding a `StepKind` means updating `schema.py`, `engine.py`, `docs/artifact-spec.md`, and tests
**in one commit**.

> **Reconciled with WORKFLOW.md 2.1 on Day 2** — the plan's field sketch (`navigate`/`assert_visible`,
> `timeout_ms`, env-only bindings) predates this file and disagreed with it in three places. Resolved:
> keep this file's naming (`goto`/`press`/`budget_ms`/`title`/`origin`/`created_at`), add the `on_fail`
> and `description` fields WORKFLOW.md called for (§12 already assumed `on_fail` existed — this was a
> real gap), and widen `Binding.source` to the four kinds below so a flow can chain an extracted value
> into a later step, not just read credentials from `.env`.

```json
{
  "schema_version": 1,
  "id": "get_savings_balance",
  "title": "Read the savings account balance",
  "origin": "http://127.0.0.1:8000",
  "created_at": "2026-08-17T14:25:30Z",
  "created_by": { "mode": "discovery", "run_id": "20260817T142530Z-9f3ab1", "model": "claude-opus-5" },
  "bindings": [
    { "name": "username", "source": "env", "type": "string", "key": "BANK_USERNAME", "secret": false },
    { "name": "password", "source": "env", "type": "string", "key": "BANK_PASSWORD", "secret": true }
  ],
  "outputs": ["savings_balance"],
  "steps": [
    { "id": "goto_login", "kind": "goto", "description": "Open the login page", "url": "/login",
      "budget_ms": 8000, "on_fail": "abort", "locators": [] },
    { "id": "fill_username", "kind": "fill", "description": "Enter the username",
      "binding": "username", "budget_ms": 8000, "on_fail": "abort",
      "locators": [
        { "strategy": "testid",   "value": "username" },
        { "strategy": "label",    "value": "Username" },
        { "strategy": "css",      "value": "#user" }
      ] },
    { "id": "open_savings", "kind": "click", "description": "Open the savings account detail page",
      "budget_ms": 8000, "on_fail": "handoff",
      "locators": [
        { "strategy": "role_name", "value": "Savings", "role": "link", "nth": 0 },
        { "strategy": "text",      "value": "Savings" },
        { "strategy": "css",       "value": "tr[data-account-type='savings'] a" },
        { "strategy": "coordinates", "value": "612,318", "viewport": { "w": 1280, "h": 720 } }
      ] },
    { "id": "read_savings_balance", "kind": "extract", "description": "Read the rendered balance",
      "output": "savings_balance", "budget_ms": 12000, "on_fail": "retry",
      "locators": [ { "strategy": "testid", "value": "balance-amount" } ] }
  ]
}
```

- `StepKind` ∈ `goto | click | fill | press | wait_for | extract`. Closed set. `press` carries a
  required `key` field (e.g. `"Enter"`); `goto` carries a required `url`; `fill` carries a required
  `binding` (a name declared in `Flow.bindings`); `extract` carries a required `output` (a name that
  must appear in `Flow.outputs` or be referenced by some `Binding.source == "extracted"`).
- Every `Step` carries `description` (required, plain English — the intent the model stated when this
  step was recorded, not a restatement of the kind) and `on_fail ∈ abort | retry | handoff`, default
  `"abort"`. `LocatorStrategy` ∈ `testid | role_name | label | text | css | coordinates`, and **the
  `locators` list must be stored in exactly that rank order** — the engine walks it front to back and
  does not re-sort. Enforce with a `@model_validator(mode="after")`.
- `role` is required iff `strategy == "role_name"`; `viewport` is required iff
  `strategy == "coordinates"`. `nth` disambiguates multiple matches.
- **Coordinates rung rules:** always last; skipped at replay if the live viewport differs from the
  recorded one by more than 10% in either dimension; **never used for a step whose action is on the
  destructive denylist**. A step whose only surviving rung is coordinates and fails the viewport check
  yields `NeedsHuman`, not a blind click.
- `budget_ms` is the whole-step budget. Per-rung budget is
  `rung_budget(remaining_ms, rungs_left) = max(300, remaining_ms // rungs_left)` — a pure function in
  `locators.py`, unit-tested independently of Playwright. The ladder aborts when `remaining_ms < 300`.
- **`Binding.source`** ∈ four kinds, each with its own required companion field:
  - `"env"` — `key` names an environment variable (via `app.config`); used for credentials. `secret`
    marks it for the redactor regardless of source.
  - `"input"` — resolved by the caller at invocation time (CLI `--input name=value`, or the discovery
    harness); the artifact only declares that the flow needs it, not where the value comes from. This
    is what makes a flow reusable with different inputs and no re-recording (see `docs/artifact-spec.md`).
  - `"extracted"` — `key` names another step's `output`; resolved from that step's result within the
    same run. A `Flow`-level validator confirms the referenced step exists and precedes the binding's
    use.
  - `"literal"` — `value` is a fixed constant stored directly in the artifact. **`secret` must be
    `false` for a literal binding** — a secret literal would put the real value in a committed JSON
    file, which is exactly what invariant I4 forbids. Reject this combination at validation time.
  - `type ∈ string | number`, default `"string"` — a hint for how the harness coerces the resolved
    value, not a redaction signal.
- Serialization: `json.dumps(flow.model_dump(mode="json", exclude_none=True), indent=2,
  ensure_ascii=False)` + trailing newline. Key order = field declaration order.
  `exclude_none=True` is why a `goto` step's JSON has no `binding`/`output`/`key` keys at all rather
  than carrying them as `null` — that's what makes the worked example above the literal output, not a
  simplification of it. Determinism doesn't require the opposite choice: the same `Flow` always
  produces the same bytes either way, so this fixes the null noise a strict "no exclude_none" reading
  would have on every kind-conditional field (`Step.url`/`binding`/`output`/`key`,
  `Locator.role`/`nth`/`viewport`, `Binding.key`/`value`) without giving up reproducibility.
- Filename must equal `flow.id` + `.json`; `storage.save_flow` validates this and refuses otherwise.

---

## 7. Anthropic API conventions (discovery path only)

- **Model:** `claude-opus-5`. Hard-coded as `MODEL` in `app/agent/agent.py`, echoed into
  `flow.created_by.model`. Never construct a model ID string at runtime.
- **Client:** `anthropic.Anthropic()` — zero-arg, resolves `ANTHROPIC_API_KEY` from the environment.
  Never pass a key literal.
- **Thinking:** `thinking={"type": "adaptive"}`. `budget_tokens` is **removed** on this model and
  returns 400. `output_config={"effort": "high"}`. Do not set `temperature`, `top_p`, or `top_k` —
  they also 400.
- **Loop:** a **manual** tool-use loop in `agent.py`, not `client.beta.messages.tool_runner`. Reason:
  the harness must intercept every tool call to harvest the locator ladder from the live DOM, write a
  trace line, and enforce policy *before* execution — plus replay must never depend on a beta SDK
  surface. Shape: `while True:` → `messages.create(...)` → append `response.content` **verbatim**
  (including thinking blocks — never edit or drop them) → if `stop_reason != "tool_use"` break → execute
  every `tool_use` block → return **all** `tool_result` blocks in a **single** user message. Cap
  iterations at `MAX_TURNS = 40` and fail closed.
- **`max_tokens`:** 8000, non-streaming. Turns are small; streaming adds nothing here.
- **Prompt caching:** the system prompt and tool list are frozen strings — no timestamps, no run_id, no
  f-string interpolation — and the last system block carries
  `cache_control={"type": "ephemeral"}`. The loop resends full history every turn, so this is the
  single highest-leverage cost optimization. Assert `usage.cache_read_input_tokens > 0` from turn 2 in
  the discovery trace.
- **No assistant prefill.** It returns 400 on this model. If you need structured output from the model,
  use `output_config.format` — but note the compiler never needs it, because **the model does not emit
  JSON**.
- **Errors:** catch the SDK's typed classes (`anthropic.RateLimitError`, `anthropic.APIStatusError`,
  `anthropic.APIConnectionError`) most-specific-first. Never string-match error messages.
- Tool results for failed tools still come back, with `is_error: True` — never drop a `tool_result`, or
  the next request is malformed.

---

## 8. CLI contract

```
python main.py discover --goal "<plain English goal>" --flow-id <snake_case> [--headed] [--max-turns N]
python main.py replay   --flow artifacts/<id>.json [--headed] [--json]
```

`main.py` holds argparse and result→exit-code mapping and nothing else. Exit codes:

| Code | Meaning |
|---|---|
| 0 | `Success` |
| 2 | `NeedsHuman` |
| 3 | `PolicyBlocked` |
| 4 | `Failed` |
| 1 | Unhandled exception — **an I2 violation**; CI asserts this never occurs |

`--json` prints `result.json` to stdout for scripting (`scripts/reliability_run.py` relies on this,
not on log parsing).

---

## 9. Run identity and evidence format

**`run_id`** = `<UTC compact timestamp>-<6 lowercase hex>`, e.g. `20260817T142530Z-9f3ab1`.
Generated once per run by `app.context.new_run_id()`. Sortable, and **contains no `:`** because
Windows forbids colons in path components — never use raw ISO-8601 in a filename.

Run directory: `evidence/{discovery|replay}/<run_id>/`. Screenshots:
`steps/NNN-<step_id>.png`, `NNN` zero-padded to 3, matching step index.

**`trace.jsonl`** — one JSON object per line, UTF-8, `\n` endings, append-only, written by
`app.evidence.TraceWriter`. Both paths emit the same schema so one analysis script reads both.

| Field | Type | Notes |
|---|---|---|
| `ts` | str | `2026-08-17T14:25:30.412Z` (UTC, ms precision) |
| `run_id` | str | |
| `mode` | `"discovery"` \| `"replay"` | |
| `seq` | int | monotonic from 1, per run |
| `event` | str | vocabulary below |
| `level` | `"info"` \| `"warn"` \| `"error"` | |
| `step_index` | int \| null | |
| `step_id` | str \| null | |
| `kind` | StepKind \| null | |
| `locator` | object \| null | the `{strategy, value, role?, nth?}` attempted or used |
| `attempt` | int \| null | rung ordinal, 1-based |
| `duration_ms` | int \| null | |
| `screenshot` | str \| null | path relative to the run dir |
| `detail` | object | free-form, **always passed through `redact()`** |

**Event vocabulary** (closed set — extend in `evidence.py` and `docs/artifact-spec.md` together):
`run_start`, `run_end`, `policy_check`, `policy_block`, `step_start`, `locator_attempt`,
`locator_resolved`, `step_ok`, `step_fail`, `extract`, `handoff_request`, `handoff_resume`,
`model_turn` (discovery only; carries token usage in `detail`).

---

## 10. Coding conventions

**Python 3.11.** `requires-python = ">=3.11"`, ruff `target-version = "py311"`. Use `X | None`, not
`Optional[X]`; `list[str]`, not `List[str]`.

**Playwright: the sync API. Everywhere.** Justification, since this is the one call that shapes every
file: the FastAPI mock bank runs in a **separate OS process** (`make bank`, or the `bank_server`
subprocess fixture), so there is no in-process event loop for the driver to coexist with — the usual
reason to reach for async Playwright does not apply here. Sync also keeps the agent loop readable
top-to-bottom, which matters because a reviewer reads `agent.py` linearly. And Playwright's sync API
**cannot be called from inside a running asyncio loop**, so choosing async for the driver would force
async through `engine`, `locators`, `handoff`, `main.py`, and every test, for zero benefit. The one
place async would pay off is parallel replays in `reliability_run.py` — run those **sequentially**
(N=20 takes ~2 minutes; sequential runs also give cleaner per-run timing) or with
`concurrent.futures.ProcessPoolExecutor` if it ever matters.

> `pytest-asyncio` is in `requirements.txt` as specified, with `asyncio_mode = strict` in `pytest.ini`.
> No test should need it. **If you reach for `@pytest.mark.asyncio`, you have probably introduced async
> Playwright — stop and reconsider.** FastAPI endpoint tests use the sync `fastapi.testclient.TestClient`.

**Pydantic v2.** On every artifact model: `model_config = ConfigDict(extra="forbid", frozen=True)`.
`extra="forbid"` turns a schema drift into a loud `ValidationError` at load time instead of a silently
dropped field at replay time; `frozen=True` means a step can't be mutated mid-run. Enums subclass
`(str, Enum)` so they serialize as plain strings. No field aliases — the JSON key is the Python name.
Use `@field_validator` for scalar checks (origin is an absolute `scheme://host[:port]`, `budget_ms > 0`)
and `@model_validator(mode="after")` for cross-field rules (ladder ordering, `role` required for
`role_name`, `viewport` required for `coordinates`, `binding` name resolves against `flow.bindings`).
Parse with `Flow.model_validate_json(text)`; never `json.loads` into a dict and index it.

**Tests.** One `test_<module>.py` per module under test. Function names read as sentences:
`test_ladder_falls_through_to_css_when_testid_missing`. Arrange-act-assert, no shared mutable state
between tests, no test order dependence. `pytest.ini`: `testpaths = tests`,
`addopts = -q --strict-markers`, declared markers `slow` and `browser`. No test reaches the public
internet — the only network endpoint is the local mock bank; locator-drift tests use `file://` URLs
against `tests/fixtures/*.html` so they are fast and hermetic. `tests/test_replay_e2e.py` replays the
**committed** `artifacts/get_savings_balance.json`, which makes the artifact itself a regression test.

**Docstrings and comments.** Every module gets a one-line docstring naming its role and, for anything
in the AI-free set, stating so (`"""Locator ladder resolution. AI-free (see CLAUDE.md I1)."""`).
Function docstrings **only when the WHY is not obvious from the signature** — never restate parameter
types, never write `"""Returns the flow."""`. Comments explain *why*, not *what*: `# 800ms artificial
delay on the balance render — the ladder needs a real wait, not a retry loop` earns its place;
`# loop over steps` does not. No commented-out code, no TODOs without an owner and a WORKFLOW day.
Reviewers read this code — a wrong comment is worse than none.

**Other.** Full type hints on every public signature; no `Any` in a public signature. Functions under
~40 lines; if an executor grows past that, the step kind is doing two things. `print()` only in
`main.py` and `scripts/`; everywhere else `logging.getLogger(__name__)` — the JSONL trace is the
machine record, logging is the human one, and they are not interchangeable. Line length 100
(ruff + black agree). Ruff `select = ["E", "F", "I", "UP", "B"]` — `I` means imports are
ruff-sorted, so never hand-order them.

**Commits.** One commit per WORKFLOW task, message `<day>/<task>: imperative summary`. `make lint` and
`make test` pass before every commit. `/gate` runs at the end of each day.

---

## 11. Configuration

`.env.example` (committed) documents exactly these, and `app/config.py` is the only consumer:

| Var | Example | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Discovery only. Replay must work with it unset. |
| `BANK_BASE_URL` | `http://127.0.0.1:8000` | No trailing slash. |
| `BANK_USERNAME` | `demo` | |
| `BANK_PASSWORD` | `demo1234` | Registered with the redactor at startup. |
| `ALLOWED_ORIGINS` | `http://127.0.0.1:8000` | Comma-separated, **exact** `scheme://host:port` match. No wildcards, no globbing, no suffix matching. |

`config.py` exposes a frozen pydantic `Settings` via `get_settings()` (`functools.lru_cache`), calling
`load_dotenv()` once. `policy.py` receives the allowlist as an **argument** so it stays pure —
`check_navigation(url, allowed_origins)`, not `check_navigation(url)` reading globals. Tests construct
`Settings` directly or `monkeypatch.setenv`; **no test reads `.env`**.

`.gitignore` covers `__pycache__/`, `*.py[cod]`, `.venv/`, `venv/`, `.env`, `.pytest_cache/`,
`.ruff_cache/`, `.mypy_cache/`, `playwright-report/`, `test-results/`, `*.egg-info/`.
It must **not** contain a blanket `*.json`, `*.png`, or `*.jsonl` rule — those would silently swallow
`artifacts/` and `evidence/`, which are deliverables. After touching `.gitignore`, run
`git check-ignore -v artifacts/get_savings_balance.json` and confirm it reports nothing.

---

## 12. Handoff protocol

When replay exhausts a ladder, `app/intervention/handoff.py` writes
`evidence/intervention/<run_id>-<step_id>.json` containing the step, every strategy tried, a
screenshot path, the current URL, and a human-readable ask. It returns `NeedsHuman` — it does **not**
block, prompt on stdin, or retry from within `run_flow`.

On resume, the handoff module **revalidates state before continuing**: it re-checks the origin against
the allowlist and confirms an expected anchor element for the current step is present. The browser may
have moved anywhere while a human had the keyboard; resuming on an unverified page is how a replay
silently does the wrong thing on the wrong account. Failed revalidation → `Failed`, not a retry.
`PolicyBlocked` never becomes a handoff — a blocked action is a decision, not an obstacle.
