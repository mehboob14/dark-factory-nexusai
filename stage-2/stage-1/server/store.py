from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import Any

import bcrypt

from server.util import (
    HANDLE_RE,
    canonical_json,
    derive_handle,
    gen_id,
    json_equal,
    note_len_ok,
    now_rfc3339,
    parse_amount,
    split_shares,
    valid_email,
)

BCRYPT_ROUNDS = 4


@dataclass
class User:
    id: str
    email: str
    password_hash: bytes
    display_name: str
    handle: str
    balance: int


@dataclass
class Payment:
    id: str
    from_user_id: str
    to_user_id: str
    amount: int
    note: str
    visibility: str
    request_id: str | None
    settlement_id: str | None
    created_at: str
    seq: int = 0


@dataclass
class MoneyRequest:
    id: str
    requester_id: str
    payer_id: str
    amount: int
    note: str
    status: str
    payment_id: str | None
    created_at: str
    seq: int = 0


@dataclass
class Split:
    id: str
    creator_id: str
    amount: int
    note: str
    participant_handles: list[str]
    shares: list[dict[str, Any]]
    request_ids: list[str]
    created_at: str


@dataclass
class Settlement:
    id: str
    committed_at: str
    payment_ids: list[str]


@dataclass
class IdempotencyRecord:
    method: str
    path: str
    body: Any
    response: Any
    http_status: int


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.ready = False
        self.currency = "EUR"
        self.minor_units = 2
        self.users: dict[str, User] = {}
        self.users_by_email: dict[str, str] = {}
        self.users_by_handle: dict[str, str] = {}
        self.tokens: dict[str, str] = {}
        self.payments: dict[str, Payment] = {}
        self.requests: dict[str, MoneyRequest] = {}
        self.splits: dict[str, Split] = {}
        self.settlements: dict[str, Settlement] = {}
        self.settlement_operator_ids: set[str] = set()
        self.idempotency: dict[tuple[str, str, str, str], IdempotencyRecord] = {}
        self._pay_seq = 0
        self._req_seq = 0

    def _next_pay_seq(self) -> int:
        self._pay_seq += 1
        return self._pay_seq

    def _next_req_seq(self) -> int:
        self._req_seq += 1
        return self._req_seq

    def mark_ready(self) -> None:
        with self._lock:
            self.ready = True

    def hash_password(self, password: str) -> bytes:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))

    def check_password(self, user: User, password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), user.password_hash)

    def user_public(self, user: User) -> dict[str, Any]:
        return {
            "user_id": user.id,
            "display_name": user.display_name,
            "handle": user.handle,
            "balance": user.balance,
            "currency": self.currency,
            "minor_units": self.minor_units,
        }

    def payment_public(self, p: Payment) -> dict[str, Any]:
        fu = self.users[p.from_user_id]
        tu = self.users[p.to_user_id]
        return {
            "payment_id": p.id,
            "from_user_id": p.from_user_id,
            "from_handle": fu.handle,
            "to_user_id": p.to_user_id,
            "to_handle": tu.handle,
            "amount": p.amount,
            "currency": self.currency,
            "note": p.note,
            "visibility": p.visibility,
            "request_id": p.request_id,
            "settlement_id": p.settlement_id,
            "created_at": p.created_at,
        }

    def request_public(self, r: MoneyRequest) -> dict[str, Any]:
        req = self.users[r.requester_id]
        pay = self.users[r.payer_id]
        return {
            "request_id": r.id,
            "requester_id": r.requester_id,
            "requester_handle": req.handle,
            "payer_id": r.payer_id,
            "payer_handle": pay.handle,
            "amount": r.amount,
            "currency": self.currency,
            "note": r.note,
            "status": r.status,
            "payment_id": r.payment_id,
            "created_at": r.created_at,
        }

    def total_balance(self) -> int:
        return sum(u.balance for u in self.users.values())

    def _validate_fixture(self, data: dict[str, Any]) -> str | None:
        if not isinstance(data, dict):
            return "malformed"
        currency = data.get("currency")
        minor_units = data.get("minor_units")
        users = data.get("users")
        if not isinstance(currency, str):
            return "validation_failed"
        if minor_units not in (0, 2, 3):
            return "validation_failed"
        if not isinstance(users, list):
            return "validation_failed"
        seen_ids: set[str] = set()
        seen_emails: set[str] = set()
        seen_handles: set[str] = set()
        parsed_users: list[dict[str, Any]] = []
        for u in users:
            if not isinstance(u, dict):
                return "validation_failed"
            uid = u.get("id")
            email = u.get("email")
            password = u.get("password")
            display_name = u.get("display_name")
            handle = u.get("handle")
            balance = u.get("balance")
            if not all(isinstance(x, str) for x in (uid, email, password, display_name, handle)):
                return "validation_failed"
            if len(uid) > 64:
                return "validation_failed"
            bal = parse_amount(balance)
            if bal is None or bal < 0:
                return "validation_failed"
            if not HANDLE_RE.match(handle):
                return "validation_failed"
            if uid in seen_ids or email in seen_emails or handle in seen_handles:
                return "validation_failed"
            seen_ids.add(uid)
            seen_emails.add(email)
            seen_handles.add(handle)
            parsed_users.append(
                {"id": uid, "email": email, "password": password, "display_name": display_name, "handle": handle, "balance": bal}
            )
        user_ids = seen_ids
        payments = data.get("payments", [])
        if payments is None:
            payments = []
        if not isinstance(payments, list):
            return "validation_failed"
        for p in payments:
            if not isinstance(p, dict):
                return "validation_failed"
            pid = p.get("id")
            fid = p.get("from_user_id")
            tid = p.get("to_user_id")
            amount = parse_amount(p.get("amount"))
            vis = p.get("visibility")
            note = p.get("note", "")
            if not isinstance(pid, str) or len(pid) > 64:
                return "validation_failed"
            if fid not in user_ids or tid not in user_ids:
                return "validation_failed"
            if amount is None or amount < 1 or amount > 1_000_000_000:
                return "validation_failed"
            if vis not in ("public", "private"):
                return "validation_failed"
            if note is None:
                note = ""
            if not isinstance(note, str) or not note_len_ok(note):
                return "validation_failed"
        reqs = data.get("requests", [])
        if reqs is None:
            reqs = []
        if not isinstance(reqs, list):
            return "validation_failed"
        for r in reqs:
            if not isinstance(r, dict):
                return "validation_failed"
            rid = r.get("id")
            requester = r.get("requester_id")
            payer = r.get("payer_id")
            amount = parse_amount(r.get("amount"))
            status = r.get("status")
            note = r.get("note", "")
            payment_id = r.get("payment_id")
            if not isinstance(rid, str) or len(rid) > 64:
                return "validation_failed"
            if requester not in user_ids or payer not in user_ids:
                return "validation_failed"
            if amount is None or amount < 1 or amount > 1_000_000_000:
                return "validation_failed"
            if status not in ("pending", "paid", "declined", "cancelled"):
                return "validation_failed"
            if note is None:
                note = ""
            if not isinstance(note, str) or not note_len_ok(note):
                return "validation_failed"
            if payment_id is not None and (not isinstance(payment_id, str) or len(payment_id) > 64):
                return "validation_failed"
        ops = data.get("settlement_operator_ids", [])
        if ops is None:
            ops = []
        if not isinstance(ops, list):
            return "validation_failed"
        for oid in ops:
            if not isinstance(oid, str) or oid not in user_ids:
                return "validation_failed"
        return None

    def apply_reset(self, data: dict[str, Any]) -> str | None:
        err = self._validate_fixture(data)
        if err:
            return err
        ts = now_rfc3339()
        self.currency = data["currency"]
        self.minor_units = data["minor_units"]
        self.users.clear()
        self.users_by_email.clear()
        self.users_by_handle.clear()
        self.tokens.clear()
        self.payments.clear()
        self.requests.clear()
        self.splits.clear()
        self.settlements.clear()
        self.idempotency.clear()
        self._pay_seq = 0
        self._req_seq = 0
        self.settlement_operator_ids = set(data.get("settlement_operator_ids") or [])
        for u in data["users"]:
            pw_hash = self.hash_password(u["password"])
            user = User(
                id=u["id"],
                email=u["email"],
                password_hash=pw_hash,
                display_name=u["display_name"],
                handle=u["handle"],
                balance=u["balance"],
            )
            self.users[user.id] = user
            self.users_by_email[user.email] = user.id
            self.users_by_handle[user.handle] = user.id
        for p in data.get("payments") or []:
            note = p.get("note", "")
            if note is None:
                note = ""
            created = p.get("created_at", ts)
            if not isinstance(created, str):
                created = ts
            pay = Payment(
                id=p["id"],
                from_user_id=p["from_user_id"],
                to_user_id=p["to_user_id"],
                amount=parse_amount(p["amount"]) or 0,
                note=note,
                visibility=p["visibility"],
                request_id=None,
                settlement_id=None,
                created_at=created,
                seq=self._next_pay_seq(),
            )
            self.payments[pay.id] = pay
        for r in data.get("requests") or []:
            note = r.get("note", "")
            if note is None:
                note = ""
            created = r.get("created_at", ts)
            if not isinstance(created, str):
                created = ts
            mr = MoneyRequest(
                id=r["id"],
                requester_id=r["requester_id"],
                payer_id=r["payer_id"],
                amount=parse_amount(r["amount"]) or 0,
                note=note,
                status=r["status"],
                payment_id=r.get("payment_id"),
                created_at=created,
                seq=self._next_req_seq(),
            )
            self.requests[mr.id] = mr
        return None

    def export_state(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "minor_units": self.minor_units,
            "settlement_operator_ids": sorted(self.settlement_operator_ids),
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "password_hash": u.password_hash.decode("latin-1"),
                    "display_name": u.display_name,
                    "handle": u.handle,
                    "balance": u.balance,
                }
                for u in self.users.values()
            ],
            "tokens": dict(self.tokens),
            "payments": [copy.deepcopy(p.__dict__) for p in self.payments.values()],
            "requests": [copy.deepcopy(r.__dict__) for r in self.requests.values()],
            "splits": [copy.deepcopy(s.__dict__) for s in self.splits.values()],
            "settlements": [copy.deepcopy(st.__dict__) for st in self.settlements.values()],
            "idempotency": {
                f"{uid}\0{key}\0{method}\0{path}": {
                    "method": rec.method,
                    "path": rec.path,
                    "body": rec.body,
                    "response": rec.response,
                    "http_status": rec.http_status,
                }
                for (uid, key, method, path), rec in self.idempotency.items()
            },
        }

    def import_state(self, state: dict[str, Any]) -> str | None:
        if not isinstance(state, dict):
            return "validation_failed"
        if not isinstance(state.get("currency"), str):
            return "validation_failed"
        if state.get("minor_units") not in (0, 2, 3):
            return "validation_failed"
        users_raw = state.get("users")
        if not isinstance(users_raw, list):
            return "validation_failed"
        self.users.clear()
        self.users_by_email.clear()
        self.users_by_handle.clear()
        for u in users_raw:
            if not isinstance(u, dict):
                return "validation_failed"
            try:
                ph = u["password_hash"].encode("latin-1")
            except Exception:
                return "validation_failed"
            user = User(
                id=u["id"],
                email=u["email"],
                password_hash=ph,
                display_name=u["display_name"],
                handle=u["handle"],
                balance=int(u["balance"]),
            )
            if user.id in self.users:
                return "validation_failed"
            self.users[user.id] = user
            self.users_by_email[user.email] = user.id
            self.users_by_handle[user.handle] = user.id
        self.currency = state["currency"]
        self.minor_units = state["minor_units"]
        ops = state.get("settlement_operator_ids", [])
        if not isinstance(ops, list):
            return "validation_failed"
        self.settlement_operator_ids = set(ops)
        tokens = state.get("tokens", {})
        if not isinstance(tokens, dict):
            return "validation_failed"
        self.tokens = {str(k): str(v) for k, v in tokens.items()}
        self.payments.clear()
        self._pay_seq = 0
        for p in state.get("payments") or []:
            if not isinstance(p, dict):
                return "validation_failed"
            pay = Payment(**p)
            self.payments[pay.id] = pay
            self._pay_seq = max(self._pay_seq, pay.seq)
        self.requests.clear()
        self._req_seq = 0
        for r in state.get("requests") or []:
            if not isinstance(r, dict):
                return "validation_failed"
            mr = MoneyRequest(**r)
            self.requests[mr.id] = mr
            self._req_seq = max(self._req_seq, mr.seq)
        self.splits.clear()
        for s in state.get("splits") or []:
            if not isinstance(s, dict):
                return "validation_failed"
            sp = Split(**s)
            self.splits[sp.id] = sp
        self.settlements.clear()
        for st in state.get("settlements") or []:
            if not isinstance(st, dict):
                return "validation_failed"
            sett = Settlement(**st)
            self.settlements[sett.id] = sett
        self.idempotency.clear()
        idem = state.get("idempotency", {})
        if not isinstance(idem, dict):
            return "validation_failed"
        for composite, rec in idem.items():
            if not isinstance(rec, dict):
                return "validation_failed"
            parts = composite.split("\0")
            if len(parts) not in (2, 4):
                return "validation_failed"
            if len(parts) == 2:
                uid, key = parts
                method = rec.get("method")
                path = rec.get("path")
                if not isinstance(method, str) or not isinstance(path, str):
                    return "validation_failed"
            else:
                uid, key, method, path = parts
            self.idempotency[(uid, key, method, path)] = IdempotencyRecord(
                method=rec["method"],
                path=rec["path"],
                body=rec["body"],
                response=rec["response"],
                http_status=rec["http_status"],
            )
        return None

    def resolve_idempotency(
        self,
        user_id: str,
        method: str,
        path: str,
        key: str | None,
        body: Any,
        required: bool,
    ) -> tuple[str | None, IdempotencyRecord | None, bool]:
        if not required:
            return None, None, False
        if key is None or key == "":
            return "missing_idempotency_key", None, False
        if len(key) < 1 or len(key) > 255:
            return "validation_failed", None, False
        rec = self.idempotency.get((user_id, key, method, path))
        if rec is None:
            return None, None, True
        if not json_equal(rec.body, body):
            return "idempotency_key_reuse", None, False
        return "replay", rec, False

    def save_idempotency(self, user_id: str, key: str, method: str, path: str, body: Any, response: Any, status: int) -> None:
        self.idempotency[(user_id, key, method, path)] = IdempotencyRecord(
            method, path, copy.deepcopy(body), copy.deepcopy(response), status
        )

    def signup(self, email: str, password: str, display_name: str) -> tuple[str, dict[str, Any] | None]:
        if not valid_email(email):
            return "validation_failed", None
        if not isinstance(password, str) or len(password) < 8:
            return "validation_failed", None
        if not isinstance(display_name, str) or display_name == "":
            return "validation_failed", None
        if email in self.users_by_email:
            return "email_taken", None
        handle = derive_handle(email)
        if not handle or not HANDLE_RE.match(handle):
            return "validation_failed", None
        if handle in self.users_by_handle:
            return "handle_taken", None
        uid = gen_id("u")
        user = User(
            id=uid,
            email=email,
            password_hash=self.hash_password(password),
            display_name=display_name,
            handle=handle,
            balance=0,
        )
        self.users[uid] = user
        self.users_by_email[email] = uid
        self.users_by_handle[handle] = uid
        token = gen_id("tok")
        self.tokens[token] = uid
        return "ok", {"user_id": uid, "display_name": display_name, "token": token}

    def login(self, email: str, password: str) -> tuple[str, dict[str, Any] | None]:
        if not isinstance(email, str) or not isinstance(password, str):
            return "malformed", None
        uid = self.users_by_email.get(email)
        if uid is None:
            return "unauthenticated", None
        user = self.users[uid]
        if not self.check_password(user, password):
            return "unauthenticated", None
        token = gen_id("tok")
        self.tokens[token] = uid
        return "ok", {"user_id": uid, "display_name": user.display_name, "token": token}

    def create_payment_direct(
        self, from_id: str, to_handle: str, amount: int, note: str, visibility: str
    ) -> tuple[str, dict[str, Any] | None]:
        if from_id == self.users_by_handle.get(to_handle):
            return "self_payment", None
        to_id = self.users_by_handle.get(to_handle)
        if to_id is None:
            return "not_found", None
        payer = self.users[from_id]
        if payer.balance < amount:
            return "insufficient_funds", None
        payer.balance -= amount
        self.users[to_id].balance += amount
        pid = gen_id("p")
        pay = Payment(
            id=pid,
            from_user_id=from_id,
            to_user_id=to_id,
            amount=amount,
            note=note,
            visibility=visibility,
            request_id=None,
            settlement_id=None,
            created_at=now_rfc3339(),
            seq=self._next_pay_seq(),
        )
        self.payments[pid] = pay
        return "ok", self.payment_public(pay)

    def create_request(self, requester_id: str, payer_handle: str, amount: int, note: str) -> tuple[str, dict[str, Any] | None]:
        if requester_id == self.users_by_handle.get(payer_handle):
            return "self_request", None
        payer_id = self.users_by_handle.get(payer_handle)
        if payer_id is None:
            return "not_found", None
        rid = gen_id("rq")
        mr = MoneyRequest(
            id=rid,
            requester_id=requester_id,
            payer_id=payer_id,
            amount=amount,
            note=note,
            status="pending",
            payment_id=None,
            created_at=now_rfc3339(),
            seq=self._next_req_seq(),
        )
        self.requests[rid] = mr
        return "ok", self.request_public(mr)

    def pay_request(self, payer_id: str, request_id: str, visibility: str) -> tuple[str, dict[str, Any] | None]:
        mr = self.requests.get(request_id)
        if mr is None:
            return "not_found", None
        if mr.payer_id != payer_id:
            return "forbidden", None
        if mr.status != "pending":
            return "request_not_pending", None
        if self.users[payer_id].balance < mr.amount:
            return "insufficient_funds", None
        self.users[payer_id].balance -= mr.amount
        self.users[mr.requester_id].balance += mr.amount
        pid = gen_id("p")
        pay = Payment(
            id=pid,
            from_user_id=payer_id,
            to_user_id=mr.requester_id,
            amount=mr.amount,
            note=mr.note,
            visibility=visibility,
            request_id=mr.id,
            settlement_id=None,
            created_at=now_rfc3339(),
            seq=self._next_pay_seq(),
        )
        self.payments[pid] = pay
        mr.status = "paid"
        mr.payment_id = pid
        return "ok", self.payment_public(pay)

    def decline_request(self, payer_id: str, request_id: str) -> tuple[str, dict[str, Any] | None]:
        mr = self.requests.get(request_id)
        if mr is None:
            return "not_found", None
        if mr.payer_id != payer_id:
            return "forbidden", None
        if mr.status == "declined":
            return "ok", self.request_public(mr)
        if mr.status != "pending":
            return "request_not_pending", None
        mr.status = "declined"
        return "ok", self.request_public(mr)

    def cancel_request(self, requester_id: str, request_id: str) -> tuple[str, dict[str, Any] | None]:
        mr = self.requests.get(request_id)
        if mr is None:
            return "not_found", None
        if mr.requester_id != requester_id:
            return "forbidden", None
        if mr.status == "cancelled":
            return "ok", self.request_public(mr)
        if mr.status != "pending":
            return "request_not_pending", None
        mr.status = "cancelled"
        return "ok", self.request_public(mr)

    def create_split(
        self, caller_id: str, amount: int, participant_handles: list[str], note: str
    ) -> tuple[str, dict[str, Any] | None]:
        if not participant_handles:
            return "validation_failed", None
        if len(participant_handles) != len(set(participant_handles)):
            return "validation_failed", None
        for h in participant_handles:
            if h not in self.users_by_handle:
                return "not_found", None
        caller = self.users[caller_id]
        amounts = split_shares(amount, len(participant_handles))
        shares = [{"handle": h, "amount": a} for h, a in zip(participant_handles, amounts)]
        req_objs: list[dict[str, Any]] = []
        req_ids: list[str] = []
        for h, share_amt in zip(participant_handles, amounts):
            if h == caller.handle:
                continue
            payer_id = self.users_by_handle[h]
            rid = gen_id("rq")
            mr = MoneyRequest(
                id=rid,
                requester_id=caller_id,
                payer_id=payer_id,
                amount=share_amt,
                note=note,
                status="pending",
                payment_id=None,
                created_at=now_rfc3339(),
            )
            self.requests[rid] = mr
            req_ids.append(rid)
            req_objs.append(self.request_public(mr))
        sid = gen_id("sp")
        sp = Split(
            id=sid,
            creator_id=caller_id,
            amount=amount,
            note=note,
            participant_handles=list(participant_handles),
            shares=shares,
            request_ids=req_ids,
            created_at=now_rfc3339(),
        )
        self.splits[sid] = sp
        return "ok", {
            "split_id": sid,
            "amount": amount,
            "currency": self.currency,
            "note": note,
            "shares": shares,
            "requests": req_objs,
            "created_at": sp.created_at,
        }

    def settlement_affordable(self, deltas: dict[str, int]) -> bool:
        for uid, user in self.users.items():
            if user.balance + deltas.get(uid, 0) < 0:
                return False
        return True

    def create_settlement(self, operator_id: str, transfers: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
        if operator_id not in self.settlement_operator_ids:
            return "forbidden", None
        validated: list[tuple[str, str, int, str, str]] = []
        for t in transfers:
            if not isinstance(t, dict):
                return "validation_failed", None
            fh = t.get("from_handle")
            th = t.get("to_handle")
            amount = parse_amount(t.get("amount"))
            if not isinstance(fh, str) or not isinstance(th, str):
                return "validation_failed", None
            if amount is None or amount < 1 or amount > 1_000_000_000:
                return "validation_failed", None
            if "note" in t:
                note = t.get("note")
                if not isinstance(note, str) or not note_len_ok(note):
                    return "validation_failed", None
            else:
                note = ""
            if "visibility" in t:
                vis = t.get("visibility")
                if not isinstance(vis, str) or vis not in ("public", "private"):
                    return "validation_failed", None
            else:
                vis = "public"
            if fh not in self.users_by_handle:
                return "not_found", None
            if th not in self.users_by_handle:
                return "not_found", None
            if fh == th:
                return "self_payment", None
            validated.append((fh, th, amount, note, vis))
        deltas: dict[str, int] = {}
        for fh, th, amount, _, _ in validated:
            fid = self.users_by_handle[fh]
            tid = self.users_by_handle[th]
            deltas[fid] = deltas.get(fid, 0) - amount
            deltas[tid] = deltas.get(tid, 0) + amount
        if not self.settlement_affordable(deltas):
            return "insufficient_funds", None
        committed = now_rfc3339()
        sid = gen_id("st")
        payment_ids: list[str] = []
        payment_objs: list[dict[str, Any]] = []
        for fh, th, amount, note, vis in validated:
            fid = self.users_by_handle[fh]
            tid = self.users_by_handle[th]
            self.users[fid].balance -= amount
            self.users[tid].balance += amount
            pid = gen_id("p")
            pay = Payment(
                id=pid,
                from_user_id=fid,
                to_user_id=tid,
                amount=amount,
                note=note,
                visibility=vis,
                request_id=None,
                settlement_id=sid,
                created_at=committed,
                seq=self._next_pay_seq(),
            )
            self.payments[pid] = pay
            payment_ids.append(pid)
            payment_objs.append(self.payment_public(pay))
        self.settlements[sid] = Settlement(id=sid, committed_at=committed, payment_ids=payment_ids)
        return "ok", {"settlement_id": sid, "committed_at": committed, "payments": payment_objs}

    def list_requests(
        self, user_id: str, direction: str | None, status: str | None, limit: int, offset: int
    ) -> dict[str, Any]:
        items = []
        for r in self.requests.values():
            if r.requester_id != user_id and r.payer_id != user_id:
                continue
            if direction == "incoming" and r.payer_id != user_id:
                continue
            if direction == "outgoing" and r.requester_id != user_id:
                continue
            if status is not None and r.status != status:
                continue
            items.append(r)
        items.sort(key=lambda x: (x.created_at, x.seq), reverse=True)
        page = items[offset : offset + limit]
        has_more = len(items) > offset + limit
        return {"requests": [self.request_public(r) for r in page], "has_more": has_more}

    def list_activity(self, user_id: str, limit: int, offset: int) -> dict[str, Any]:
        visible: list[Payment] = []
        for p in self.payments.values():
            if p.visibility == "public" or p.from_user_id == user_id or p.to_user_id == user_id:
                visible.append(p)
        visible.sort(key=lambda x: (x.created_at, x.seq), reverse=True)
        page = visible[offset : offset + limit]
        has_more = len(visible) > offset + limit
        return {"payments": [self.payment_public(p) for p in page], "has_more": has_more}


store = Store()
