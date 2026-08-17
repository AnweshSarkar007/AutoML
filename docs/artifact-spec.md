# Flow artifact specification

This is the normative spec for the JSON flow artifact — the thing `app/agent/agent.py` compiles on
Day 4 and `app/replay/engine.py` executes on Day 3. CLAUDE.md §6 carries a summary of this file for
quick reference; where the two disagree, this file wins. The implementation is
[`app/artifact/schema.py`](../app/artifact/schema.py) — every rule below has a corresponding
`pydantic` validator there and a test in [`tests/test_schema.py`](../tests/test_schema.py).

A flow artifact is a `schema_version: 1` JSON document with six top-level fields: `id`, `title`,
`origin`, `created_at`, `created_by`, `bindings`, `outputs`, `steps`. Filename is always
`<id>.json`; `app.artifact.storage.save_flow` refuses to write it under any other name.

## Why `bindings` is a separate list from `steps`

A `Step` never embeds a literal credential or a hardcoded search term. It references a *binding
name*, and the `Flow.bindings` list separately declares where that name's value comes from. That
split exists so the same recorded flow can run with different inputs without ever being
re-discovered: `get_savings_balance.json` recorded once against one demo account replays correctly
against any account, because "which username" lives in `bindings`, resolved fresh at replay time —
not baked into the `fill_username` step itself. It's also what makes the artifact safe to commit:
a `Step` is pure structure and selectors, so nothing about *whose* data flows through it needs
redacting; only `Binding` values (and only some of them — see below) are secret-shaped.

## `Binding`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | Referenced by `Step.binding` (fill steps) or by another binding's `key` (`source: extracted`). |
| `source` | `env \| input \| extracted \| literal` | See below. |
| `type` | `string \| number`, default `string` | A coercion hint for the harness, not a redaction signal. |
| `key` | `str \| None` | Required iff `source` is `env` (an environment variable name) or `extracted` (another step's `output` name). Forbidden otherwise. |
| `value` | `str \| None` | Required iff `source == "literal"`. Forbidden otherwise. |
| `secret` | `bool`, default `false` | Marks the value for `app.safety.policy.redact()` regardless of source. **Forbidden when `source == "literal"`** — see below. |

Four sources, four different places the actual value comes from at run time:

- **`env`** — read from an environment variable via `app.config` at replay time. This is how
  `get_savings_balance.json` supplies `BANK_USERNAME`/`BANK_PASSWORD`: the artifact says *which*
  env var, never the value.
- **`input`** — supplied by whoever invokes the run (a CLI `--input name=value` flag today; the
  discovery harness tomorrow). The artifact only declares that the flow needs an input by this
  name — it has no opinion on where the caller gets it. This is the general form of "same flow,
  different inputs."
- **`extracted`** — resolved from another step's result within the *same* run. `key` names that
  step's `output`; a `Flow`-level validator confirms some step actually produces it. This is how a
  flow chains steps: extract an account id on step 3, then fill a field with it on step 5.
- **`literal`** — a fixed constant, stored directly in the artifact as `value`. Because this is the
  one source kind that writes its resolved value straight into a committed JSON file, **a literal
  binding can never be `secret: true`** — schema validation rejects that combination outright. If a
  value needs to be secret, it cannot also be a compile-time constant in the artifact; it has to be
  `env` (or, less commonly, `input`).

## `Step`

Every step has: `id` (unique within the flow), `kind`, `description` (required — the plain-English
intent the model stated when this step was recorded; not a restatement of `kind`), `budget_ms`
(whole-step timeout budget, `> 0`), `on_fail` (`abort | retry | handoff`, default `abort`), and
`locators` (the ladder — empty only for `goto`, since navigation has nothing to locate).

`kind` is a closed set, and each kind has exactly one companion field that only it uses (present iff
that kind, forbidden otherwise):

| `kind` | Companion field | Meaning |
|---|---|---|
| `goto` | `url` | Navigate to this URL (relative to `Flow.origin` or absolute). |
| `click` | — | Click the resolved element. |
| `fill` | `binding` | Fill the resolved element with the named binding's resolved value. |
| `press` | `key` | Press a keyboard key (e.g. `"Enter"`) — no element resolution beyond focus. |
| `wait_for` | — | Wait for the ladder to resolve and stop; used when a step exists only to synchronize timing (e.g. the mock bank's 800ms balance-render delay). |
| `extract` | `output` | Read the resolved element's text and store it under this output name — must appear in `Flow.outputs` or be referenced by some `Binding.source == "extracted"`, or both. |

`on_fail` controls what the replay engine does when every locator rung fails: `abort` stops the run
(`Failed`), `retry` retries the step with backoff before giving up, `handoff` goes straight to
`app.intervention.handoff` (`NeedsHuman`) without retrying. `PolicyBlocked` never goes through
`on_fail` at all — a policy denial is a decision, not a resolution failure (see CLAUDE.md I3/§12).

## `Locator` and the ladder

`strategy` is one of `testid | role_name | label | text | css | coordinates`, and a step's
`locators` list **must be in exactly that rank order**, with no repeated strategy — the replay
engine walks front to back and does not re-sort or retry out of order. `role` is required iff
`strategy == "role_name"` (and forbidden otherwise); `viewport` is required iff
`strategy == "coordinates"` (and forbidden otherwise). `nth` optionally disambiguates multiple
matches for any strategy.

`coordinates` is always last when present, is skipped at replay if the live viewport differs from
the recorded `viewport` by more than 10% in either dimension, and is never attempted for a step
whose action is on the safety denylist — a step whose only surviving rung is `coordinates` and
fails the viewport check yields `NeedsHuman`, never a blind click.

## Annotated example

The reference flow, `artifacts/get_savings_balance.json`, hand-written for Day 2's gate and later
reproduced by the Day 4 discovery agent unchanged:

```json
{
  "schema_version": 1,
  "id": "get_savings_balance",
  "title": "Read the savings account balance",
  "origin": "http://127.0.0.1:8000",
  "created_at": "2026-08-17T14:25:30Z",
  "created_by": { "mode": "discovery", "run_id": "20260817T142530Z-9f3ab1", "model": "claude-opus-5" },
  "bindings": [
    { "name": "username", "source": "env", "key": "BANK_USERNAME", "secret": false },
    { "name": "password", "source": "env", "key": "BANK_PASSWORD", "secret": true }
  ],
  "outputs": ["savings_balance"],
  "steps": [
    { "id": "goto_login", "kind": "goto", "description": "Open the login page", "url": "/login.html",
      "budget_ms": 8000, "locators": [] },

    { "id": "fill_username", "kind": "fill", "description": "Enter the username",
      "binding": "username", "budget_ms": 8000,
      "locators": [
        { "strategy": "testid", "value": "username" },
        { "strategy": "label",  "value": "Username" },
        { "strategy": "css",    "value": "#username" }
      ] },

    { "id": "fill_password", "kind": "fill", "description": "Enter the password",
      "binding": "password", "budget_ms": 8000,
      "locators": [
        { "strategy": "testid", "value": "password" },
        { "strategy": "label",  "value": "Password" },
        { "strategy": "css",    "value": "#password" }
      ] },

    { "id": "submit_login", "kind": "click", "description": "Submit the login form",
      "budget_ms": 8000,
      "locators": [
        { "strategy": "testid", "value": "login-submit" },
        { "strategy": "role_name", "role": "button", "value": "Log in" }
      ] },

    { "id": "open_savings", "kind": "click", "description": "Open the savings account detail page",
      "budget_ms": 8000, "on_fail": "handoff",
      "locators": [
        { "strategy": "role_name", "role": "link", "value": "Savings" },
        { "strategy": "text", "value": "Savings" }
      ] },

    { "id": "wait_for_balance", "kind": "wait_for", "description": "Wait for the balance to render",
      "budget_ms": 3000,
      "locators": [ { "strategy": "testid", "value": "account-balance" } ] },

    { "id": "read_balance", "kind": "extract", "description": "Read the rendered balance",
      "output": "savings_balance", "budget_ms": 3000, "on_fail": "retry",
      "locators": [ { "strategy": "testid", "value": "account-balance" } ] }
  ]
}
```

Notes on the choices this flow makes, since they're not obvious from the JSON alone:

- `fill_username`/`fill_password` list `testid` first — the mock bank's login page is the "easy"
  page (CLAUDE.md, WORKFLOW.md Day 1.2), so the ladder resolves at rung 1 every time. `label` and
  `css` exist as documented fallbacks, exercised only if the login page's testids ever drift.
- `open_savings` has **no `css` or `coordinates` rung at all**. The dashboard deliberately assigns
  no `data-testid` to account rows and reshuffles row `id`s every session (WORKFLOW.md Day 1.3), so
  any CSS selector built from this page would be stale by the next login — there is nothing durable
  to put in that rung. `role_name` and `text` (both keyed on the visible account name, which is the
  one thing that *is* stable) are the only real options; `on_fail: "handoff"` reflects that if both
  of those somehow fail, blind coordinates would be actively dangerous on a page whose layout can
  legitimately vary by account count.
- `wait_for_balance` exists as its own step, separate from `read_balance`, so the 800ms artificial
  render delay (WORKFLOW.md Day 1.4) is paid once by an explicit wait rather than by giving every
  subsequent step a padded budget. `read_balance` still carries `on_fail: "retry"` as a second line
  of defense against timing flakiness.

## Serialization and versioning

`app.artifact.storage.save_flow` writes
`json.dumps(flow.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=False)` plus a
trailing newline. Field order matches declaration order in `schema.py`; `exclude_none=True` is why a
`goto` step's JSON has no `binding`/`output`/`key` keys at all rather than carrying them as `null` —
the same `Flow` object always produces the same bytes, so artifacts diff cleanly in git regardless.

`schema_version` is currently always `1`. `app.artifact.storage.load_flow` rejects any other value
with a clear error before attempting to parse the rest of the document — a version bump is a
deliberate, visible event, never a silent best-effort coercion. Adding a new `StepKind` or changing
what a source kind on `Binding` requires is a schema change and must land in `schema.py`,
`engine.py`, this file, and the tests **in the same commit** (CLAUDE.md §6).
