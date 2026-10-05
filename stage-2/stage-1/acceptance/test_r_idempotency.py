from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from httpapi import Probe, as_json, expect_error, fresh_key, same_json
from world import PASSWORD


def _src(probe: Probe) -> str:
    return probe.login("src@acc.test", PASSWORD)[0]


WRITE_PATHS = (
    ("POST", "/payments", {"to_handle": "dstuser", "amount": 1}),
    ("POST", "/requests", {"payer_handle": "dstuser", "amount": 1}),
    ("POST", "/splits", {"amount": 3, "participant_handles": ["dstuser"]}),
)


def test_R57_five_write_paths_require_idempotency_key(probe: Probe, seed):
    src = _src(probe)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    op, _ = probe.login("op@acc.test", PASSWORD)
    rid = as_json(
        probe.call("POST", "/requests", body={"payer_handle": "srcuser", "amount": 1}, bearer=dst, idem=fresh_key())
    )["request_id"]
    cases = [
        (src, "/payments", {"to_handle": "dstuser", "amount": 1}),
        (src, "/requests", {"payer_handle": "dstuser", "amount": 1}),
        (src, f"/requests/{rid}/pay", {}),
        (src, "/splits", {"amount": 2, "participant_handles": ["dstuser"]}),
        (op, "/settlements", {"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]}),
    ]
    for token, path, body in cases:
        missing = probe.call("POST", path, body=body, bearer=token)
        expect_error(missing, 400, "missing_idempotency_key")


def test_R58_keys_are_scoped_to_the_authenticated_user(probe: Probe, seed):
    src = _src(probe)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    key = "shared-key-string"
    a = probe.call("POST", "/payments", body={"to_handle": "obsuser", "amount": 1}, bearer=src, idem=key)
    b = probe.call("POST", "/payments", body={"to_handle": "obsuser", "amount": 1}, bearer=dst, idem=key)
    assert a.status_code == 201
    assert b.status_code == 201
    assert as_json(a)["payment_id"] != as_json(b)["payment_id"]


def test_R59_same_key_on_different_path_is_new_request(probe: Probe, seed):
    src = _src(probe)
    key = fresh_key()
    pay = probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src, idem=key)
    req = probe.call("POST", "/requests", body={"payer_handle": "dstuser", "amount": 1}, bearer=src, idem=key)
    assert pay.status_code == 201
    assert req.status_code == 201


def test_R60_absent_or_empty_key_is_400(probe: Probe, seed):
    src = _src(probe)
    expect_error(
        probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src),
        400,
        "missing_idempotency_key",
    )
    expect_error(
        probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src, idem=None),
        400,
        "missing_idempotency_key",
    )


def test_R61_first_success_is_201(probe: Probe, seed):
    src = _src(probe)
    resp = probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src, idem=fresh_key())
    assert resp.status_code == 201


def test_R62_replay_same_body_is_200_identical_json(probe: Probe, seed):
    src = _src(probe)
    key = fresh_key()
    body = {"to_handle": "dstuser", "amount": 2, "note": "same"}
    first = probe.call("POST", "/payments", body=body, bearer=src, idem=key)
    replay = probe.call(
        "POST",
        "/payments",
        raw=b'{"note":"same","amount":2,"to_handle":"dstuser"}',
        bearer=src,
        idem=key,
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert same_json(as_json(first), as_json(replay))


def test_R63_same_key_different_body_is_409(probe: Probe, seed):
    src = _src(probe)
    key = fresh_key()
    first = probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src, idem=key)
    assert first.status_code == 201
    expect_error(
        probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 2}, bearer=src, idem=key),
        409,
        "idempotency_key_reuse",
    )


def test_R64_failed_4xx_does_not_claim_key(probe: Probe, seed):
    src = _src(probe)
    key = fresh_key()
    expect_error(
        probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 50_000}, bearer=src, idem=key),
        409,
        "insufficient_funds",
    )
    ok = probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src, idem=key)
    assert ok.status_code == 201


def test_R65_concurrent_identical_unused_key(probe: Probe, origin, seed):
    key = fresh_key()
    body = {"to_handle": "dstuser", "amount": 1}

    def once(_i):
        client = Probe(origin)
        try:
            token, _ = client.login("src@acc.test", PASSWORD)
            return client.call("POST", "/payments", body=body, bearer=token, idem=key)
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=12) as pool:
        resps = list(pool.map(once, range(12)))
    codes = sorted(r.status_code for r in resps)
    assert codes.count(201) == 1, codes
    assert codes.count(200) == 11, codes
    bodies = [as_json(r) for r in resps]
    assert all(same_json(bodies[0], b) for b in bodies)
    src, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(src)["balance"] == 10_000 - 1


def test_R66_replay_after_resource_changes_does_not_move_money(probe: Probe, seed):
    src = _src(probe)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    key = fresh_key()
    created = as_json(
        probe.call("POST", "/requests", body={"payer_handle": "srcuser", "amount": 1}, bearer=dst, idem=key)
    )
    rid = created["request_id"]
    probe.call("POST", f"/requests/{rid}/cancel", body={}, bearer=dst)
    replay = probe.call(
        "POST", "/requests", body={"payer_handle": "srcuser", "amount": 1}, bearer=dst, idem=key
    )
    assert replay.status_code == 200
    assert as_json(replay)["request_id"] == rid
    listed = as_json(probe.call("GET", "/requests", bearer=dst))
    item = next(r for r in listed["requests"] if r["request_id"] == rid)
    assert item["status"] == "cancelled"


def test_R67_claimed_key_outranks_later_invalid_body(probe: Probe, seed):
    src = _src(probe)
    key = fresh_key()
    first = probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 1}, bearer=src, idem=key)
    assert first.status_code == 201
    expect_error(
        probe.call("POST", "/payments", body={"to_handle": "dstuser", "amount": 0}, bearer=src, idem=key),
        409,
        "idempotency_key_reuse",
    )


def test_R68_failed_settlement_validation_claims_no_key(probe: Probe, seed):
    op, _ = probe.login("op@acc.test", PASSWORD)
    key = fresh_key()
    bad = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "srcuser", "amount": 1}]},
        bearer=op,
        idem=key,
    )
    expect_error(bad, 422, "self_payment")
    ok = probe.call(
        "POST",
        "/settlements",
        body={"transfers": [{"from_handle": "srcuser", "to_handle": "dstuser", "amount": 1}]},
        bearer=op,
        idem=key,
    )
    assert ok.status_code == 201, ok.text
