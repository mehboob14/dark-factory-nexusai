# Pocketful stage 2 — requirements contract

Source: `C:\Development\darkfactory\dark-factory-wearedevs\pocketful\spec\stage-1.md` and `stage-2.md` (read in full).
Stage 2 extends stage 1 with browser UI and payment authorizations (holds and captures).
All stage-1 requirements (R1–R159, D1–D29) continue to apply.

This list covers the stage-2 additions. Build every line. Do not implement stage 3+ (statements, corrections, `as_of`, `known_at`) or stage 4+ (refunds, batch corrections).

---

## Browser routes and content negotiation

R160. The following routes must be reachable by URL and return HTML for `Accept: text/html`; without that header, return JSON. [§2]
R161. Routes: `/` (balance, pay form, request form, activity feed), `/requests` (incoming/outgoing requests), `/split` (split form), `/signup` (signup), `/login` (login). [§2]
R162. `/requests` serves both API and browser: the same route returns JSON to API clients and HTML to browsers. [§2]
R163. The browser experience must feel coherent and presentation-ready, not a test harness. Calm, trustworthy character. UI must feel like a consumer finance product. [§2]
R164. Available funds must be the clearest monetary value once holds exist, with total and held visibly secondary. [§2]
R165. Payments, requests, splits and authorizations must be easy to scan. Status, direction, privacy and money movement must be understandable without interpreting raw API data. [§2]
R166. Consistent visual system for typography, spacing, colour, controls and feedback. Primary actions easy to identify. [§2]
R167. Available, held, pending, loading, successful, refused and uncertain states visually distinct and satisfying behavioural requirements. Format people, amounts and timestamps for people first; expose technical identifiers only when they help. [§2]
R168. Required flows remain clear and usable at 375 CSS-pixel viewport and conventional desktop widths, without horizontal scrolling. [§2]
R169. Inputs need visible labels, keyboard focus must be apparent, text and controls need sufficient contrast. Empty, loading and error states considered. Navigation consistent across required routes. [§2]
R170. Custom illustrations, brand assets or exact reference matches not required. [§2]

---

## data-testid contract

### Signup and login

R171. `signup-email`, `signup-password`, `signup-display-name` inputs; `signup-submit` button. [§2]
R172. `login-email`, `login-password`, `login-submit` inputs/button. [§2]
R173. `auth-error`: error message; present only when there is one. [§2]
R174. `current-user`: visible on every screen when signed in; text contains the display name. [§2]
R175. `current-handle`: text is exactly the caller's handle, with no `@` and no surrounding words. [§2]
R176. `logout-button`: button present when signed in. [§2]

### Balance and pay — `/`

R177. `wallet-balance`: text exactly the formatted amount, with `data-amount="{minor units}"`. Formatted: decimal with exactly `minor_units` places, single space, currency code. For `minor_units: 0`, no decimal point: `1200 JPY`. For `minor_units: 2`, `100.00 EUR`. [§2]
R178. `wallet-available`: formatted `available`, with `data-amount`. **Present this as the headline number** — it is what the user can actually spend. [§2]
R179. `wallet-held`: formatted `held`, with `data-amount`. Absent when `held` is zero. [§2]
R180. Pay form: `pay-handle`, `pay-amount`, `pay-note` (inputs); `pay-visibility` (select, options `public`/`private`); `pay-submit` (button). [§2]
R181. `pay-amount` is a **decimal** string as a person would type it, e.g., `15.00`. [§2]
R182. `pay-error`: error message when payment refused (including insufficient funds). Shown only when there is an error. [§2]
R183. Request form: `request-handle`, `request-amount`, `request-note`, `request-submit`. [§2]
R184. `request-error`: error message when request refused. [§2]
R185. After pay success, keep the form's values. Submitting without changing a field must not send another payment: `wallet-balance` falls once, feed contains one payment, `pay-error` absent. Changing a field makes next submission a new request. Retries follow stage-1 §7 idempotency rules. [§2]
R186. Form accepts decimal amounts and submits minor units to API. With `minor_units: 2`, `15.00` and `15` both submit `1500`; `15.5` submits `1550`. Nonnumeric input or more than `minor_units` decimal places must show form's error without sending. E.g., `15.005` is rejected, not rounded. [§2]

### Activity feed — `/`

R187. `activity-list`: container; children are newest first in the DOM. [§2]
R188. `activity-item-{payment_id}`: one per visible payment; carries `data-visibility="public"` or `data-visibility="private"`. [§2]
R189. `activity-parties-{payment_id}`: text contains both handles. [§2]
R190. `activity-amount-{payment_id}`: text exactly the formatted amount. [§2]
R191. `activity-note-{payment_id}`: text exactly the note. Present even when note is empty. [§2]
R192. `empty-activity`: shown instead of list when nothing is visible. [§2]

### Requests — `/requests`

R193. `incoming-list`, `outgoing-list`: containers. [§2]
R194. `request-item-{request_id}`: one per request; carries `data-status="{status}"`. [§2]
R195. `request-amount-{request_id}`: text exactly the formatted amount. [§2]
R196. `request-pay-{request_id}`: button; present only on `pending` incoming request. [§2]
R197. `request-decline-{request_id}`: button; present only on `pending` incoming request. [§2]
R198. `request-cancel-{request_id}`: button; present only on `pending` outgoing request. [§2]
R199. `request-error`: shown when pay, decline or cancel is refused. [§2]
R200. `empty-requests`: shown when both lists are empty. [§2]

### Split — `/split`

R201. `split-amount`: decimal input, same rule as `pay-amount`. [§2]
R202. `split-handles`: text input; handles separated by commas, in order. [§2]
R203. `split-note`, `split-submit`: input and button. [§2]
R204. `split-preview`: shows computed shares before submitting. Contains one `split-share-{handle}` per participant. [§2]
R205. `split-share-{handle}`: text exactly the formatted share amount. [§2]
R206. `split-preview` must show shares the server would compute by stage-1 §9 rule, before anything is posted. Preview and submitted split must have identical shares. [§2]
R207. `split-error`: error message when split is refused. [§2]

### Authorizations — `/authorizations`

R208. New route `/authorizations`, shared with `/requests` (HTML for `Accept: text/html`, JSON otherwise). [§2]
R209. `wallet-balance`: formatted `total`, retaining existing display and `data-amount`. [§2]
R210. `wallet-available`: formatted `available`, with `data-amount`. **Present as headline number.** [§2]
R211. `wallet-held`: formatted `held`, with `data-amount`. Absent when `held` is zero. [§2]
R212. Authorize form: `authorize-handle`, `authorize-amount`, `authorize-note`, `authorize-visibility`, `authorize-submit`. Same input rules as pay form. [§2]
R213. `authorize-error`: shown when authorization is refused, including insufficient available funds. [§2]
R214. `authorization-list`: container on `/authorizations`. Children newest first in the DOM. [§2]
R215. `authorization-item-{authorization_id}`: carries `data-status="{status}"`. [§2]
R216. `authorization-amount-{id}`: text exactly the formatted authorised amount. [§2]
R217. `authorization-captured-{id}`: formatted captured amount. Present only when `status` is `captured`. [§2]
R218. `authorization-expires-{id}`: text is RFC 3339 `expires_at`. [§2]
R219. `authorization-capture-amount-{id}`: decimal input, pre-filled with the remaining amount. Present only on incoming `open` authorization. [§2]
R220. `authorization-capture-{id}`: button; present only on incoming `open` authorization. [§2]
R221. `authorization-void-{id}`: button; present only on outgoing `open` authorization. [§2]
R222. `authorization-error`: shown when capture or void is refused. [§2]
R223. `empty-authorizations`: shown when list is empty. [§2]

---

## State after actions

R224. After any successful action on `/`, the balance, feed and request lists on the same page must show new state without manual reload. Navigation must wait for write to succeed before refreshing data. Any mechanism fine, including full navigation. **No live-update requirement** — another client may change state, but this browser need only refresh after its own action or explicit refresh. [§2]
R225. Same rule applies after successful action on `/requests`: lists and balance must refresh. [§2]
R226. Same rule applies after successful action on `/split`: balance and request lists must refresh. [§2]
R227. Same rule applies after successful action on `/authorizations`: lists and balance must refresh. [§2]

---

## Competing clients and uncertain outcomes

R228. Add `wallet-refresh` button on `/` that refreshes balance and feed without clearing pay form. **Latest refresh wins:** delayed earlier read must not overwrite later refresh, including when responses arrive out of order. [§2]
R229. Another client may spend balance after this browser reads it. Refused payment shows `pay-error`, refreshes balance/feed, and preserves all pay inputs. [§2]
R230. Request cancelled elsewhere while pay button is visible must show `request-error` when payment is refused and refresh the request list so stale pay button disappears. [§2]
R231. If payment response is lost, including after `POST /payments` commits, show `pay-uncertain` (nonempty text), not `pay-error`. Keep form retryable with **same key and body**. Successful retry removes both error/uncertainty elements, refreshes balance and feed, and moves money exactly once. Unknown outcomes not confirmed rejections. [§2]
R232. No background polling, live synchronization or recovery across page reloads required. Same balance refresh rules apply to available and held amounts. [§2]

---

## Existing clients after upgrade

R233. Stage-2 service must accept export from same team's stage-1 service. Browser signed in before export/import upgrade must remain signed in afterwards. [§2]
R234. Existing pending requests remain payable through request screen. Payment whose response was lost before export remains retryable after import with same body and key; UI must recover original payment and refresh imported balance. [§2]
R235. These requirements apply when import completes between browser requests; migration during in-flight request not required. No page reload or new screen required. Form and pending retry identity must survive upgrade. [§2]

---

## GET /me endpoint changes

R236. `GET /me` adds three fields: `total` (wallet total, equals `balance`), `available` (total − held), `held` (sum of open holds). [§2]
R237. `balance` and `total` are always equal. `held` is sum of open holds. `available = total − held`, never negative. [§2]
R238. With no open holds, `balance`, `total`, and `available` agree and `held` is zero; every earlier behaviour unchanged. [§2]

---

## Authorizations and captures

R239. A payment may be **authorised** now and **captured** later, for full amount or less. Authorisation places **hold** on payer's wallet: reserves money without moving it. Capturing moves money; final capture releases uncaptured remainder. Nonfinal captures keep remainder held. Open authorisation expires and releases remainder on its own. [§2]
R240. Sum of all wallet `total` values always equals seeded total from last reset. Hold moves no money; payments, settlements and captures transfer money between wallets. [§2]
R241. `available = total − held` must never be negative. Held funds cannot fund new payments, authorizations or settlement net debits. Captures may spend money reserved for them. [§2]
R242. Cumulative captures must not exceed authorized amount. Each idempotent capture moves money once. Closed hold cannot be captured again. [§2]

---

## Existing API changes for authorizations

R243. `POST /payments` remains immediate transfer. Must not leave intermediate hold or require separate capture. [§2]
R244. Every `409 insufficient_funds` in stage 1 (on `POST /payments`, `POST /requests/{id}/pay`, settlements) is now evaluated against `available`. With no holds, result unchanged. [§2]
R245. Paying a request remains immediate. Authorizing a request is out of scope. [§2]
R246. `POST /splits` unchanged. [§2]
R247. There are now seven idempotent write paths: stage 1's five, authorizations, and captures. Same replay rules apply independently to each. [§2]

---

## Fixture model changes

R248. Fixture gains `authorization_ttl_seconds` (service-wide default lifetime) and `authorizations` array. [§2]
R249. `authorization_ttl_seconds` applies to every authorisation created through API. Defaults to 600 when omitted. If supplied, must be positive integer number of seconds. Seeded authorisations carry their own absolute `expires_at` instead. [§2]
R250. User's seeded `balance` is still `total`. **`available` is derived, never seeded** — service subtracts seeded open holds itself. [§2]
R251. Sum of seeded unexpired open holds larger than user's `balance` is reset error: `422 validation_failed` from `POST /_test/reset`, changing nothing, exactly like negative seeded balance. [§2]
R252. Seeded authorization `status` is `open`, `captured`, `voided`, or `expired`. Only `open` holds anything. [§2]
R253. Earlier fixture may omit `authorizations` altogether; omission means empty list. [§2]
R254. Authorization whose `expires_at` is at or before now is `expired` and holds no funds. Reads and writes must reflect expiry even if no request occurred at deadline. [§2]
R255. `GET /authorizations` must show `status: "expired"` for expired holds. `GET /me` must include released remainder in `available`. Seeded expiry times at least an hour from reset, in past or future; newly created may have shorter lifetimes. [§2]

---

## POST /authorizations

R256. `Idempotency-Key` required. Caller is the payer. [§2]
R257. Body: `to_handle` (required), `amount` (required), optional `note` default `""`, optional `visibility` default `"public"`. [§2]
R258. Success `201` body: `{authorization_id, from_user_id, from_handle, to_user_id, to_handle, amount, captured_amount, currency, note, visibility, status:"open", expires_at, payment_id:null, created_at}`. [§2]
R259. `expires_at` is `created_at` plus `authorization_ttl_seconds`. [§2]
R260. Caller's `available` below `amount` → `409 insufficient_funds`. [§2]
R261. `amount` below 1, above 1000000000, or not integer → `422 validation_failed`. [§2]
R262. `to_handle` is caller's own handle → `422 self_payment`. [§2]
R263. `note` over 200 characters, or `visibility` neither `public` nor `private` → `422 validation_failed`. [§2]
R264. Unknown `to_handle` → `404 not_found`. [§2]
R265. Open authorization is **not** feed item and never appears in `GET /activity`. [§2]

---

## POST /authorizations/{id}/capture

R266. `Idempotency-Key` required. Only receiver (to party) may capture. [§2]
R267. Body: optional `amount` (defaults to authorization's remaining amount), optional `final` (boolean, default `true`). [§2]
R268. `{}` and `{"amount": 2000}` are different JSON values; reusing key across them is `409 idempotency_key_reuse`. [§2]
R269. Success `201` body: created **payment** in exact shape `POST /payments` returns, with `authorization_id` set to this authorization, `request_id: null`. Payment's `amount` is captured amount; `note` and `visibility` copied from authorization; appears in feed by visibility rule. Payments without authorization carry `authorization_id: null`; existing `request_id` semantics unchanged. [§2]
R270. By default (or `final: true`), authorization becomes `captured`, carries `captured_amount` and `payment_id`, and **releases uncaptured remainder immediately**: capturing 1500 of 2000 returns 500 to payer's `available` in same step. [§2]
R271. **Default: one final capture per authorization.** Second capture after final is `409 authorization_not_open`. [§2]
R272. **Extended capture mode:** `{"amount": 700, "final": false}` keeps remainder held. With `final: false` and uncaptured remainder, status stays `open`; further captures allowed up to remainder. Capturing entire remainder closes it even with `final: false`. Final capture closes and releases any remainder. [§2]
R273. `captured_amount` is cumulative; `payment_id` is latest capture; `payment_ids` lists every capture in order. [§2]
R274. Every authorization response adds `remaining_amount`: amount still held, zero when closed. Void and expiry can close partially captured authorization, release only remainder, preserve all capture records. New fields do not change idempotency body equality. [§2]
R275. Authorization not `open` → `409 authorization_not_open`. [§2]
R276. `expires_at` at or before now → `409 authorization_expired`. [§2]
R277. `amount` above authorization's uncaptured remainder → `422 capture_exceeds_authorization`. [§2]
R278. `amount` below 1, or not integer → `422 validation_failed`. [§2]
R279. Caller not receiver → `403 forbidden`. Unknown authorization → `404 not_found`. [§2]

---

## POST /authorizations/{id}/void

R280. **Only payer may void** — from party releasing their own hold. No idempotency key. [§2]
R281. `200` with authorization, `status: "voided"`, hold released. Voiding already-voided is `200` with current state. `captured` or `expired` → `409 authorization_not_open`. [§2]

---

## Authorization visibility and access

R282. For existing authorization, capture and void return `403 forbidden` when caller not permitted party, including callers who are neither party. `GET /authorizations` returns only authorizations involving caller. [§2]

---

## GET /authorizations

R283. Lists authorizations where caller is payer or receiver. Newest first by `created_at`. [§2]
R284. Query `direction`: `outgoing` (caller is payer), `incoming` (caller is receiver), or absent for both. [§2]
R285. Query `status`: one of `open|captured|voided|expired`, or absent for all. Authorization expired by clock matches `expired`, never `open`. [§2]
R286. `limit`, `offset` and `has_more` behave exactly as on `GET /requests`. [§2]

---

## UI and wallet display

R287. UI must reflect seeded and newly created holds. Show available funds as user's spending balance, including immediately after reset with open holds. [§2]
R288. A new route `/authorizations` shared with `/requests`: serve HTML for `Accept: text/html`, JSON otherwise. [§2]

---

## Concurrency for authorizations

R289. Concurrent requests must produce same results as executing one at a time in some order, and requirements above hold at every read. [§2]

---

## Explicitly not in stage 2

R290. No statements, `as_of` queries, corrections, `known_at` parameter. [stage-3]
R291. No refunds, correction batches, `refund_of` field. [stage-4]

---

## Stage 1 requirements preserved

All stage-1 requirements (R1–R159, D1–D29) remain in force. Do not remove stage-1 functionality.
