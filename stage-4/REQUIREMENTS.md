# Pocketful stage 4 — requirements contract

Source: `C:\Development\darkfactory\dark-factory-wearedevs\pocketful\spec\stage-1.md`, `stage-2.md`, `stage-3.md`, and `stage-4.md` (read in full).
Stage 4 extends stages 1, 2 and 3 with refunds and batch corrections.
All stage-1 (R1–R159, D1–D29), stage-2 (R160–R289), and stage-3 (R292–R336) requirements continue to apply.

This list covers the stage-4 additions. Build every line.

---

## Ten idempotent write paths

R339. There are now ten idempotent write paths: stage-1's five (`POST /payments`, `POST /requests`, `POST /requests/{id}/pay`, `POST /splits`, `POST /settlements`), stage-2's two (`POST /authorizations`, `POST /authorizations/{id}/capture`), stage-3's one (`POST /payments/{payment_id}/corrections`), and stage-4's two (`POST /payments/{payment_id}/refunds`, `POST /correction-batches`). [§4]

---

## Refunds

R340. `POST /payments/{payment_id}/refunds` requires idempotency key. Only original receiver may refund, else `403 forbidden`; unknown payment is `404`. [§4]
R341. Body: `{"amount": <amount>}`. Target may be direct payment, request payment or capture, but never a refund. Invalid amount is `422 validation_failed`. [§4]
R342. Refunds cumulatively may not exceed payment's current corrected amount: `422 refund_exceeds_payment`. Refunds of refunds give `422 invalid_refund_target`. [§4]
R343. Refund is new payment in opposite direction, with `refund_of` naming target, `request_id: null`, `authorization_id: null`, and original note/visibility. Return `201` with that payment; replay returns `200` with original body. [§4]
R344. Refund moves existing money from receiver's **available** funds, or fails `409 insufficient_funds`, atomically. Refunds never reopen request or authorization or restore released hold. [§4]
R345. Other payments have `refund_of: null`. [§4]

---

## Corrections for refunds and captures

R346. Stage-3 corrections remain available for ordinary direct/request payments. Captures and refund payments cannot themselves be corrected: `422 linked_payment_immutable`. [§4]
R347. Correction cannot reduce payment below its already-refunded amount: `422 refund_exceeds_payment`. Correction debits checked against available funds. [§4]

---

## Batch corrections

R348. `POST /correction-batches` requires settlement operator and idempotency key, same 401/403 rules as settlements. [§4]
R349. Body: `{corrections: [{payment_id, expected_revision, amount, effective_at, reason}, ...]}`. `corrections` contains 1..32 objects with distinct payment_ids, else `422 validation_failed`. [§4]
R350. Every item has ordinary correction fields and validation. Unknown payment is `404`; stale expected revision is `409 stale_revision`. [§4]
R351. Operator may correct ordinary, request and settlement payments, but captures and refunds remain immutable. Correcting any settlement member requires including every member of that settlement, else `422 incomplete_settlement`. [§4]
R352. Members of one settlement must have identical effective instants (offset spellings may differ), else `422 validation_failed`. Ordinary single-payment corrections remain available for nonmembers. Unknown fields ignored. [§4]
R353. Error precedence: item errors in input order, settlement completeness, resulting current available funds, then historical total and available funds at every effective/event boundary. Existing codes apply: `linked_payment_immutable`, `refund_exceeds_payment`, `insufficient_funds`, `historical_overdraft`. [§4]
R354. Affordability determined by combined effect of all proposed revisions. Rejected batch leaves history, balances and idempotency records unchanged. [§4]
R355. Return `201` with `{correction_batch_id, recorded_at, revisions}` in input order. All new revisions share `recorded_at`, strictly later than previous `recorded_at` of every member; each revision also exposes `correction_batch_id`. [§4]
R356. Effective times cannot be later than now. Original payments and receipts never change. Original payment and settlement retries return their original bodies. [§4]
R357. New statements reflect new revisions; earlier snapshot tokens continue to page their frozen entries. Replays return original batch response with `200`. [§4]
R358. Settlement payment may be refunded under existing refund rules, but refunds never change settlement membership. [§4]
R359. Concurrent corrections sharing any expected payment revision cannot both succeed. [§4]

---

## Export/import compatibility

R360. Stage-4 service must accept exports from same team's stages 1–3, retaining settlement membership, corrections and snapshots. [§4]

---

## Explicitly not in stage 4

R361. No further additions beyond stage-4 scope. [end of specification]

---

## All prior requirements preserved

All stage-1 (R1–R159, D1–D29), stage-2 (R160–R289), and stage-3 (R292–R336) requirements remain in force. Do not remove earlier functionality.
