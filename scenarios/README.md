# Controlled failure scenarios

These defects are for the self-healing demo. They have a known broken
behavior and a known correct outcome. They are **not** applied on `main`.

Use the injector, which creates a disposable Git worktree:

```powershell
.\.venv\Scripts\python.exe scripts\inject_bug.py --list
.\.venv\Scripts\python.exe scripts\inject_bug.py A
cd .worktrees\scenario-a
..\..\.venv\Scripts\python.exe -m pytest
```

Clean up when finished:

```powershell
python scripts/inject_bug.py --cleanup A
python scripts/inject_bug.py --cleanup-all
```

| Scenario | Injected defect | Expected detection | Correct outcome |
| -------- | --------------- | ------------------ | --------------- |
| A | `OrderResponse` serializes `amount` instead of `total` | Contract violation on `GET /orders/{id}` | Response includes `total` and matches `contracts/order.json` |
| B | Stored order totals are reduced by 10% | Incorrect invoice values and failed business assertions | Order 101 total is `499.0`; INV-101 total is `548.9`; revenue is `823.9` |
| C | Invoice totals omit tax (`total = amount`) | Downstream regression in invoices and revenue reports | Invoice totals include tax; revenue stays `823.9` |

`--in-place` is only for a checkout that is already a demo branch. The script refuses to mutate `main` or `master` in place.
