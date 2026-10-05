# Pocketful four-stage build — coordination plan (this run)

**Start:** 2026-10-05 20:34 UTC  
**Finish:** (open)  
**Wall-clock budget:** 6.5 hours (until 03:04 UTC 2026-10-06)  
**Planned allocation:**
- Stage 1: 0.5 hours (verify existing at 037d00b in isolated mode)
- Stage 2: 1.5 hours (fix browser UI and authorizations; 2/35 tests passing before this run)
- Stage 3: 1.5 hours (add statements and corrections)
- Stage 4: 1.5 hours (add refunds and batch corrections)
- Reserve: 1 hour for rework and final report
- **Stop new work:** when 45 minutes remain (~02:19 UTC)

**Overflow rule:** If a stage exceeds 1.5× planned time and produces a revision that builds/claims its stage, accept the best such revision, record remaining gaps in REQUIREMENTS.md, and move on.

---

## Overall strategy

**Stage inheritance:** Each stage inherits prior stage's source, Dockerfile, RUN.md, and acceptance suite (if stage N passes). Stage N's REQUIREMENTS.md, PLAN.md, and acceptance/ live inside stage-N/ and must not break Docker build.

**Handoff cycle per increment:**
1. @implementer builds and commits changes
2. @reviewer verifies commit in isolated harness + runs acceptance suite
3. @coordinator accepts or forwards defects back to @implementer

**Acceptance criteria:** A stage is complete when:
- Harness in isolated mode: last line is `claimed stage: N`
- Stage N+1 probe (overshoot) fails as expected
- Acceptance suite: all shipped tests pass
- @reviewer has accepted at a specific commit

Once a stage is accepted, it is locked. Next stage begins as a copy with that stage's additions.

---

## Stage 1: verify existing service

**Commit to verify:** `037d00b`  
**Status:** Source, Dockerfile, RUN.md, and REQUIREMENTS.md already in stage-1/  
**Goal:** Confirm stage-1 HTTP API at 037d00b meets all stage-1 requirements (R1–R159, D1–D29) in isolated harness and acceptance suite.

**Evidence needed:**
- Harness isolated run: `claimed stage: 1` on last line, stage-2 probe fails as expected
- Acceptance suite: all shipped tests pass
- No stage-2+ fields in API responses (e.g., no `total`, `available`, `held`, `authorization_id`)

**Handoff to @reviewer:**
- Commit: `037d00b`
- Check command: `.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage 1 --mode isolated --out C:\Development\darkfactory\band-work\checks\s1-<seat>-037d00b`
- Acceptance suite path: `C:\Development\darkfactory\band-work\result\stage-1\acceptance\`
- Acceptance command: `.venv\Scripts\pytest.exe stage-1/acceptance -v --tb=short`

---

## Stage 2: fix browser UI and authorizations

**Status:** 2 of 35 acceptance tests passing. Browser routes and authorization API partially implemented but failing most tests.  
**Starting point:** Copy stage-1 (after acceptance) and extend with:
1. Browser routes (HTML for `/`, `/login`, `/signup`, `/requests`, `/split`, `/authorizations`)
2. Render data-testid attributes for forms, buttons, inputs
3. Authorization API: `POST /authorizations`, `POST /authorizations/{id}/capture`, `POST /authorizations/{id}/void`, `GET /authorizations`
4. Wallet fields: `total`, `available`, `held` on `GET /me`
5. Fixture support for `authorization_ttl_seconds` and `authorizations` array
6. Hold validation: insufficient available (not balance) checks on payments/requests
7. Export/import preservation of holds and authorizations

**Requirements:** stage-2/REQUIREMENTS.md (R160–R289 + all stage-1)

**Acceptance suite:** stage-2/acceptance/ (35 shipped tests, only 2 passing)  
**Goal:** All 35 tests passing in isolated mode, harness claims stage 2

**Handoff to @implementer after stage-1 accepted:**
- Starting from: stage-1 accepted commit
- Due by: budget allows 1.5 hours
- Check command: `.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage 2 --mode isolated --out C:\Development\darkfactory\band-work\checks\s2-<seat>-<hash>`
- Acceptance suite: `.venv\Scripts\pytest.exe stage-2/acceptance -v --tb=short`

**Known issues from prior attempts:**
- PLAN.md and PLAN-attempt-*.md show previous runs created server code and browser routes but missed key data-testid attributes and authorization/capture endpoints
- Last commits: f8e34b3 (auth localStorage), 1cb5206 (pytest fixtures), 658ba67 (browser routes)
- All had issues with HTML structure and idempotency handling

---

## Stage 3: add statements and corrections

**Status:** Acceptance suite written but not yet implemented  
**Starting point:** Copy stage-2 (after acceptance) and extend with:
1. Payment revisions and correction history
2. `POST /payments/{payment_id}/corrections` with idempotency, revision tracking, effective/recorded time distinction
3. `GET /payments/{payment_id}/revisions` to read correction history
4. `GET /me?as_of=<instant>&known_at=<instant>` for historical balance queries
5. `GET /statement?from=<instant>&to=<instant>&known_at=<instant>&snapshot=<token>` for paginated statements with snapshot tokens
6. Settlement history: mark settlement members as immutable to corrections

**Requirements:** stage-3/REQUIREMENTS.md (R292–R336 + all stage-1 + stage-2)

**Acceptance suite:** stage-3/acceptance/ (expected ~9% of hidden tests shipped)  
**Goal:** Harness claims stage 3; all acceptance tests pass

**Handoff to @implementer after stage-2 accepted:**
- Starting from: stage-2 accepted commit
- Due by: budget allows 1.5 hours
- Check command: `.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage 3 --mode isolated --out C:\Development\darkfactory\band-work\checks\s3-<seat>-<hash>`
- Acceptance suite: `.venv\Scripts\pytest.exe stage-3/acceptance -v --tb=short`

---

## Stage 4: add refunds and batch corrections

**Status:** Acceptance suite written but not yet implemented  
**Starting point:** Copy stage-3 (after acceptance) and extend with:
1. `POST /payments/{payment_id}/refunds` (idempotent, receiver-only, creates reverse payment)
2. Refund tracking and validation (cannot exceed corrected amount, cannot refund a refund)
3. `POST /correction-batches` with settlement operator authorization, batch validation
4. Batch-wide affordability checks and atomic commit/rollback
5. Settlement member correction rules (all members must be corrected together)

**Requirements:** stage-4/REQUIREMENTS.md (R339–R360 + all prior)

**Acceptance suite:** stage-4/acceptance/ (expected ~16% of hidden tests shipped)  
**Goal:** Harness claims stage 4; all acceptance tests pass

**Handoff to @implementer after stage-3 accepted:**
- Starting from: stage-3 accepted commit
- Due by: budget allows 1.5 hours
- Check command: `.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage 4 --mode isolated --out C:\Development\darkfactory\band-work\checks\s4-<seat>-<hash>`
- Acceptance suite: `.venv\Scripts\pytest.exe stage-4/acceptance -v --tb=short`

---

## Review and defect handling

**Defect handling:** When @reviewer rejects a revision:
- @coordinator extracts root cause from harness output and acceptance test failures
- Forward full defect list to @implementer with file paths and line references
- @implementer fixes and commits new revision
- Cycle repeats until acceptance

**Same defect three times:** If the same defect is rejected three times, @coordinator re-plans: split into smaller step, give different approach, or work out root cause and hand over. Work continues until budget exhausted.

**Concurrent Docker:** Before running any check, verify `docker ps` shows no running df-* containers. Wait up to 5 minutes if another seat's check is running.

---

## Durable state

Requirements, plans, decisions and rejections are committed alongside code in stage-N/ folders. See:
- `stage-N/REQUIREMENTS.md` — contract for that stage
- `stage-N/PLAN.md` — decision log for that stage
- `stage-N/PLAN-attempt-*.md` — archived attempt logs
- `PLAN.md` (root) — this coordination plan (current run)

All four stage folders must exist by end of run, with Dockerfile and RUN.md that build.

---

## Final report

When every increment is accepted or budget exhausted:
1. Post one room message with accepted revision for each increment
2. Result of every harness check (isolated mode)
3. Acceptance test status
4. Requirement coverage with any known gaps
5. Each rejection and what it changed
6. Wall-clock time per increment
7. Stop

If a stage cannot complete by end of budget:
- Report blocker with evidence
- Record known gaps in REQUIREMENTS.md
- Move on (do not leave a stage folder in broken state)

---

## Decisions

**D1 (Spec interpretation):** Stage-1 REQUIREMENTS.md already contains 29 decisions (D1–D29). Stage 2+ inherit those and add new decisions only if needed.

**D2 (Acceptance testing):** Both harness and shipped acceptance suites guide development. Harness isolated mode is ground truth for judging.

**D3 (Stage isolation):** No .git folders in stage directories after copy. Each stage folder is self-contained.

**D4 (Browser testing):** Playwright-based acceptance tests exercise HTML routes. Visual inspection by humans is not required.
