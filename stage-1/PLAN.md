# Pocketful stage 1 — plan

Start: 2026-10-05 13:08 UTC+5 (08:08 UTC)
Finish: (open)

Planned time: 2.5 hours. Cap: if still not accepted after 3.75 hours (1.5×), reviewer accepts the best revision that builds, starts, and claims stage 1 in isolated mode; remaining gaps are written into REQUIREMENTS.md and this plan.

## Goal

A complete stage-1 HTTP wallet/payments service in `C:\Development\darkfactory\band-work\result\stage-1` that meets every line of REQUIREMENTS.md, claims stage 1 on the harness in isolated mode, and does not implement stage 2+.

## Decisions

- In-memory single-process store with one mutex around mutations (D8).
- bcrypt cost 4 (D9).
- Payment objects include `settlement_id` (D2) and omit later-stage fields (D10).
- Implementer chooses language. Prefer Go or Python (stdlib or FastAPI) for delivery speed and one-lock concurrency.
- Dockerfile must not fail because REQUIREMENTS.md / PLAN.md / acceptance/ exist: copy only runtime files, or `.dockerignore` those planning paths.
- Build to the specification, never to the shipped sample tests.

## Work items (dependency order)

| ID | Owner | Covers | Evidence |
|---|---|---|---|
| W1 | implementer | R1–R9: listen, health, Dockerfile, RUN.md | Container starts; `GET /health` 200 within 60 s |
| W2 | implementer | R31–R41: reset/seed/validation | Reset 204; negative balance 422; seeded login works |
| W3 | implementer | R42–R56: signup/login/tokens/GET /me | Auth table in §6; hashed passwords |
| W4 | implementer | R69–R79, R26–R29: payments + conservation | Atomic debit/credit; insufficient_funds |
| W5 | implementer | R80–R104, R28, R87–R99: requests | Create/pay/decline/cancel/list |
| W6 | implementer | R105–R121, R30, R117–R120: splits | Exact §9 shares; zero-share request |
| W7 | implementer | R122–R129: activity visibility | Public vs private; requests absent |
| W8 | implementer | R57–R68: idempotency | 201/200/409; concurrent one-effect; 4xx does not claim |
| W9 | implementer | R130–R142: settlements | Operator 403; net affordability; atomic batch |
| W10 | implementer | R143–R153: export/import | Round-trip tokens, hashes, idempotent replays |
| W11 | implementer | R10–R23, R154–R156: conventions + concurrency | No 5xx; 50-way conservation |
| W12 | tester | R1–R156: acceptance suite in `stage-1/acceptance/` | One command; every R-line named |
| W13 | tester | Harness sample + isolated claim | `claimed stage: 1`; stage 2 overshoot FAIL expected |
| W14 | reviewer | Accept named commit | Isolated harness + acceptance; no stage-2 leak |

Do not start stage 2 until W14 accepts.

## Checks

From `C:\Development\darkfactory\dark-factory-wearedevs`:

```
.venv\Scripts\python.exe -m harness run --track pocketful --repo C:\Development\darkfactory\band-work\result --stage 1 --out C:\Development\darkfactory\band-work\checks\s1-<unique-name>
```

Before accept, same with `--mode isolated`. Last line must be `claimed stage: 1`. Suite 2 overshoot is expected FAIL.

If a run reports a missing browser: `.venv\Scripts\python.exe -m playwright install chromium` (stage 1 has no UI; still install if the harness asks).

## Log

- 13:08 UTC+5 — coordinator read all four specs, wrote REQUIREMENTS.md (R1–R159, D1–D29) and this plan.
- 13:12 UTC+5 — contract committed at `136a315106ae0954200a32d5ded8755abb0d8f40`. Implementer readiness requested.
- 13:13 UTC+5 — implementer confirmed ready. Waking tester next; no work handoff until the remaining seats answer.
- 13:14 UTC+5 — tester confirmed ready. Waking reviewer next.
- 13:16 UTC+5 — reviewer confirmed ready. Dispatching implementer (W1–W11) and tester (W12) in parallel with the full contract and spec.
- 13:23 UTC+5 — implementer started then hit a premature-close. Scaffolding (Dockerfile, RUN.md, requirements.txt) exists; server/ is empty. Told implementer to resume and commit incrementally.
- 13:29 UTC+5 — tester crashed mid-suite. Uncommitted acceptance files cover delivery through settlements. Told tester to commit and finish export/import, concurrency, and non-goals.
- 13:33 UTC+5 — tester crashed again after adding export/concurrency/nongoals. Told tester to commit the suite. Pinged implementer: server files still uncommitted.
- 13:35 UTC+5 — tester committed suite `e55a3f7aaf2f810b98762298e0653e590faed3dc` then cleanup `ad9b010cf4b47cc6b0c6872fc33e75992dff8e00`. Implementer product files still uncommitted.
- 13:37 UTC+5 — tester reported W12: suite `C:\Development\darkfactory\band-work\result\stage-1\acceptance` at `ad9b010cf4b47cc6b0c6872fc33e75992dff8e00`. Run: `python C:\Development\darkfactory\band-work\result\stage-1\acceptance\run.py`. Covers R1–R7 and R9–R159 (166 checks). R8 not observable over HTTP. W13 blocked on an implementer product commit.
- 13:40 UTC+5 — tester updated suite to `22376e72abbf893fcc9ec8007d69dbe46a53b5fc` (R16 scientific notation on the wire, R153 per-call 10s budget, R1/R2/R9 skip if delivery files absent). Implementer still uncommitted.
- 13:58 UTC+5 — implementer committed service `a1772612ff1623bdf301ca5fb763f31c48703982` (Dockerfile, RUN.md, server/). Dispatching W13: acceptance suite plus harness sample and isolated mode.
