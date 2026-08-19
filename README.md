
Browser workflows are usually automated one of two ways: hand-written scripts that break the
moment a `div` moves, or an LLM agent that re-reasons through the same click-path on every single
run, at every run's latency and cost. Cowpath does neither. An agent discovers a workflow once,
by actually driving a browser against the target site; the discovery is then compiled into a
deterministic artifact that replays with **zero further AI calls**, resilient to DOM drift because
each step carries a ranked ladder of ways to find its element rather than one brittle selector.

## The three-phase model

1. **Discover once** — an LLM agent (Anthropic API + Playwright) is given a goal in plain English
   and drives a live browser interactively, one tool call at a time, until the goal is met.
2. **Compile artifact** — the harness, not the model, turns that session into a JSON *flow*: an
   ordered list of steps, each carrying a locator ladder (`testid > role_name > label > text > css
   > coordinates`) harvested from the live DOM at the moment the step succeeded. The model
   contributes sequence and intent; the DOM contributes the selectors.
3. **Replay deterministically** — a pure Playwright engine reads the artifact and re-executes it
   with no AI involvement, walking the ladder rung by rung until one resolves. A safety layer
   (origin allowlist, destructive-action denylist, secret redaction) gates both paths, and a
   human-handoff mechanism takes over when replay genuinely can't resolve a step.

## Directory map

| Path | What lives there |
|---|---|
| `app/artifact/` | Flow/Step/Locator schema and JSON storage |
| `app/replay/` | The AI-free replay engine and locator ladder resolver |
| `app/agent/` | Discovery loop, tool definitions, and the DOM-harvest compiler |
| `app/safety/` | Origin allowlist, action denylist, secret redaction (pure functions) |
| `app/intervention/` | Human handoff on unresolved steps |
| `mock-bank/` | The target app being automated — a deliberately awkward fake bank |
| `artifacts/` | Committed flow artifacts |
| `evidence/` | Screenshots and JSONL traces from discovery and replay runs |
| `tests/` | pytest suite |
| `scripts/` | `reliability_run.py` — repeated-replay measurement harness |
| `docs/` | Artifact format specification |

Full tree with placement rationale: [CLAUDE.md §2](CLAUDE.md#2-directory-tree).

## Setup

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY, BANK_USERNAME, BANK_PASSWORD
make install                 # pip install -r requirements.txt + playwright install chromium
make lint
make test
```

Run the mock bank locally:

```bash
make bank                    # http://127.0.0.1:8000
```

Discover and replay a flow (once the CLI exists — see WORKFLOW.md Day 4/5):

```bash
make discover GOAL="Read the savings account balance" FLOW_ID=get_savings_balance
make replay
```

## Results

TODO — filled in as Day 6 reliability data lands.

- Reliability numbers: `evidence/reliability.md`
- Full write-up: [REPORT.md](REPORT.md) (TODO — Day 7)
