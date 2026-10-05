import json
import math
import re
import secrets
from datetime import datetime, timezone
from typing import Any

HANDLE_RE = re.compile(r"^[a-z0-9_]{1,20}$")


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z").replace("+0000", "+00:00")


def gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def json_equal(a: Any, b: Any) -> bool:
    return canonical_json(a) == canonical_json(b)


def parse_amount(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value != int(value):
            return None
        return int(value)
    return None


def valid_email(email: Any) -> bool:
    if not isinstance(email, str):
        return False
    if any(ch.isspace() for ch in email):
        return False
    if email.count("@") != 1:
        return False
    local, domain = email.split("@", 1)
    return len(local) > 0 and len(domain) > 0


def derive_handle(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    out = []
    for ch in local:
        if "a" <= ch <= "z" or "0" <= ch <= "9" or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    h = "".join(out)[:20]
    return h


def note_len_ok(note: str) -> bool:
    return len(note) <= 200


def parse_query_int(raw: str | None, default: int | None) -> tuple[int | None, str | None]:
    if raw is None:
        if default is None:
            return None, "validation_failed"
        return default, None
    if raw == "":
        return None, "validation_failed"
    if not raw.isdigit():
        return None, "validation_failed"
    return int(raw), None


def split_shares(amount: int, n: int) -> list[int]:
    base = amount // n
    rem = amount % n
    return [base + (1 if i < rem else 0) for i in range(n)]
