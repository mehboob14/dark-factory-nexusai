from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse

from server.store import store
from server.util import note_len_ok, parse_amount, parse_query_int

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

JSON_CT = "application/json; charset=utf-8"

PUBLIC_PATHS = {
    ("GET", "/health"),
    ("POST", "/_test/reset"),
    ("POST", "/auth/signup"),
    ("POST", "/auth/login"),
    ("GET", "/_test/export"),
    ("POST", "/_test/import"),
}


def err(status: int, code: str, message: str | None = None) -> JSONResponse:
    if message is None:
        message = code
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        media_type=JSON_CT,
    )



def ok_json(status: int, body: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content=body, media_type=JSON_CT)


def html_response(content: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(content=content, status_code=status)


def parse_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth is None:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        return None
    return parts[1]


def auth_user_id(request: Request) -> str | None:
    token = parse_bearer(request)
    if token is None:
        return None
    with store._lock:
        return store.tokens.get(token)


async def read_json_object(request: Request) -> tuple[dict[str, Any] | None, str | None]:
    raw = await request.body()
    if not raw:
        return {}, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "malformed_request"
    if not isinstance(data, dict):
        return None, "malformed_request"
    return data, None


def idempotency_key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")


def handle_idempotent(
    user_id: str,
    method: str,
    path: str,
    key: str | None,
    body: dict[str, Any],
    required: bool,
    handler,
) -> JSONResponse:
    with store._lock:
        code, rec, is_new = store.resolve_idempotency(user_id, method, path, key, body, required)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec is not None:
            return ok_json(200, rec.response)
        if not is_new:
            return err(500, "validation_failed")
        result = handler()
        if isinstance(result, JSONResponse):
            return result
        status, resp_body = result
        if status == 201 and key:
            store.save_idempotency(user_id, key, method, path, body, resp_body, 201)
        return ok_json(status, resp_body)


@app.on_event("startup")
def _startup() -> None:
    store.mark_ready()


@app.get("/health")
def health() -> JSONResponse:
    with store._lock:
        if not store.ready:
            return JSONResponse(status_code=503, content={"status": "starting"}, media_type=JSON_CT)
    return ok_json(200, {"status": "ok"})


@app.post("/_test/reset")
async def test_reset(request: Request) -> Response:
    raw = await request.body()
    try:
        data = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return err(400, "malformed_request")
    if not isinstance(data, dict):
        return err(400, "malformed_request")
    with store._lock:
        prev = store.export_state()
        reset_err = store.apply_reset(data)
        if reset_err == "malformed":
            store.import_state(prev)
            return err(400, "malformed_request")
        if reset_err:
            store.import_state(prev)
            return err(422, "validation_failed")
    return Response(status_code=204)


@app.get("/_test/export")
def test_export() -> JSONResponse:
    with store._lock:
        snap = store.export_state()
    return ok_json(200, {"track": "pocketful", "format_version": 1, "state": snap})


@app.post("/_test/import")
async def test_import(request: Request) -> Response:
    data, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert data is not None
    if data.get("track") != "pocketful" or data.get("format_version") != 1:
        return err(422, "validation_failed")
    state = data.get("state")
    with store._lock:
        prev = store.export_state()
        imp_err = store.import_state(state)
        if imp_err:
            store.import_state(prev)
            return err(422, "validation_failed")
    return Response(status_code=204)


@app.post("/auth/signup")
async def auth_signup(request: Request) -> JSONResponse:
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    email = body.get("email")
    password = body.get("password")
    display_name = body.get("display_name")
    if email is None or password is None or display_name is None:
        return err(422, "validation_failed")
    if not isinstance(email, str) or not isinstance(password, str) or not isinstance(display_name, str):
        return err(400, "malformed_request")
    with store._lock:
        code, resp = store.signup(email, password, display_name)
    if code == "email_taken":
        return err(409, "email_taken")
    if code == "handle_taken":
        return err(409, "handle_taken")
    if code == "validation_failed":
        return err(422, "validation_failed")
    return ok_json(201, resp)


@app.post("/auth/login")
async def auth_login(request: Request) -> JSONResponse:
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    email = body.get("email")
    password = body.get("password")
    if email is None or password is None:
        return err(422, "validation_failed")
    if not isinstance(email, str) or not isinstance(password, str):
        return err(400, "malformed_request")
    with store._lock:
        code, resp = store.login(email, password)
    if code == "unauthenticated":
        return err(401, "unauthenticated")
    if code == "malformed":
        return err(400, "malformed_request")
    return ok_json(200, resp)


@app.get("/me")
def get_me(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    with store._lock:
        user = store.users[uid]
        return ok_json(200, store.user_public(user))


def validate_payment_body(body: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    to_handle = body.get("to_handle")
    amount_raw = body.get("amount")
    if to_handle is None or amount_raw is None:
        return "validation_failed", None
    if not isinstance(to_handle, str):
        return "malformed_request", None
    amount = parse_amount(amount_raw)
    if amount is None:
        return "validation_failed", None
    if amount < 1 or amount > 1_000_000_000:
        return "validation_failed", None
    if "note" in body:
        note = body.get("note")
        if not isinstance(note, str):
            return "validation_failed", None
    else:
        note = ""
    if not note_len_ok(note):
        return "validation_failed", None
    if "visibility" in body:
        visibility = body.get("visibility")
        if not isinstance(visibility, str) or visibility not in ("public", "private"):
            return "validation_failed", None
    else:
        visibility = "public"
    return None, {"to_handle": to_handle, "amount": amount, "note": note, "visibility": visibility}


@app.post("/payments")
async def post_payments(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    key = idempotency_key(request)

    def run():
        verr, fields = validate_payment_body(body)
        if verr == "malformed_request":
            return err(400, "malformed_request")
        if verr:
            return err(422, verr)
        assert fields is not None
        code, resp = store.create_payment_direct(
            uid, fields["to_handle"], fields["amount"], fields["note"], fields["visibility"]
        )
        if code == "self_payment":
            return err(422, "self_payment")
        if code == "not_found":
            return err(404, "not_found")
        if code == "insufficient_funds":
            return err(409, "insufficient_funds")
        return 201, resp

    with store._lock:
        code, rec, is_new = store.resolve_idempotency(uid, "POST", "/payments", key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        result = run()
        if isinstance(result, JSONResponse):
            return result
        status, resp_body = result
        if status == 201 and key:
            store.save_idempotency(uid, key, "POST", "/payments", body, resp_body, 201)
        return ok_json(status, resp_body)


def validate_request_body(body: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    payer_handle = body.get("payer_handle")
    amount_raw = body.get("amount")
    if payer_handle is None or amount_raw is None:
        return "validation_failed", None
    if not isinstance(payer_handle, str):
        return "malformed_request", None
    amount = parse_amount(amount_raw)
    if amount is None or amount < 1 or amount > 1_000_000_000:
        return "validation_failed", None
    if "note" in body:
        note = body.get("note")
        if not isinstance(note, str) or not note_len_ok(note):
            return "validation_failed", None
    else:
        note = ""
    return None, {"payer_handle": payer_handle, "amount": amount, "note": note}


@app.post("/requests")
async def post_requests(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    key = idempotency_key(request)
    with store._lock:
        code, rec, is_new = store.resolve_idempotency(uid, "POST", "/requests", key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        verr, fields = validate_request_body(body)
        if verr == "malformed_request":
            return err(400, "malformed_request")
        if verr:
            return err(422, verr)
        assert fields is not None
        rcode, resp = store.create_request(uid, fields["payer_handle"], fields["amount"], fields["note"])
        if rcode == "self_request":
            return err(422, "self_request")
        if rcode == "not_found":
            return err(404, "not_found")
        if key:
            store.save_idempotency(uid, key, "POST", "/requests", body, resp, 201)
        return ok_json(201, resp)


@app.get("/requests")
def get_requests(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    q = request.query_params
    direction = q.get("direction")
    status = q.get("status")
    if direction is not None and direction not in ("incoming", "outgoing"):
        return err(422, "validation_failed")
    if status is not None and status not in ("pending", "paid", "declined", "cancelled"):
        return err(422, "validation_failed")
    limit, le = parse_query_int(q.get("limit"), 50)
    offset, oe = parse_query_int(q.get("offset"), 0)
    if le or oe:
        return err(422, "validation_failed")
    assert limit is not None and offset is not None
    if limit < 1 or limit > 200 or offset < 0:
        return err(422, "validation_failed")
    with store._lock:
        return ok_json(200, store.list_requests(uid, direction, status, limit, offset))


@app.post("/requests/{request_id}/pay")
async def pay_request(request_id: str, request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    path = f"/requests/{request_id}/pay"
    key = idempotency_key(request)
    with store._lock:
        code, rec, _ = store.resolve_idempotency(uid, "POST", path, key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        if "visibility" in body:
            visibility = body.get("visibility")
            if not isinstance(visibility, str) or visibility not in ("public", "private"):
                return err(422, "validation_failed")
        else:
            visibility = "public"
        pcode, resp = store.pay_request(uid, request_id, visibility)
        if pcode == "not_found":
            return err(404, "not_found")
        if pcode == "forbidden":
            return err(403, "forbidden")
        if pcode == "request_not_pending":
            return err(409, "request_not_pending")
        if pcode == "insufficient_funds":
            return err(409, "insufficient_funds")
        if key:
            store.save_idempotency(uid, key, "POST", path, body, resp, 201)
        return ok_json(201, resp)


@app.post("/requests/{request_id}/decline")
def decline_request(request_id: str, request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    with store._lock:
        code, resp = store.decline_request(uid, request_id)
    if code == "not_found":
        return err(404, "not_found")
    if code == "forbidden":
        return err(403, "forbidden")
    if code == "request_not_pending":
        return err(409, "request_not_pending")
    return ok_json(200, resp)


@app.post("/requests/{request_id}/cancel")
def cancel_request(request_id: str, request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    with store._lock:
        code, resp = store.cancel_request(uid, request_id)
    if code == "not_found":
        return err(404, "not_found")
    if code == "forbidden":
        return err(403, "forbidden")
    if code == "request_not_pending":
        return err(409, "request_not_pending")
    return ok_json(200, resp)


@app.post("/splits")
async def post_splits(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    key = idempotency_key(request)
    with store._lock:
        code, rec, _ = store.resolve_idempotency(uid, "POST", "/splits", key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        amount_raw = body.get("amount")
        handles = body.get("participant_handles")
        note = body.get("note", "")
        amount = parse_amount(amount_raw) if amount_raw is not None else None
        if amount is None or amount < 1 or amount > 1_000_000_000:
            return err(422, "validation_failed")
        if not isinstance(handles, list):
            return err(422, "validation_failed")
        if not all(isinstance(h, str) for h in handles):
            return err(422, "validation_failed")
        if note is None or not isinstance(note, str) or not note_len_ok(note):
            return err(422, "validation_failed")
        scode, resp = store.create_split(uid, amount, handles, note)
        if scode == "validation_failed":
            return err(422, "validation_failed")
        if scode == "not_found":
            return err(404, "not_found")
        if key:
            store.save_idempotency(uid, key, "POST", "/splits", body, resp, 201)
        return ok_json(201, resp)


@app.get("/activity")
def get_activity(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    q = request.query_params
    limit, le = parse_query_int(q.get("limit"), 50)
    offset, oe = parse_query_int(q.get("offset"), 0)
    if le or oe:
        return err(422, "validation_failed")
    assert limit is not None and offset is not None
    if limit < 1 or limit > 200 or offset < 0:
        return err(422, "validation_failed")
    with store._lock:
        return ok_json(200, store.list_activity(uid, limit, offset))


@app.post("/settlements")
async def post_settlements(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    key = idempotency_key(request)
    with store._lock:
        code, rec, _ = store.resolve_idempotency(uid, "POST", "/settlements", key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        transfers = body.get("transfers")
        if not isinstance(transfers, list) or len(transfers) < 1 or len(transfers) > 32:
            return err(422, "validation_failed")
        scode, resp = store.create_settlement(uid, transfers)
        if scode == "forbidden":
            return err(403, "forbidden")
        if scode == "validation_failed":
            return err(422, "validation_failed")
        if scode == "not_found":
            return err(404, "not_found")
        if scode == "self_payment":
            return err(422, "self_payment")
        if scode == "insufficient_funds":
            return err(409, "insufficient_funds")
        if key:
            store.save_idempotency(uid, key, "POST", "/settlements", body, resp, 201)
        return ok_json(201, resp)


@app.get("/")
async def home(request: Request) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html = """<!DOCTYPE html>
<html>
<head><title>Pocketful</title><style>
body { font-family: sans-serif; margin: 20px; }
.balance-display { font-size: 24px; margin: 20px 0; }
form { margin: 20px 0; padding: 10px; border: 1px solid #ccc; }
input, select, button { display: block; margin: 5px 0; padding: 5px; width: 200px; }
button { width: auto; cursor: pointer; }
.error { color: red; display: none; }
.activity-item { border: 1px solid #ddd; margin: 5px 0; padding: 5px; }
</style></head>
<body>
<div data-testid="current-user" style="display:none;"></div>
<button data-testid="logout-button" style="display:none;">Logout</button>
<h1>Wallet</h1>
<div class="balance-display">
  <div>Balance: <span data-testid="wallet-balance" data-amount="0">0.00 EUR</span></div>
  <div>Available: <span data-testid="wallet-available" data-amount="0">0.00 EUR</span></div>
</div>
<h2>Send Payment</h2>
<form id="pay-form">
  <label>To: <input data-testid="pay-handle" type="text" placeholder="handle" /></label>
  <label>Amount: <input data-testid="pay-amount" type="text" placeholder="0.00" /></label>
  <label>Note: <input data-testid="pay-note" type="text" placeholder="" /></label>
  <label>Visibility: <select data-testid="pay-visibility"><option value="public">public</option><option value="private">private</option></select></label>
  <button data-testid="pay-submit" type="submit">Pay</button>
  <div data-testid="pay-error" class="error"></div>
</form>
<h2>Request Payment</h2>
<form id="request-form">
  <label>From: <input data-testid="request-handle" type="text" placeholder="handle" /></label>
  <label>Amount: <input data-testid="request-amount" type="text" placeholder="0.00" /></label>
  <label>Note: <input data-testid="request-note" type="text" placeholder="" /></label>
  <button data-testid="request-submit" type="submit">Request</button>
  <div data-testid="request-error" class="error"></div>
</form>
<h2>Activity Feed</h2>
<div data-testid="activity-list"></div>
<div data-testid="empty-activity">No activity</div>
</body>
</html>
"""
        return html_response(html)
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    with store._lock:
        user = store.users[uid]
        return ok_json(200, store.user_public(user))


@app.get("/requests")
async def requests_page(request: Request) -> Response:
    accept = request.headers.get("accept", "")

    uid = auth_user_id(request)
    if uid is None:
        if "text/html" in accept:
            return err(401, "unauthenticated")
        return err(401, "unauthenticated")

    direction = request.query_params.get("direction")
    status = request.query_params.get("status")
    limit = parse_query_int(request.query_params.get("limit"))
    offset = parse_query_int(request.query_params.get("offset"))

    if limit is None:
        limit = 50
    if offset is None:
        offset = 0
    if limit < 1 or limit > 200 or offset < 0:
        return err(422, "validation_failed")
    if direction and direction not in ("incoming", "outgoing"):
        return err(422, "validation_failed")
    if status and status not in ("pending", "paid", "declined", "cancelled"):
        return err(422, "validation_failed")

    with store._lock:
        result = store.list_requests(uid, direction, status, limit, offset)

    if "text/html" in accept:
        html = """<!DOCTYPE html>
<html>
<head><title>Requests</title><style>
body { font-family: sans-serif; margin: 20px; }
.request-item { border: 1px solid #ddd; margin: 5px 0; padding: 5px; }
button { margin: 2px; padding: 2px 5px; cursor: pointer; }
</style></head>
<body>
<h1>Money Requests</h1>
<h2>Incoming Requests</h2>
<div data-testid="incoming-list">""" + "".join(
            f'<div data-testid="request-item-{r["request_id"]}" data-status="{r["status"]}" class="request-item">'
            f'{r["requester_handle"]} → {r["payer_handle"]}: '
            f'<span data-testid="request-amount-{r["request_id"]}">{r["amount"]}</span> {r["note"]}'
            f'{"<button data-testid=\"request-pay-" + r["request_id"] + "\">Pay</button>" if r["status"] == "pending" else ""}'
            f'{"<button data-testid=\"request-decline-" + r["request_id"] + "\">Decline</button>" if r["status"] == "pending" else ""}'
            f'</div>'
            for r in result.get("requests", []) if r.get("status") == "pending" and r.get("payer_id") == uid
        ) + """
</div>
<h2>Outgoing Requests</h2>
<div data-testid="outgoing-list">""" + "".join(
            f'<div data-testid="request-item-{r["request_id"]}" data-status="{r["status"]}" class="request-item">'
            f'{r["requester_handle"]} → {r["payer_handle"]}: '
            f'<span data-testid="request-amount-{r["request_id"]}">{r["amount"]}</span> {r["note"]}'
            f'{"<button data-testid=\"request-cancel-" + r["request_id"] + "\">Cancel</button>" if r["status"] == "pending" else ""}'
            f'</div>'
            for r in result.get("requests", []) if r.get("status") == "pending" and r.get("requester_id") == uid
        ) + """
</div>
<div data-testid="empty-requests" style="display:""" + ("none" if result.get("requests") else "block") + """;>No requests</div>
<div data-testid="request-error" style="display:none;"></div>
</body>
</html>
"""
        return html_response(html)

    return ok_json(200, result)


@app.get("/split")
async def split_page(request: Request) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html = """<!DOCTYPE html>
<html>
<head><title>Split</title><style>
body { font-family: sans-serif; margin: 20px; }
form { padding: 10px; border: 1px solid #ccc; }
input, button { display: block; margin: 5px 0; padding: 5px; width: 300px; }
button { width: auto; cursor: pointer; }
#split-preview { margin: 10px 0; padding: 10px; border: 1px solid #eee; }
.split-share { margin: 5px 0; }
.error { color: red; display: none; }
</style></head>
<body>
<h1>Split Payment</h1>
<form id="split-form">
  <label>Amount: <input data-testid="split-amount" type="text" placeholder="0.00" /></label>
  <label>Participants (comma-separated handles): <input data-testid="split-handles" type="text" placeholder="alice,bob,charlie" /></label>
  <label>Note: <input data-testid="split-note" type="text" placeholder="" /></label>
  <div data-testid="split-preview" id="split-preview"></div>
  <button data-testid="split-submit" type="submit">Split</button>
  <div data-testid="split-error" class="error"></div>
</form>
</body>
</html>
"""
        return html_response(html)
    return err(404, "not_found")


@app.get("/signup")
async def signup_page(request: Request) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html = """<!DOCTYPE html>
<html>
<head><title>Sign Up</title><style>
body { font-family: sans-serif; margin: 20px; }
form { padding: 20px; border: 1px solid #ccc; max-width: 300px; }
input, button { display: block; margin: 10px 0; padding: 8px; width: 100%; box-sizing: border-box; }
button { width: auto; cursor: pointer; }
.error { color: red; display: none; }
a { display: block; margin-top: 20px; }
</style></head>
<body>
<h1>Create Account</h1>
<form id="signup-form">
  <label>Email: <input data-testid="signup-email" type="email" placeholder="user@example.com" /></label>
  <label>Password: <input data-testid="signup-password" type="password" placeholder="(min 8 characters)" /></label>
  <label>Display Name: <input data-testid="signup-display-name" type="text" placeholder="Your Name" /></label>
  <button data-testid="signup-submit" type="submit">Sign Up</button>
  <div data-testid="auth-error" class="error"></div>
</form>
<p><a href="/login">Already have an account? Log in</a></p>
</body>
</html>
"""
        return html_response(html)
    return err(404, "not_found")


@app.get("/login")
async def login_page(request: Request) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html = """<!DOCTYPE html>
<html>
<head><title>Log In</title><style>
body { font-family: sans-serif; margin: 20px; }
form { padding: 20px; border: 1px solid #ccc; max-width: 300px; }
input, button { display: block; margin: 10px 0; padding: 8px; width: 100%; box-sizing: border-box; }
button { width: auto; cursor: pointer; }
.error { color: red; display: none; }
.nav { display: none; }
.nav.shown { display: block; margin-top: 20px; }
a { display: block; margin: 5px 0; }
</style></head>
<body>
<h1>Log In</h1>
<form id="login-form">
  <label>Email: <input data-testid="login-email" type="email" placeholder="user@example.com" /></label>
  <label>Password: <input data-testid="login-password" type="password" placeholder="" /></label>
  <button data-testid="login-submit" type="submit">Log In</button>
  <div data-testid="auth-error" class="error"></div>
</form>
<div class="nav">
  <p>Don't have an account? <a href="/signup">Sign up</a></p>
</div>
<div data-testid="current-user" style="display:none;"></div>
<div data-testid="current-handle" style="display:none;"></div>
</body>
</html>
"""
        return html_response(html)
    return err(404, "not_found")


@app.post("/authorizations")
async def post_authorizations(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    key = idempotency_key(request)

    def run():
        verr, fields = validate_payment_body(body)
        if verr == "malformed_request":
            return err(400, "malformed_request")
        if verr:
            return err(422, verr)
        assert fields is not None
        code, resp = store.create_authorization(
            uid, fields["to_handle"], fields["amount"], fields["note"], fields["visibility"]
        )
        if code == "self_payment":
            return err(422, "self_payment")
        if code == "not_found":
            return err(404, "not_found")
        if code == "insufficient_funds":
            return err(409, "insufficient_funds")
        return 201, resp

    with store._lock:
        code, rec, is_new = store.resolve_idempotency(uid, "POST", "/authorizations", key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        result = run()
        if isinstance(result, JSONResponse):
            return result
        status, resp_body = result
        if status == 201 and key:
            store.save_idempotency(uid, key, "POST", "/authorizations", body, resp_body, 201)
        return ok_json(status, resp_body)


@app.post("/authorizations/{auth_id}/capture")
async def capture_authorization(auth_id: str, request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    body, parse_err = await read_json_object(request)
    if parse_err:
        return err(400, parse_err)
    assert body is not None
    key = idempotency_key(request)

    def run():
        cap_amount_raw = body.get("amount")
        if cap_amount_raw is not None:
            cap_amount = parse_amount(cap_amount_raw)
            if cap_amount is None or cap_amount < 1 or cap_amount > 1_000_000_000:
                return err(422, "validation_failed")
        else:
            cap_amount = None

        code, resp = store.capture_authorization(auth_id, uid, cap_amount)
        if code == "not_found":
            return err(404, "not_found")
        if code == "forbidden":
            return err(403, "forbidden")
        if code == "authorization_not_open":
            return err(409, "authorization_not_open")
        if code == "authorization_expired":
            return err(409, "authorization_expired")
        if code == "capture_exceeds_authorization":
            return err(422, "capture_exceeds_authorization")
        if code == "validation_failed":
            return err(422, "validation_failed")
        return 201, resp

    with store._lock:
        code, rec, is_new = store.resolve_idempotency(uid, "POST", f"/authorizations/{auth_id}/capture", key, body, True)
        if code == "missing_idempotency_key":
            return err(400, "missing_idempotency_key")
        if code == "validation_failed":
            return err(422, "validation_failed")
        if code == "idempotency_key_reuse":
            return err(409, "idempotency_key_reuse")
        if code == "replay" and rec:
            return ok_json(200, rec.response)
        result = run()
        if isinstance(result, JSONResponse):
            return result
        status, resp_body = result
        if status == 201 and key:
            store.save_idempotency(uid, key, "POST", f"/authorizations/{auth_id}/capture", body, resp_body, 201)
        return ok_json(status, resp_body)


@app.post("/authorizations/{auth_id}/void")
def void_authorization(auth_id: str, request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")

    with store._lock:
        code, resp = store.void_authorization(auth_id, uid)
        if code == "not_found":
            return err(404, "not_found")
        if code == "forbidden":
            return err(403, "forbidden")
        if code == "authorization_not_open":
            return err(409, "authorization_not_open")
        return ok_json(200, resp)


@app.get("/authorizations")
def get_authorizations(request: Request) -> JSONResponse:
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")

    direction = request.query_params.get("direction")
    status = request.query_params.get("status")
    limit = parse_query_int(request.query_params.get("limit"))
    offset = parse_query_int(request.query_params.get("offset"))

    if limit is None or offset is None:
        return err(422, "validation_failed")
    if limit < 1 or limit > 200:
        return err(422, "validation_failed")
    if offset < 0:
        return err(422, "validation_failed")
    if direction is not None and direction not in ("incoming", "outgoing"):
        return err(422, "validation_failed")
    if status is not None and status not in ("open", "captured", "voided", "expired"):
        return err(422, "validation_failed")
    if limit == 0:
        limit = 50
    if offset is None:
        offset = 0

    with store._lock:
        result = store.list_authorizations(uid, direction, status, limit, offset)
    return ok_json(200, result)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def catch_all(full_path: str, request: Request) -> JSONResponse:
    method = request.method
    path = "/" + full_path if full_path else "/"
    if (method, path) in PUBLIC_PATHS:
        return err(404, "not_found")
    uid = auth_user_id(request)
    if uid is None:
        return err(401, "unauthenticated")
    return err(404, "not_found")
