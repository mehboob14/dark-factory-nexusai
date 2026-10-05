# Pocketful stage 3 — requirements contract

Source: `C:\Development\darkfactory\dark-factory-wearedevs\pocketful\spec\stage-1.md`, `stage-2.md`, and `stage-3.md` (read in full).
Stage 3 extends stages 1 and 2 with statements, historical balance queries, and payment corrections.
All stage-1 (R1–R159, D1–D29) and stage-2 (R160–R289) requirements continue to apply.

This list covers the stage-3 additions. Build every line. Do not implement stage 4+ (refunds, batch corrections).

---

## Payment timestamps

R292. Every payment's `created_at` is RFC 3339 instant with offset identifying when it moved money. Every endpoint returning payment includes it. `GET /activity` retains existing ordering by this field. [§3]
R293. Seeded payments may supply `created_at`; omission uses reset time, before subsequent API-created payments. Seeded `created_at` in future gives `422 validation_failed` from `POST /_test/reset`, no state change. [§3]
R294. Fixture's `balance` remains balance after all seeded payments. Loading those payments must not change that balance. [§3]

---

## GET /me as of an instant

R295. `GET /me?as_of=<RFC 3339 instant>`: optional `as_of` parameter, RFC 3339 instant with offset. Anything else (naive local time, bare date, empty value) is `422 validation_failed`. [§3]
R296. Without temporal query parameters, response retains existing money fields and reports current corrected values. [§3]
R297. With `as_of`, `balance` is caller's balance as it stood at that instant: balance after every payment of theirs with `created_at` at or before `as_of`, and before every payment after it. Payment made exactly at `as_of` counts as having happened. [§3]
R298. `as_of` at or after latest payment returns current balance. `as_of` before earliest payment returns opening balance (what wallet held before anything moved). [§3]
R299. Response carries `as_of` back, exactly as given. [§3]

---

## GET /statement

R300. `GET /statement?from=<instant>&to=<instant>&limit=50&offset=0`: both `from` and `to` optional; `from` defaults to opening of wallet, `to` defaults to now. `limit` and `offset` behave exactly as on `GET /requests`. [§3]
R301. Returns payments caller sent or received in half-open window `[from, to)`, **oldest first**, each with caller's balance immediately after it. [§3]
R302. Response body: `{opening_balance, entries, closing_balance, has_more, snapshot}`. [§3]
R303. `entries` array contains objects `{payment, delta, balance_after, revision, effective_at, recorded_at}`. [§3]
R304. Entries ordered by `created_at` ascending, then payment `id` ascending for ties. With corrections, entries ordered by selected `effective_at` ascending, then payment id ascending. [§3]
R305. `opening_balance`: balance immediately before `from`. `closing_balance`: balance immediately before `to`. [§3]
R306. `opening_balance` plus all `delta` values in full window must equal `closing_balance`. Sent payment has negative `delta`; received has positive `delta`. [§3]
R307. Pagination must not change entry's `balance_after` or window's opening/closing balances. These values describe full window regardless of `limit` and `offset`. [§3]
R308. Only payments sent or received by caller appear in statement, including when other payments public. Activity-feed visibility rules do not apply to statements. [§3]

---

## Effective time, recorded time, and payment revisions

R309. Service distinguishes **when money took effect** from **when it learned that fact**. Every payment has revision history. [§3]
R310. Revision 1 has `amount` as originally paid and `effective_at = recorded_at = created_at`. Seeded payment's supplied `created_at` is also original recorded/effective time; omission uses reset time. Opening balances equal seeded ending balances minus net effect of original seeded payments. Corrections must not change opening balances. [§3]
R311. New accounts open at zero. Seeded history is consistent and nonnegative. [§3]

---

## POST /payments/{payment_id}/corrections

R312. Requires idempotency key and original sender. Authenticated non-sender gets `403 forbidden`; unknown payment gets `404`. Body all required: `expected_revision` (positive integer), `amount` (0..1000000000; zero reverses entire payment), `effective_at` (RFC 3339 instant, not later than now), `reason` (string 1..200 chars). [§3]
R313. Invalid input is `422 validation_failed`. [§3]
R314. Correction changes neither parties nor visibility. Appends immutable revision, returning `201` with `payment_id`, `revision`, `amount`, `effective_at`, server-assigned `recorded_at`, and `reason`. Recorded times for one payment strictly increase. [§3]
R315. Stale expected revision gives `409 stale_revision`. Successful replay returns that original revision with `200` even after newer revisions. Different body with same key is `409 idempotency_key_reuse`. [§3]
R316. Difference from previous amount moves between **same two wallets** in same atomic step. Increasing amount debits original sender; decreasing debits original receiver. Currently unaffordable debit gives `409 insufficient_funds`. [§3]
R317. If any user's corrected balance negative at any effective-time boundary, return `409 historical_overdraft`. Balances at boundary include combined effect of all movements at that instant. Either failure preserves balances, revision history, statements and idempotency state. Sum of balances must equal seeded total in every historical view. [§3]
R318. Original payment and every original idempotent response remain unchanged. `GET /activity` continues to display original payment; correction records are not new feed payments. [§3]

---

## GET /payments/{payment_id}/revisions

R319. Returns `{revisions: [...]}` in revision order, including revision 1 (`reason: ""`). Only two parties can read it; third party gets `404` even for public payment. No token is `401`. [§3]

---

## Temporal queries with known_at

R320. `GET /me` and `GET /statement` accept optional `known_at`, RFC 3339 instant with offset. For each payment, select its latest revision recorded **at or before** `known_at`; if none yet recorded, that payment contributes nothing. Omission means everything known when read begins. Then apply selected revisions according to their **effective** times. [§3]
R321. `as_of` retains inclusive meaning; statement retains half-open window. Both query instants may be in future. Invalid/empty instants are `422`. Echo supplied `known_at` exactly. [§3]

---

## Statement with corrections

R322. Statement ordering now by selected `effective_at`, then payment id. Each entry retains `payment`, `delta`, `balance_after`, and adds selected `revision`, `effective_at`, `recorded_at`. `payment.amount` is selected amount for this statement. [§3]
R323. Zero-amount revisions still appear as entries with zero delta. No correction counted alongside revision it replaces. With no corrections and no `known_at`, previous behaviour unchanged. [§3]

---

## Stable statement pagination with snapshot

R324. Every first `GET /statement` response additionally returns opaque `snapshot` token. Freezes caller's selected revisions, window, balances, entries and default `to` at that read. [§3]
R325. `GET /statement?snapshot=<token>&limit=...&offset=...` pages that exact result, even after payments or corrections. Only `limit` and `offset` may accompany snapshot; supplying `from`, `to` or `known_at` with it gives `422 validation_failed`. [§3]
R326. Unknown token, another user's token, or token from before reset gives `404 not_found`. Tokens last until reset. No storage survival across container restarts required. [§3]
R327. Paging changes neither balances nor entries; final partial page and offsets beyond end must report `has_more` correctly. Unrecognized query parameters remain ignored under stage-1 general rule. [§3]
R328. Correction may move payment into or out of statement window. Existing snapshots remain unchanged during concurrent payments or corrections. Concurrent corrections using same expected revision cannot both succeed. [§3]

---

## Settlement history and immutability

R329. Stage-1 settlements retain original receipts and privacy rules. Each member's original revision uses its shared `committed_at` as both `effective_at` and `recorded_at`. [§3]
R330. Single-payment corrections reject settlement members with `422 linked_payment_immutable`. [§3]

---

## Export/import compatibility

R331. Stage-3 service must accept exports from same team's stage-1 or stage-2 service. Ledger must import and account for authorizations and captures. Captures are immutable linked payments: correction of a capture gives `422 linked_payment_immutable`. [§3]

---

## Historical holds

R332. For `GET /me?as_of=T&known_at=K`, all four money fields describe same view: `balance = total`, `available = total - held`. [§3]
R333. Hold starts at authorization creation; nonfinal capture reduces it at capture time; final capture, void or expiry releases remainder at that event's time. Expiry takes effect at `expires_at`. Events other than clock expiry known at their server-assigned event time. Once creation known, expiry deadline known too. [§3]
R334. For queries beyond now, open hold expires at its deadline. Without `as_of`, use instant request began. Authorizations expose `closed_at` (null while open; event time when closed). [§3]
R335. Historical `total` follows stage-3 effective/recorded-time rules. Correction rejected with `409 historical_overdraft` if it makes either total or available negative at any past effective/event boundary, under latest known revisions. Current unaffordable debits still take precedence as `insufficient_funds`. [§3]
R336. Seeded open holds assumed created at reset unless `created_at` supplied; seeded closed holds need not reconstruct prior lifecycle. `GET /statement` contains money movements only: authorization, release and expiry not payments. Captures appear exactly once with their links. Old snapshots remain unchanged after any lifecycle action or correction. [§3]

---

## Explicitly not in stage 3

R337. No refunds, refund_of field. [stage-4]
R338. No correction batches, batch operations. [stage-4]

---

## Stage 1 and 2 requirements preserved

All stage-1 (R1–R159, D1–D29) and stage-2 (R160–R289) requirements remain in force. Do not remove earlier functionality.
