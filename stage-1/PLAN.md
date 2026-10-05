# Pocketful four-stage build — plan (this run)

**Start:** 2026-10-05 13:46 UTC  
**Finish:** (open)

**Total wall-clock budget:** 9 hours  
**Planned allocation:**
- Stage 1: 1 hour (existing service from `037d00b`, verify in isolation)
- Stage 2: 2 hours (browser UI + authorizations/holds)
- Stage 3: 2 hours (statements + corrections)
- Stage 4: 2 hours (refunds + batch corrections)
- Reserve: 2 hours for rework and final report

**Overflow rule:** If a stage exceeds 1.5× planned time, accept best-builds-and-claims revision, record remaining gaps in REQUIREMENTS.md, and move on.

## Overall strategy

Each stage inherits every prior stage's source, Dockerfile, RUN.md and acceptance suite. Stage N's REQUIREMENTS.md, PLAN.md and acceptance/ folder live inside stage-N/; they must not break the Docker build.

Handoff cycle per increment:
1. @implementer: builds and submits commit
2. @reviewer: verifies in isolated harness mode + runs acceptance suite
3. @coordinator: accepts or forwards defects back to @implementer

Once a stage is accepted by @reviewer at a specific commit, that stage is locked. The next stage begins as a copy of the previous, with that stage's additions.

## Stage 1: verify existing service

**Goal:** Verify stage-1 HTTP API service at commit `037d00b` meets REQUIREMENTS.md (R1–R159, D1–D29) in isolated harness and acceptance suite; claim stage 1; confirm no stage-2+ leak.

**Inheritance:**
- REQUIREMENTS.md complete and correct per spec (stage-1.md)
- Service source, Dockerfile, RUN.md exist at `037d00b`
- Acceptance suite in place

**Handoff to @reviewer:**
- Commit hash: `037d00b`
- Isolated harness: 147/147 claimed and expecting to pass
- Acceptance suite: expecting all pass
- Check commands and acceptance suite path provided below

**Evidence of accept:**
- Harness isolated: last line `claimed stage: 1`, stage-2 probe fails as expected
- Acceptance suite: all tests pass
- No stage-2+ API fields in responses (D10)

---

## Stage 2: browser UI + authorizations

Once stage 1 is accepted:
- Copy stage-1/ to stage-2/, delete .git if present
- Extend with browser UI routes and authorization/capture endpoints per stage-2.md
- New REQUIREMENTS.md adds stage-2 browser/auth rules (appended or merged)
- New PLAN.md and acceptance suite in stage-2/
- Handoff to @implementer: full spec text, requirements, check commands

**Planned work:**
- `/`, `/requests`, `/split`, `/signup`, `/login` routes returning HTML for `Accept: text/html`
- `data-testid` attributes per stage-2 spec
- `GET /me` returns `balance`, `total`, `available`, `held`
- `POST /authorizations`, `POST /authorizations/{id}/capture` idempotent write paths
- `authorization_ttl_seconds` fixture field
- Fixture validation for `authorizations` array
- Export/import preserve authorizations
- Browser form decimal-to-minor-units conversion
- Idempotency and replay semantics

---

## Stage 3: statements + corrections

Once stage 2 is accepted:
- Copy stage-2/ to stage-3/
- Extend with historical queries and payment corrections per stage-3.md
- REQUIREMENTS.md adds stage-3 rules
- New PLAN.md and acceptance suite in stage-3/

**Planned work:**
- `GET /me?as_of=<instant>` historical balance queries
- `GET /statement?from=<instant>&to=<instant>` with pagination and snapshot tokens
- `POST /payments/{payment_id}/corrections` single-payment corrections
- `GET /payments/{payment_id}/revisions` revision history
- Seeded `created_at` in fixtures for payments
- Concurrency: concurrent corrections on same revision fail atomically
- Export/import preserve corrections and snapshots

---

## Stage 4: refunds + batch corrections

Once stage 3 is accepted:
- Copy stage-3/ to stage-4/
- Extend with refunds and batch corrections per stage-4.md
- REQUIREMENTS.md adds stage-4 rules
- New PLAN.md and acceptance suite in stage-4/

**Planned work:**
- `POST /payments/{payment_id}/refunds` refund endpoint
- `POST /correction-batches` batch correction operator endpoint
- Refund immutability rules and constraints
- Batch completion rules: all members of a settlement corrected together
- Correction history and settlement membership preservation
- Export/import preserve refunds and batch corrections

---

## Checks and handoff details

### Harness (isolated mode, no outbound network)

From `C:\Development\darkfactory\dark-factory-wearedevs`:

```bash
.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage N --mode isolated --out C:\Development\darkfactory\band-work\checks\sN-<unique-name>
```

Last line must be `claimed stage: N`.  
Stage N+1 probe (overshoot) expected to FAIL.  
No 5xx responses under load.

### Docker prerequisites

Before starting a check: `docker ps` to confirm no `df-...` containers running (another seat's check in progress). Wait max 5 minutes if needed; checks take 1–3 minutes.

Run once per session (not per check): `.venv\Scripts\python.exe -m playwright install chromium`

### Acceptance suite

Each stage-N includes `acceptance/run.py` or equivalent. All tests must pass.

### Handoff to @tester and @implementer

Specs, requirements, check commands, acceptance suite path, and work-item sequence provided in dedicated handoffs. Seats see only messages directed to them. Handoff includes spec text verbatim (not references).

---

## Log

- **(intake)** — Coordinator read all four stage specs (stage-1.md through stage-4.md), reviewed REQUIREMENTS.md (R1–R159 complete), inherited service at `037d00b` which passed isolated 147/147 in prior band. Archived PLAN.md to PLAN-attempt-2.md. Writing fresh four-stage plan and waking seats now.
