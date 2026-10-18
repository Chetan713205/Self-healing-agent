Build a Self-Healing API Agent: it monitors live endpoints against their contract, and when a change breaks one, it diagnoses the root cause, repairs the code in a sandbox, verifies that no other endpoints regress, and either proposes the fix for approval or rolls back. The detect/repair/verify layers are pluggable so it can extend to other domains. POC ready early next week.

## The simple version

You have an app with a REST API. Somewhere there's a **contract**, a written description of what each endpoint should return. The agent keeps checking the live API against that contract. When they stop matching, it investigates and repairs.

## A concrete example

Your app has this endpoint:

```
GET /orders/101
```

**Contract (what it should return):**
```json
{ "id": 101, "total": 499.0, "status": "shipped" }
```

**Then a developer changes the code.** They rename `total` to `amount` in the order-building function, and forget that other parts of the system expect `total`.

Now the live API returns:
```json
{ "id": 101, "amount": 499.0, "status": "shipped" }
```

### What the agent does

1. **Detect.** The probe calls `/orders/101` and compares the response to the contract. It finds that `total` is missing and `amount` is unexpected. Alert raised.

2. **Diagnose.** The agent collects evidence: the failing response, the recent git diff, and the failing test. It reads the diff and concludes: "Commit abc123 renamed `total` to `amount` in `orders.py`, line 42. That broke the contract."

3. **Repair.** In a safe copy of the code (never your main branch), the agent edits `orders.py` to return `total` again.

4. **Verify.** It reruns the probe and all the tests on the patched copy. Everything passes, and no other endpoint broke.

5. **Propose.** It produces a report for a human:
   - Root cause: field renamed in commit abc123
   - Fix: a one-line diff
   - Evidence: all 24 tests and 4 endpoint checks passing
   - Button: **Approve and merge**

6. **If it can't fix it:** after 3 failed attempts it reverts the bad commit and alerts a person with its diagnosis.

## One decision you'll need to make

When a field is renamed, there are two possible "fixes":

- **Restore the old name** so the API matches the contract (what I described above).
- **Update the contract** because the rename was intentional.

The agent can't always know which one is right. For your demo, keep it simple: **the contract is the source of truth, so the agent restores the old behavior.** You can mention the intentional-change case as a future improvement, since it's a good point to raise with your boss.

## In one sentence

The agent is a loop that **checks the API against its contract, finds the code change that broke it, fixes it in a sandbox, proves the fix works, and asks a human to approve.**

If this makes sense, I can scaffold the starter project (the sample FastAPI app, a script that injects this exact bug, and the probe) so you can see the loop run today.


## Flow Diagra
1. Developer changes the code (or you run inject_bug.py for the demo)
2. You run one command in the terminal:
      cursor-agent -p --force "The API may be broken. Use the guardian tools to check, fix and verify it."
3. Cursor agent starts and calls the MCP tool check_api_health()
4. MCP probes the live API, compares it to the contract, returns what is broken
5. Agent calls get_recent_changes() to see which commit caused it
6. Agent reads and edits the code to fix the root cause
7. Agent calls run_targeted_tests(), then run_full_tests(); MCP runs pytest and the probe again
      - if they fail, the agent retries (MCP allows 3 attempts)
      - after 3 failures, MCP reverts the change and escalates to a human
8. When everything passes, agent calls submit_fix_report()
9. MCP saves the report (root cause, diff, test evidence) to a file
10. Human reviews the report and approves the merge

## Phase 2: sample API

The repository includes a small FastAPI application with three connected business
functions. Orders are the source of truth for order totals, invoice calculations
derive amount, tax, and total from those orders, and the revenue report aggregates
the issued invoice totals.

### Start the API

From the repository root, install the dependencies and start the development server:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation or
`http://127.0.0.1:8000/openapi.json` for the generated OpenAPI document. Sample
endpoints include `POST /orders`, `GET /orders/101`, `GET /invoices/INV-101`, and
`GET /reports/revenue`. Machine-readable response contracts live in `contracts/`.

### Run baseline tests

In another terminal, activate the virtual environment and run:

```powershell
python -m pytest
```

The unit tests cover the business services. Integration tests exercise the API,
validate responses against their JSON Schema contracts, and check the OpenAPI
endpoint definitions.

### Inject a controlled failure (demo only)

Do not apply these defects on `main`. The injector creates a disposable Git
worktree and a `demo/failure-*` branch:

```powershell
.\.venv\Scripts\python.exe scripts\inject_bug.py --list
.\.venv\Scripts\python.exe scripts\inject_bug.py A
cd .worktrees\scenario-a
..\..\.venv\Scripts\python.exe -m pytest
```

| Scenario | Injected defect | Expected detection |
| -------- | --------------- | ------------------ |
| A | Order response field `total` renamed to `amount` | Contract violation |
| B | Order totals silently reduced by 10% | Incorrect invoice values / failed business assertions |
| C | Shared invoice totals omit tax | Downstream revenue-report regression |

Restore the workspace with `python scripts/inject_bug.py --cleanup A` or
`--cleanup-all`. Details live in `scenarios/README.md`.

## Phase 3: MCP server

The MCP server is separate from the FastAPI application. Cursor Agent reasons
and edits code. This server only returns evidence: live schema checks, Git
diffs, an import-graph impact map, pytest results, and a saved repair report.

Copy `mcp_server/` into another FastAPI repository and it discovers that
app. It reads route declarations and imports from the code, so it does not
need a handwritten endpoint table. JSON files in `contracts/` are optional:
a file is used when its `title` matches a response schema. Otherwise the
OpenAPI response schema is the contract. Path parameters are filled from
schema examples; a route with no example is reported as skipped.

| Tool | Responsibility |
| --- | --- |
| `check_api_health` | Call the local API and compare each probe with its contract |
| `get_contract_violations` | Return missing fields, unexpected fields, wrong types, and schema mismatches |
| `get_recent_changes` | Return recent commits, the latest diff, and any uncommitted diff |
| `analyze_impact` | Map changed files to affected endpoints and tests |
| `run_targeted_tests` | Run the node ids selected by impact analysis |
| `run_full_tests` | Run the unit and integration suites |
| `get_failure_evidence` | Collect failing tests, contract violations, and the latest change |
| `verify_repair` | Run contract probes, targeted tests, then the full suite, and set `accepted` |
| `submit_fix_report` | Save the diagnosis and patch summary. The status comes from `verify_repair` |

`analyze_impact` follows imports. A module that imports changed code is
downstream, and so are the routes and tests that reference it. That chooses
which tests to run first. `verify_repair` still runs the full suite, and a
repair is `pending_approval` only when the contract checks and both test
runs pass. Text supplied by the agent is stored as notes, not as the verdict.

Start the API in one terminal, then the checks can reach `http://127.0.0.1:8000`.
The server process itself is:

```powershell
.\.venv\Scripts\python.exe -m mcp_server
```

That command speaks MCP over stdin/stdout and writes logs to stderr. Cursor
loads it from `.cursor/mcp.json`. A project rule tells the agent to diagnose
with these tools and to treat `verify_repair` as the pass/fail verdict.