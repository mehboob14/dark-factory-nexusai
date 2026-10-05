from __future__ import annotations

import copy
import time

from httpapi import Probe, as_json, expect_error, fresh_key, same_json
from world import PASSWORD, default_world


def test_R143_export_shape_unauthenticated(probe: Probe, seed):
    resp = probe.call("GET", "/_test/export", wait=12)
    assert resp.status_code == 200
    body = as_json(resp)
    assert body["track"] == "pocketful"
    assert body["format_version"] == 1
    assert "state" in body and isinstance(body["state"], dict)


def test_R144_export_is_a_frozen_snapshot(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    snap = probe.export()
    held = copy.deepcopy(snap)
    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 17},
        bearer=src,
        idem=fresh_key(),
    )
    assert same_json(snap, held)
    probe.import_state(held)
    after = probe.me(src)["balance"]
    assert after == 10_000


def test_R145_import_replaces_and_returns_204(probe: Probe, seed):
    snap = probe.export()
    resp = probe.import_state(snap, expect_ok=False)
    assert resp.status_code == 204
    assert not resp.text.strip()


def test_R146_import_accepts_own_export(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    key = fresh_key()
    pay = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 11},
        bearer=src,
        idem=key,
    )
    assert pay.status_code == 201
    snap = probe.export()
    probe.reset(default_world())
    probe.import_state(snap)
    assert probe.me(src)["balance"] == 10_000 - 11
    replay = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 11},
        bearer=src,
        idem=key,
    )
    assert replay.status_code == 200
    assert as_json(replay)["payment_id"] == as_json(pay)["payment_id"]


def test_R147_import_is_replacement_not_merge(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 3},
        bearer=src,
        idem=fresh_key(),
    )
    snap = probe.export()
    probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 5},
        bearer=src,
        idem=fresh_key(),
    )
    probe.import_state(snap)
    probe.import_state(snap)
    feed = as_json(probe.call("GET", "/activity", bearer=src))["payments"]
    assert len(feed) == 1
    assert feed[0]["amount"] == 3
    assert probe.me(src)["balance"] == 10_000 - 3


def test_R148_import_errors_do_not_change_destination(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    keep = probe.me(src)["balance"]
    expect_error(probe.call("POST", "/_test/import", raw=b"{", wait=12), 400, "malformed_request")
    expect_error(
        probe.import_state({"track": "other", "format_version": 1, "state": {}}, expect_ok=False),
        422,
        "validation_failed",
    )
    expect_error(
        probe.import_state({"track": "pocketful", "format_version": 2, "state": {}}, expect_ok=False),
        422,
        "validation_failed",
    )
    expect_error(
        probe.import_state({"track": "pocketful", "format_version": 1}, expect_ok=False),
        422,
        "validation_failed",
    )
    assert probe.me(src)["balance"] == keep


def test_R149_import_preserves_tokens_hashes_balances_and_retries(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    op, _ = probe.login("op@acc.test", PASSWORD)
    key = fresh_key()
    pay = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 8, "note": "keep"},
        bearer=src,
        idem=key,
    )
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 2},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    split_key = fresh_key()
    split = probe.call(
        "POST",
        "/splits",
        body={"amount": 3, "participant_handles": ["dstuser"]},
        bearer=src,
        idem=split_key,
    )
    assert split.status_code == 201
    snap = probe.export()
    probe.import_state(snap)
    assert probe.me(src)["user_id"] == "id_src"
    assert probe.me(src)["balance"] == 10_000 - 8
    replay = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 8, "note": "keep"},
        bearer=src,
        idem=key,
    )
    assert replay.status_code == 200
    assert as_json(replay)["payment_id"] == as_json(pay)["payment_id"]
    listed = as_json(probe.call("GET", "/requests", bearer=dst))
    assert any(r["request_id"] == rid for r in listed["requests"])
    split_replay = probe.call(
        "POST",
        "/splits",
        body={"amount": 3, "participant_handles": ["dstuser"]},
        bearer=src,
        idem=split_key,
    )
    assert split_replay.status_code == 200
    assert as_json(split_replay)["split_id"] == as_json(split)["split_id"]
    settle = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
        bearer=op,
        idem=fresh_key(),
    )
    assert settle.status_code == 201


def test_R150_import_does_not_replay_money(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    pay = as_json(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 13},
            bearer=src,
            idem=fresh_key(),
        )
    )
    snap = probe.export()
    probe.import_state(snap)
    assert probe.me(src)["balance"] == 10_000 - 13
    feed = as_json(probe.call("GET", "/activity", bearer=src))["payments"]
    match = next(p for p in feed if p["payment_id"] == pay["payment_id"])
    assert match["created_at"] == pay["created_at"]
    assert match["amount"] == 13


def test_R151_failed_keys_reusable_after_import(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    key = fresh_key()
    expect_error(
        probe.call(
            "POST",
            "/payments",
            body={"to_handle": "dstuser", "amount": 50_000},
            bearer=src,
            idem=key,
        ),
        409,
        "insufficient_funds",
    )
    snap = probe.export()
    probe.import_state(snap)
    ok = probe.call(
        "POST",
        "/payments",
        body={"to_handle": "dstuser", "amount": 1},
        bearer=src,
        idem=key,
    )
    assert ok.status_code == 201
    still = probe.call("GET", "/me", bearer=src)
    assert still.status_code == 200


def test_R152_import_wipes_destination_then_reset_is_clean(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    extra, _ = probe.signup("wipe@acc.test", PASSWORD, "Wipe")
    snap = probe.export()
    probe.reset(default_world())
    other, _ = probe.signup("otherwipe@acc.test", PASSWORD, "Other")
    probe.import_state(snap)
    gone = probe.call("POST", "/auth/login", body={"email": "otherwipe@acc.test", "password": PASSWORD})
    expect_error(gone, 401, "unauthenticated")
    assert probe.call("GET", "/me", bearer=extra).status_code == 200
    probe.reset(default_world())
    expect_error(probe.call("GET", "/me", bearer=extra), 401, "unauthenticated")
    expect_error(probe.call("GET", "/me", bearer=src), 401, "unauthenticated")
    fresh, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(fresh)["balance"] == 10_000
    assert as_json(probe.call("GET", "/activity", bearer=fresh))["payments"] == []


def test_R153_test_control_calls_finish_inside_ten_seconds(probe: Probe, seed):
    started = time.monotonic()
    probe.reset(default_world())
    assert time.monotonic() - started <= 10.0
    started = time.monotonic()
    snap = probe.export()
    assert time.monotonic() - started <= 10.0
    started = time.monotonic()
    probe.import_state(snap)
    assert time.monotonic() - started <= 10.0
