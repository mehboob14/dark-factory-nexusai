# Pocketful stage 1 — requirements contract

Source: `C:\Development\darkfactory\dark-factory-wearedevs\pocketful\spec\stage-1.md` (read in full).
This list is the contract. Build every line. Hidden judging tests are derived from the specification text, not from shipped samples. Do not special-case fixtures, test names, or sample emails.

Stage 1 is HTTP API only. Do not implement stage 2+ (browser UI, authorizations/holds, statements, corrections, refunds, batch corrections, `available`/`held`/`total`, `authorization_id`, `refund_of`, `known_at`/`as_of`).

---

## Delivery and runtime

R1. Deliver an HTTP service, a `Dockerfile`, and a `RUN.md` whose single documented command builds and starts the service with no manual steps. [§2]
R2. The image must run alone with `-e PORT=<port>` and a port mapping. Compose is not used to start the service. [§2]
R3. Listen on `0.0.0.0` using env `PORT`, default `8080`. [§3.1]
R4. `GET /health` returns `200` and `{"status":"ok"}` once the service and store can serve requests, within 60 s of container start. Non-200 is allowed before ready. [§3.2]
R5. Runtime limits: 2 vCPU, 2 GiB, up to 50 concurrent in-flight requests, 5 s per request, 10 s for `POST /_test/reset` and other test-control calls, no outbound network at runtime. Disk is ephemeral; state need not survive restart. [§2 Resource limits] [§10]
R6. Bundle every runtime asset (fonts, scripts, stylesheets, dependencies). No external services at runtime. Outbound network is available only during `docker build`. [§2]
R7. Language is unrestricted. The submission is a containerized HTTP service, not a Python package. The harness talks to HTTP only. [§2]
R8. Do not use source, API documentation, or schemas from existing products in this domain. [opening]
R9. `REQUIREMENTS.md`, `PLAN.md`, and `acceptance/` live in this folder and must not break the Docker build. [factory layout]

---

## Conventions

R10. Request and response bodies are `application/json; charset=utf-8`. [§3.4]
R11. Timestamps in responses are RFC 3339 with an explicit numeric offset, e.g. `2026-09-24T19:00:00+02:00` or `2026-09-24T11:04:03+00:00`. [§3.4]
R12. Unknown fields in a request body are ignored, never an error. [§3.4]
R13. Unknown query parameters are ignored. [§3.4]
R14. IDs are opaque strings of at most 64 characters. Seeded IDs are preserved exactly. Generated IDs must be ≤ 64 characters. [§3.4]
R15. There is one currency, declared in the fixture. Every API amount is an integer count of that currency's minor units. [§4]
R16. Body amounts must have an integral numeric JSON value: `1000`, `1000.0`, and `1e3` are the same valid amount. Booleans and strings are not numbers. [§4] [§5]
R17. A field of the correct JSON type with invalid format or out-of-range value is `422 validation_failed`, unless an endpoint names a more specific code. [§5]
R18. Reserve `400 malformed_request` for an unparseable body or a field of the wrong JSON type, except where an endpoint-specific rule says otherwise. [§5]
R19. Invalid `amount` values (including strings and booleans), non-string `note` values (including `null`), and any `visibility` other than `public` or `private` are `422 validation_failed`. Omission of optional fields selects defaults. Other wrong JSON types follow R18. [§5]
R20. An integer-valued query parameter must be plain decimal digits. `1e9`, `4.0`, and `+4` are `422 validation_failed`. [§5]
R21. Shared ranges: `Idempotency-Key` 1..255 characters (else `422 validation_failed` when the header is present but invalid); `limit` integer 1..200; `offset` integer ≥ 0. Outside those ranges is `422 validation_failed`. [§5]
R22. Every 4xx and 5xx body is `{"error":{"code":"<code>","message":"<any wording>"}}`. Use the specified HTTP status and `code`. [§5]
R23. Requests must not produce 5xx responses, including under concurrent load. [§5]
R24. Money moves only between existing wallets. Deposits, top-ups, withdrawals, cards, and bank integrations are out of scope. [§1]
R25. Directory, user-search, email verification, password reset, refresh tokens, role-management, and administrative balance endpoints are out of scope. [§4] [§6]

---

## Invariants (all operations, including concurrency and retries)

R26. The sum of wallet balances always equals the total seeded by the last successful `POST /_test/reset`. [§1]
R27. No wallet balance may be negative, including transiently. [§1]
R28. A payment request may move money at most once. [§1]
R29. `amount` is at most `1000000000` on any single request, and no operation produces a balance outside ±2⁵³. Monetary arithmetic is exact integer minor units with no rounding error. [§4 Arithmetic range]
R30. After any number of splits have been paid in full, wallet balances still sum exactly to the seeded total. [§9]

---

## Reset and fixture

R31. `POST /_test/reset` is unauthenticated, enabled in the delivered image, accepts `application/json`, replaces all service state with the fixture, and returns `204 No Content`. [§3.3]
R32. When reset returns 204, subsequent requests see only that fixture. Repeated resets are supported. [§3.3]
R33. Reset clears all prior state, including imported state, tokens, idempotency records, payments, requests, splits, settlements, and users. [§10]
R34. Seeded users can log in immediately with the given password. [§4 Fixture]
R35. Seeded `balance` is the wallet total **after** every seeded payment has been applied. Do not replay seeded payments against balances. [§4 Fixture]
R36. A `balance` below zero in a fixture is a reset error: `422 validation_failed`, and state is unchanged. [§4 Fixture]
R37. `minor_units` is `0`, `2`, or `3`. Fixtures use `EUR` (2), `JPY` (0), and `BHD` (3). Accept those pairings; reject `minor_units` other than 0, 2, or 3 with `422 validation_failed` and no state change. [§4 Fixture]
R38. Fixture may include `payments` and `requests` arrays (omit means empty). Seeded payments and requests are visible through the normal APIs using their seeded ids, amounts, notes, visibility, and status. [§4 Fixture]
R39. Fixture may include `settlement_operator_ids`, an array of user ids, default `[]`. [§11]
R40. Invalid JSON on reset is `400 malformed_request` and changes nothing. Missing required fixture fields, wrong types for required fixture fields, duplicate user `id`/`email`/`handle`, handle not matching `^[a-z0-9_]{1,20}$`, unknown `from_user_id`/`to_user_id`/`requester_id`/`payer_id`, invalid seeded visibility/status, or a seeded id longer than 64 characters is `422 validation_failed` and changes nothing. [§3.3] [§4] [§5] [decision D1]
R41. Unparseable or wrong-type fixture `amount`/`balance` values follow §5. Negative seeded payment/request amounts are `422`. [§5] [decision D1]

---

## Users, handles, authentication

R42. Every user has a handle: unique across the service, matching `^[a-z0-9_]{1,20}$`, never changing once set. [§4]
R43. Seeded users take their handle from the fixture. [§4]
R44. A user created through `POST /auth/signup` (no `handle` field in the body) has a handle derived from email: take the local part, lowercase it, replace every character outside `[a-z0-9_]` with `_`, truncate to 20 characters. [§4]
R45. If the derived handle is already taken, signup returns `409 handle_taken` and creates no account. [§4] [§6]
R46. New users start with balance `0` and can receive money and be asked for money immediately. [§4]
R47. `POST /auth/signup` body `{email, password, display_name}` returns `201` `{user_id, display_name, token}`. [§6]
R48. `POST /auth/login` body `{email, password}` returns `200` `{user_id, display_name, token}`. [§6]
R49. Email already registered → `409 email_taken`. [§6]
R50. Password shorter than 8 characters on signup → `422 validation_failed`. [§6]
R51. `email` not of the form `local@domain` → `422 validation_failed`. [§6]
R52. Wrong password or unknown email on login → `401 unauthenticated`. [§6]
R53. Every endpoint except `GET /health`, `POST /_test/reset`, `POST /auth/signup`, `POST /auth/login`, `GET /_test/export`, and `POST /_test/import` requires `Authorization: Bearer <token>`. Missing, malformed, or unknown token → `401 unauthenticated`. [§6] [§10]
R54. Tokens do not expire. An account may have multiple valid tokens and concurrent sessions. Each successful signup/login issues a token; previously issued tokens for that account remain valid until reset/import replaces them. [§6]
R55. Passwords are stored using a password-hashing function (bcrypt, scrypt, Argon2, or equivalent). Plaintext storage is not permitted. [§6]
R56. `GET /me` (authenticated) returns `{user_id, display_name, handle, balance, currency, minor_units}` for the caller. [§8]

---

## Idempotency

R57. Five write paths require `Idempotency-Key`: `POST /payments`, `POST /requests`, `POST /requests/{id}/pay`, `POST /splits`, `POST /settlements`. Rules apply independently per path. [§7] [§8] [§11]
R58. Key is scoped to the authenticated user. Different users may use the same key string with no interaction. [§7]
R59. A replay is the same user, same method, same path, and the same JSON body value after parsing (key order and whitespace do not matter). Same key on a different path is a new request and must succeed normally. [§7]
R60. Header absent or empty → `400 missing_idempotency_key`. [§7]
R61. First successful use of the key → normal response with **201**. [§7]
R62. Replay: same key, same body → **200**, body identical to the original response as a JSON value. [§7]
R63. Same key, different body → `409 idempotency_key_reuse`. [§7]
R64. Key reused after the original request failed with 4xx is treated as a first use (the failed attempt does not claim the key). [§7]
R65. Concurrent identical requests with an unused key: exactly one returns 201; the others return 200 with the same body; the operation takes effect only once. [§7]
R66. A successful replay returns the original response even after the resource later changes or is cancelled, and makes no further state changes. [§7]
R67. After the body has parsed as a JSON object and the caller is authenticated, an already-claimed key is resolved before endpoint field validation or current-resource checks. Changing a successful request to an invalid body with the same key still returns `409 idempotency_key_reuse`. [§7]
R68. For settlements, failed validation claims no idempotency key and creates no payment or revision. [§11]

---

## Payments

R69. `POST /payments` is an idempotent write. Body: `to_handle` (required), `amount` (required), `note` optional default `""`, `visibility` optional default `"public"`. [§8]
R70. Success `201` body: `{payment_id, from_user_id, from_handle, to_user_id, to_handle, amount, currency, note, visibility, request_id, created_at}` with `request_id` null for a direct payment. [§8]
R71. Direct payments and other non-settlement payments expose `settlement_id: null`. Settlement member payments expose the batch `settlement_id`. Include `settlement_id` on every payment object. [§11] [decision D2]
R72. Caller balance below `amount` → `409 insufficient_funds`; no money moves; no payment record. [§8]
R73. `amount` below 1, above 1000000000, or not an integer → `422 validation_failed`. [§8]
R74. `to_handle` is the caller's own handle → `422 self_payment`. [§8]
R75. `note` longer than 200 characters → `422 validation_failed`. [§8]
R76. `visibility` neither `public` nor `private` → `422 validation_failed`. [§8]
R77. No user has that handle → `404 not_found`. [§8]
R78. Debit and credit are one atomic step. A payment is never visible in one wallet and not the other. A failed payment leaves no trace in either wallet. [§8]
R79. `note` is stored and returned verbatim: no trimming, escaping, or normalisation. Unicode and emoji survive byte for byte. [§8]

---

## Requests

R80. `POST /requests` is an idempotent write. Caller is the requester. Body: `payer_handle`, `amount`, optional `note` default `""`. [§8]
R81. Success `201` body: `{request_id, requester_id, requester_handle, payer_id, payer_handle, amount, currency, note, status:"pending", payment_id:null, created_at}`. [§8]
R82. `amount` below 1, above 1000000000, or not an integer → `422 validation_failed`. [§8]
R83. `payer_handle` is the caller's own handle → `422 self_request`. [§8]
R84. `note` longer than 200 characters → `422 validation_failed`. [§8]
R85. Unknown `payer_handle` → `404 not_found`. [§8]
R86. The payer's balance is not checked. A request larger than the payer holds is created and stays `pending`. [§4] [§8]
R87. A request is `pending`, then exactly one of `paid`, `declined`, or `cancelled`. [§4]
R88. `POST /requests/{id}/pay` is an idempotent write. Only the payer may call it. Body carries optional `visibility` default `"public"`. [§8]
R89. `{}` and `{"visibility":"public"}` are different JSON values; reusing a key across them is `409 idempotency_key_reuse`. [§8]
R90. Success `201` returns the created payment in the `POST /payments` shape, with `request_id` set to this request. The request becomes `paid` and carries the new `payment_id`. [§8]
R91. Request not `pending` → `409 request_not_pending`. [§8]
R92. Payer available/balance below amount → `409 insufficient_funds`; request stays `pending`; no payment. [§8]
R93. Caller is not the payer → `403 forbidden`. [§8]
R94. Unknown request → `404 not_found`. [§8]
R95. Replaying a successful pay returns `200` with the original payment body even when the request is already `paid`. It moves no additional money and must not return `409 request_not_pending`. [§8]
R96. `POST /requests/{id}/decline`: only the payer; no idempotency key; `200` with the request `status:"declined"`. Declining an already-declined request is `200` with current state. `paid` or `cancelled` → `409 request_not_pending`. Not the payer → `403 forbidden`. Unknown → `404 not_found`. [§8]
R97. `POST /requests/{id}/cancel`: only the requester; no idempotency key; `200` with the request `status:"cancelled"`. Cancelling an already-cancelled request is `200`. `paid` or `declined` → `409 request_not_pending`. Not the requester → `403 forbidden`. Unknown → `404 not_found`. [§8]
R98. Paying a short request is `409 insufficient_funds` and changes nothing. Money can arrive later and the same request then becomes payable. [§4]
R99. Visibility belongs to the payment, not the request. A request carries no visibility and never appears in anyone else's feed. [§4]
R100. `GET /requests` returns only requests where the caller is requester or payer, newest first by `created_at`. [§8]
R101. Query `direction`: `incoming` (caller is payer), `outgoing` (caller is requester), or absent for both. [§8]
R102. Query `status`: one of `pending|paid|declined|cancelled`, or absent for all. [§8]
R103. `limit` defaults to 50 (range 1..200). `offset` defaults to 0 (≥ 0). Outside range → `422 validation_failed`. Unknown `direction` or `status` → `422 validation_failed`. [§8]
R104. Response `{requests:[...], has_more}`. `has_more` is true when items exist beyond the last one returned. [§8]

---

## Splits

R105. `POST /splits` is an idempotent write. Splits an amount and creates one `pending` request per other participant. [§8]
R106. Body: `amount`, `participant_handles` (array of handles, order significant), optional `note` default `""`. [§8]
R107. Caller may be included in `participant_handles` or omitted. A request is created for every participant except the caller, each for that participant's share, caller as requester. [§8]
R108. Success `201` body: `{split_id, amount, currency, note, shares, requests, created_at}`. [§8]
R109. `shares` covers every participant including the caller, in the order given, and always sums to `amount`. Each share is `{handle, amount}`. [§8]
R110. `requests` covers every participant except the caller, in the same order, each a full request object as in R81. [§8]
R111. `amount` below 1, above 1000000000, or not an integer → `422 validation_failed`. [§8]
R112. `participant_handles` empty, or containing a duplicate handle → `422 validation_failed`. [§8]
R113. `note` longer than 200 characters → `422 validation_failed`. [§8]
R114. Any handle unknown → `404 not_found`. [§8]
R115. A split whose only participant is the caller is valid: one share, `"requests":[]`. [§8]
R116. Nothing about a split checks anyone's balance. [§8]
R117. Shares are whole minor units, sum exactly to `amount`, and differ by at most one minor unit. When the amount does not divide evenly, larger shares go to the first participants in `participant_handles` order. [§9]
R118. Required examples: 1000/3 → 334,333,333; 1/3 → 1,0,0; 10/3 → 4,3,3; 999/3 → 333,333,333; 5/5 → 1,1,1,1,1. [§9]
R119. A share of `0` is legal and still produces a request for that participant (if not the caller). [§9]
R120. Splitting the same amount among the same people in a different handle order gives the extra unit to a different person. Each split's shares are independent of previous splits. [§9]
R121. A split is not a feed item. Its requests are visible to their two parties; later payments follow the feed rule. [§4]

---

## Activity feed

R122. `GET /activity` returns payments only, newest first by `created_at`. [§4] [§8]
R123. A payment appears for a caller if and only if `visibility` is `public` OR the caller is its sender or its receiver. No follow graph, no mute list. [§4]
R124. Requests never appear in the activity feed. [§4]
R125. A `private` payment is hidden from third parties, not from its own receiver or sender. [§4]
R126. Visibility is one value on the payment, seen identically by both parties and by everyone else. [§4]
R127. Response `{payments:[...], has_more}`. Each payment uses the payment object shape (R70–R71). [§8]
R128. `limit` and `offset` behave exactly as on `GET /requests`. [§8]
R129. Relative order of two payments created within the same second is unspecified. Stable pagination during concurrent writes is not required. [§8]

---

## Settlements

R130. `POST /settlements` requires an operator (id in `settlement_operator_ids`) and an idempotency key. [§11]
R131. No token → `401 unauthenticated`. Authenticated non-operator → `403 forbidden`. This permission does not grant access to another user's requests or private activity items. [§11]
R132. Body: `{"transfers":[{"from_handle","to_handle","amount", optional note, optional visibility}, ...]}`. `transfers` contains 1..32 objects. [§11]
R133. Each transfer uses ordinary payment amount, note, and visibility rules (defaults: empty note, public). [§11]
R134. Unknown handle → `404 not_found`. Self-transfer (`from_handle` equals `to_handle`) → `422 self_payment`. Malformed batch shape (wrong type, empty, >32, missing required fields) → `422 validation_failed`. [§11]
R135. Entry errors take precedence in input order, before insufficient funds. Unknown fields are ignored. [§11]
R136. A settlement is affordable when every wallet's balance after all incoming and outgoing transfers in the batch is nonnegative. Otherwise `409 insufficient_funds`. [§11]
R137. Either all movements commit together or none do. [§11]
R138. Success `201` body: `{settlement_id, committed_at, payments}` with `payments` in input order. [§11]
R139. Every member is an ordinary payment with `settlement_id` linking the batch, `request_id` null, and the same server-assigned `created_at` equal to `committed_at`. [§11]
R140. Constituents follow ordinary activity-feed visibility. The settlement response contains every member's receipt. [§11]
R141. Replays return `200` with the original complete response. [§11]
R142. Reset/import must preserve settlement operator permissions, original payments, requests, settlement membership, and retry responses. [§11]

---

## Export and import

R143. `GET /_test/export` is unauthenticated. Returns `200` with a JSON object `{track:"pocketful", format_version:1, state:<implementation-defined object>}`. [§10]
R144. Export is an atomic read-only snapshot; subsequent source writes do not change the already-returned object. [§10]
R145. `POST /_test/import` is unauthenticated, takes that entire object, atomically replaces service state, returns `204`. [§10]
R146. Import must accept an unchanged export produced by this service. No dependency on source process, files, volume, port, or network address. [§10]
R147. Import is replacement, not merge. Repeating it restores the exported state without duplicating anything. [§10]
R148. Invalid JSON → §5 (`400 malformed_request`). Missing fields, wrong `track`/`format_version`, or invalid `state` → `422 validation_failed` without changing destination. [§10]
R149. Preserve: accounts and hashed-password login, existing bearer tokens, currency, balances, payments, requests, permissions (including settlement operators), all completed idempotent request bodies and original responses. [§10]
R150. Identities, timestamps, and monetary records must not be regenerated or replayed against an already-net balance. [§10]
R151. Failed request keys remain reusable after import. Existing receipts, tokens, and retries remain valid after import. Replacing state with a fresh fixture does not satisfy this. [§10]
R152. Import removes all previous destination data and credentials. Reset after import yields a clean fixture-only world. [§10]
R153. Test-control calls (`reset`, `export`, `import`) have a 10-second timeout. [§10]

---

## Concurrency

R154. Concurrent requests must preserve R26–R28 at every read. Fifty in-flight requests must complete within the per-request timeout without 5xx. [§1] [§2] [§5]
R155. Concurrent payments, request pays, and settlements that compete for the same funds serialize so that at most the affordable subset commits, none go negative, and conservation holds. [§1] [§11]
R156. Concurrent identical idempotent writes obey R65. [§7]

---

## Explicitly not in stage 1

R157. No browser UI, no HTML routes, no `data-testid` contract. [stage-2]
R158. No authorizations, captures, voids, holds, `available`, `held`, or `total` fields. `GET /me` `balance` is the wallet total. Insufficient-funds checks use that balance. [stage-2]
R159. No statements, corrections, `as_of`, `known_at`, revisions, refunds, or correction batches. [stage-3] [stage-4]

---

## Decisions (ambiguities resolved)

D1. Fixture validation: required top-level `currency` (string), `minor_units` (0|2|3), `users` (array). Each user requires `id`, `email`, `password`, `display_name`, `handle`, `balance` (integral number ≥ 0). Optional `payments`, `requests`, `settlement_operator_ids`. Seeded payment requires `id`, `from_user_id`, `to_user_id`, `amount` (integer ≥ 1 and ≤ 1000000000), `visibility` (`public`|`private`); `note` optional default `""`. Seeded request requires `id`, `requester_id`, `payer_id`, `amount`, `status` in `pending|paid|declined|cancelled`; `note` optional; `payment_id` optional. Operator ids must refer to seeded users. Extra unknown fixture fields are ignored. Reason: §3.3 + §4 + §5 + §11 together require a replaceable consistent world; invalid fixtures must not partially apply.
D2. Every payment object includes `settlement_id` (`null` when not a settlement member). Reason: §11 says nonmembers expose null for that field.
D3. Email uniqueness and login compare the email string as stored (no case folding). Handle derivation still lowercases the local part. Reason: spec states uniqueness and form, not case-folding.
D4. `local@domain` means exactly one `@`, nonempty local, nonempty domain, no whitespace. A dot in the domain is not required. Reason: spec writes `local@domain`, not a full RFC 5322 grammar.
D5. `note` length is measured in Unicode code points (characters), max 200. Reason: spec says characters.
D6. Seeded passwords are accepted at any length (signup still enforces ≥ 8). Reason: fixture login requirement is independent of signup password rules.
D7. Generated payment/request/split/settlement/user ids are implementer-chosen opaque strings ≤ 64 chars; seeded ids are kept. Prefer a unique prefix + entropy form.
D8. Use a single-process in-memory store with one mutex (or equivalent transactional lock) covering every balance mutation, idempotency claim, reset, and import. Reason: simplest design that holds invariants under 50-way concurrency; state need not survive restart.
D9. Password hashing: bcrypt with a low cost (4) so reset of many users stays inside 10 s. Reason: R55 + R153.
D10. `GET /me` and payment/request objects must not include stage-2+ fields (`total`, `available`, `held`, `authorization_id`, `refund_of`, `payment_ids`, `remaining_amount`). Reason: stage N must not already implement stage N+1; extra fields risk hidden exact-shape checks.
D11. Auth endpoints and test endpoints do not require an idempotency key. Sending one is ignored.
D12. Decline/cancel/pay/get on a request id the caller cannot see: if the request exists but the caller is the wrong party, `403 forbidden`; if it does not exist, `404 not_found`. Do not hide existence behind 404 for the wrong party — the spec names 403 for wrong party and 404 for unknown. [§8]
D13. Settlement transfer `from_handle`/`to_handle` may name any existing users, including the operator. Operator permission is only the right to submit the batch.
D14. Currency string is stored and returned as given. Any currency string is accepted if `minor_units` is 0, 2, or 3. Reason: spec declares one currency in the fixture and names EUR/JPY/BHD as the fixtures used, not an enum reject-list.
D15. Query `direction` and `status` are exact, case-sensitive matches to the specified tokens.
D16. `limit`/`offset` omitted → 50 and 0. Present but empty → `422 validation_failed`.
D17. `created_at` for seeded payments/requests, if omitted, is the server time of that reset, with an explicit offset. All settlement member `created_at` values equal that settlement's `committed_at`.
D18. Signup/login missing required fields or empty `display_name` → `422 validation_failed`. Wrong JSON types → `400 malformed_request` except amount/note/visibility rules in R19.
D19. Concurrent signup of the same email: one `201`, the other `409 email_taken`. Concurrent signup that would derive the same handle: one `201`, the other `409 handle_taken` (or `409 email_taken` if emails also collide).
D20. Do not add undocumented routes that collide with later stages (`/authorizations`, `/statement`, `/payments/{id}/corrections`, `/payments/{id}/refunds`, `/correction-batches`). Unimplemented paths return `404` with the standard error body if authenticated, or `401` if a protected path is hit without a token. Unauthenticated test/auth/health paths remain as specified.
D21. On protected paths, check the bearer token before idempotency or body-field validation. No/malformed/unknown token is `401` even if `Idempotency-Key` is missing or the body is unparseable. Unparseable body with a valid token is `400 malformed_request`. Reason: idempotency is scoped to the authenticated user; the token is a header-level gate.
D22. If handle derivation would produce a string of length 0, signup is `422 validation_failed` and creates no account. This should not occur for a valid `local@domain` email. Reason: handles must match `^[a-z0-9_]{1,20}$`.
D23. Concurrent `pay` vs `decline` vs `cancel` on the same request: exactly one terminal transition commits. The others return `409 request_not_pending`, except a same-key replay of a successful pay (200 original payment) or a repeat decline/cancel of the same already-applied action (200 current state).
D24. Split validation order: empty or duplicate `participant_handles` is `422` before unknown-handle `404`. Settlement entry errors still take precedence in input order before insufficient funds, per §11.
D25. Cyclic or netting settlement transfers are valid when every wallet's post-batch balance is nonnegative.
D26. `204` responses have an empty body. JSON responses that have a body use `Content-Type: application/json; charset=utf-8`.
D27. Export `state` must be sufficient to restore splits and settlement membership so that a replay of `POST /splits` or `POST /settlements` returns the original body and ids. Reason: §10 preserve completed idempotent request bodies and original responses.
D28. Body amount `1000.5` (non-integer number) is `422 validation_failed`. `1000`, `1000.0`, and `1e3` remain valid. Query integers still require plain digits only.
D29. `GET /health`, signup, login, reset, export, and import never require a bearer token. A token sent to those paths is ignored.
