# Pocketful stage 1 — plan (this run)

**Start:** 2026-10-05 13:43:00 UTC (approx, when coordinator intake completes)  
**Finish:** (open)

**Planned time:** 1 hour (this run). Previous band got isolated 147/147 and claimed stage 1 at commit `037d00b`. This run: verify that commit against spec, accept if harness+suite pass in isolated mode, or fix and retry.

**Constraint:** If stage 1 is not accepted after 1.5 hours, accept the best revision that builds and claims stage 1 in isolated mode; record gaps in REQUIREMENTS.md and stop.

## Goal

Verify stage-1 HTTP wallet/payments service at `C:\Development\darkfactory\band-work\result\stage-1` meets every line of REQUIREMENTS.md in isolated harness mode, claim stage 1, and confirm no stage-2+ leak.

## Inheritance from previous attempt

- REQUIREMENTS.md (R1–R159, D1–D29) is complete and correct per spec
- Source code, Dockerfile, RUN.md exist and passed isolated 147/147 at commit `037d00b`
- Acceptance suite exists at `C:\Development\darkfactory\band-work\result\stage-1\acceptance`
- Previous plan logged in PLAN-attempt-1.md

## Decisions (re-affirmed)

- Same store design as previous attempt (in-memory, single-process, one mutex, D8)
- Idempotency keyed by (user_id, method, path, key) to isolate per-path claims (R57–R68)
- Settlement membership includes `settlement_id` on payments (D2)
- No stage-2+ fields in responses (D10)
- Previous code passed isolated 147/147; trust that and verify independently

## Work items

| ID | Owner | Covers | Evidence |
|---|---|---|---|
| W1 | reviewer | Verify `037d00b` in isolated harness + acceptance suite | Harness: 147/147, `claimed stage: 1`, stage-2 FAIL expected; Suite: all pass |
| W2 | coordinator | Accept W1 commit or dispatch fix | If W1 accept, stage 1 done; else forward defects to implementer and retry |

## Checks

From `C:\Development\darkfactory\dark-factory-wearedevs`:

Harness (isolated mode, no outbound):
```
.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage 1 --mode isolated --out C:\Development\darkfactory\band-work\checks\s1-<unique-name>
```

Last line must be `claimed stage: 1`. Suite 2 overshoot expected FAIL.

Acceptance suite:
```
python C:\Development\darkfactory\band-work\result\stage-1\acceptance\run.py
```

All tests must pass.

## Log

- (intake) — coordinator read specs, reviewed previous PLAN-attempt-1.md and commit history. Inherited REQUIREMENTS.md and source at `037d00b`. Waking seats now.
