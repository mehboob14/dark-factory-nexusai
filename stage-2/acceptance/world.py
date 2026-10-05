"""Fixture builders for the acceptance suite.

Users, emails, and handles are suite-owned. They are not the shipped sample
identities and are not special-cased by name in the checks.
"""

from __future__ import annotations

from typing import Any


PASSWORD = "suite-pass-ok"
SHORT_SEEDED_PASSWORD = "shortpw"


def person(
    uid: str,
    email: str,
    handle: str,
    balance: int,
    display_name: str | None = None,
    password: str = PASSWORD,
) -> dict[str, Any]:
    return {
        "id": uid,
        "email": email,
        "password": password,
        "display_name": display_name or handle,
        "handle": handle,
        "balance": balance,
    }


def fixture(
    *,
    currency: str = "EUR",
    minor_units: int = 2,
    users: list[dict[str, Any]] | None = None,
    payments: list[dict[str, Any]] | None = None,
    requests: list[dict[str, Any]] | None = None,
    settlement_operator_ids: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "currency": currency,
        "minor_units": minor_units,
        "users": users if users is not None else default_users(),
    }
    if payments is not None:
        body["payments"] = payments
    if requests is not None:
        body["requests"] = requests
    if settlement_operator_ids is not None:
        body["settlement_operator_ids"] = settlement_operator_ids
    if extra:
        body.update(extra)
    return body


def default_users() -> list[dict[str, Any]]:
    return [
        person("id_src", "src@acc.test", "srcuser", 10_000),
        person("id_dst", "dst@acc.test", "dstuser", 2_500),
        person("id_op", "op@acc.test", "opuser", 5_000),
        person("id_obs", "obs@acc.test", "obsuser", 1_000),
        person("id_p0", "p0@acc.test", "p0user", 8_000),
        person("id_p1", "p1@acc.test", "p1user", 0),
        person("id_p2", "p2@acc.test", "p2user", 0),
        person("id_p3", "p3@acc.test", "p3user", 0),
        person("id_p4", "p4@acc.test", "p4user", 0),
    ]


def default_world() -> dict[str, Any]:
    return fixture(settlement_operator_ids=["id_op"])


def seeded_total(body: dict[str, Any]) -> int:
    return sum(int(u["balance"]) for u in body["users"])
