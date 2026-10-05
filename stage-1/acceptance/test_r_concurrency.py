from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from httpapi import Probe, as_json, expect_error, fresh_key
from world import PASSWORD, fixture, person


def _sum_all(probe: Probe) -> int:
    total = 0
    for email in (
        "src@acc.test",
        "dst@acc.test",
        "op@acc.test",
        "obs@acc.test",
        "p0@acc.test",
        "p1@acc.test",
        "p2@acc.test",
        "p3@acc.test",
        "p4@acc.test",
    ):
        token, _ = probe.login(email, PASSWORD)
        bal = probe.me(token)["balance"]
        assert bal >= 0
        total += bal
    return total


def test_R28_a_request_moves_money_at_most_once(probe: Probe, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 20},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]
    first = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key())
    assert first.status_code == 201
    before_s = probe.me(src)["balance"]
    before_d = probe.me(dst)["balance"]
    second = probe.call("POST", f"/requests/{rid}/pay", body={}, bearer=src, idem=fresh_key())
    expect_error(second, 409, "request_not_pending")
    assert probe.me(src)["balance"] == before_s
    assert probe.me(dst)["balance"] == before_d


def test_R154_fifty_in_flight_without_5xx_and_conservation(probe, origin, seed, total):
    src, _ = probe.login("src@acc.test", PASSWORD)

    def one(i: int):
        client = Probe(origin)
        try:
            if i % 2 == 0:
                return client.call("GET", "/me", bearer=src).status_code
            return client.call("GET", "/health").status_code
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=50) as pool:
        codes = list(pool.map(one, range(50)))
    assert all(c < 500 for c in codes)
    assert _sum_all(probe) == total


def test_R155_competing_writes_serialize_without_negatives(probe, origin, total):
    world = fixture(
        users=[
            person("id_src", "src@acc.test", "srcuser", 100),
            person("id_dst", "dst@acc.test", "dstuser", 0),
            person("id_op", "op@acc.test", "opuser", 0),
            person("id_obs", "obs@acc.test", "obsuser", 0),
            person("id_p0", "p0@acc.test", "p0user", 0),
            person("id_p1", "p1@acc.test", "p1user", 0),
            person("id_p2", "p2@acc.test", "p2user", 0),
            person("id_p3", "p3@acc.test", "p3user", 0),
            person("id_p4", "p4@acc.test", "p4user", 0),
        ],
        settlement_operator_ids=["id_op"],
    )
    probe.reset(world)
    src, _ = probe.login("src@acc.test", PASSWORD)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    op, _ = probe.login("op@acc.test", PASSWORD)
    rid = as_json(
        probe.call(
            "POST",
            "/requests",
            body={"payer_handle": "srcuser", "amount": 40},
            bearer=dst,
            idem=fresh_key(),
        )
    )["request_id"]

    def pay_direct(i: int):
        client = Probe(origin)
        try:
            token, _ = client.login("src@acc.test", PASSWORD)
            return client.call(
                "POST",
                "/payments",
                body={"to_handle": "dstuser", "amount": 40},
                bearer=token,
                idem=fresh_key(),
            )
        finally:
            client.close()

    def pay_request(_i: int):
        client = Probe(origin)
        try:
            token, _ = client.login("src@acc.test", PASSWORD)
            return client.call(
                "POST",
                f"/requests/{rid}/pay",
                body={},
                bearer=token,
                idem=fresh_key(),
            )
        finally:
            client.close()

    def settle(_i: int):
        client = Probe(origin)
        try:
            token, _ = client.login("op@acc.test", PASSWORD)
            return client.call(
                "POST",
                "/settlements",
                body={"transfers": [{"from_handle": "srcuser", "to_handle": "obsuser", "amount": 40}]},
                bearer=token,
                idem=fresh_key(),
            )
        finally:
            client.close()

    resps = []
    with ThreadPoolExecutor(max_workers=9) as pool:
        futs = [pool.submit(pay_direct, i) for i in range(3)]
        futs += [pool.submit(pay_request, i) for i in range(3)]
        futs += [pool.submit(settle, i) for i in range(3)]
        for fut in as_completed(futs):
            resps.append(fut.result())
    assert all(r.status_code < 500 for r in resps)
    created = [r for r in resps if r.status_code == 201]
    assert 0 < len(created) <= 2
    src_bal = probe.me(src)["balance"]
    dst_bal = probe.me(dst)["balance"]
    obs, _ = probe.login("obs@acc.test", PASSWORD)
    obs_bal = probe.me(obs)["balance"]
    assert src_bal >= 0 and dst_bal >= 0 and obs_bal >= 0
    assert src_bal + dst_bal + obs_bal + probe.me(op)["balance"] == 100
    assert _sum_all(probe) == 100


def test_R156_concurrent_identical_idempotent_writes(probe, origin, seed):
    key = fresh_key()
    body = {"to_handle": "dstuser", "amount": 7}

    def once(_i: int):
        client = Probe(origin)
        try:
            token, _ = client.login("src@acc.test", PASSWORD)
            return client.call("POST", "/payments", body=body, bearer=token, idem=key)
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        resps = list(pool.map(once, range(20)))
    codes = [r.status_code for r in resps]
    assert codes.count(201) == 1, codes
    assert codes.count(200) == 19, codes
    assert all(r.status_code < 500 for r in resps)
    pid = as_json(resps[0])["payment_id"]
    assert all(as_json(r)["payment_id"] == pid for r in resps)
    src, _ = probe.login("src@acc.test", PASSWORD)
    assert probe.me(src)["balance"] == 10_000 - 7


def test_R23_concurrent_load_never_5xx(probe, origin, seed):
    src, _ = probe.login("src@acc.test", PASSWORD)

    def one(i: int):
        client = Probe(origin)
        try:
            if i % 5 == 0:
                return client.call(
                    "POST",
                    "/payments",
                    body={"to_handle": "dstuser", "amount": 1},
                    bearer=src,
                    idem=fresh_key(),
                ).status_code
            if i % 5 == 1:
                return client.call("GET", "/activity", bearer=src).status_code
            if i % 5 == 2:
                return client.call("GET", "/requests", bearer=src, query={"limit": "bad"}).status_code
            if i % 5 == 3:
                return client.call("POST", "/payments", raw=b"{", bearer=src, idem=fresh_key()).status_code
            return client.call("GET", "/me", bearer=src).status_code
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=50) as pool:
        codes = list(pool.map(one, range(50)))
    assert all(c < 500 for c in codes)


def test_R27_concurrent_drain_never_goes_negative(probe, origin):
    world = fixture(
        users=[
            person("id_src", "src@acc.test", "srcuser", 25),
            person("id_dst", "dst@acc.test", "dstuser", 0),
            person("id_op", "op@acc.test", "opuser", 0),
            person("id_obs", "obs@acc.test", "obsuser", 0),
            person("id_p0", "p0@acc.test", "p0user", 0),
            person("id_p1", "p1@acc.test", "p1user", 0),
            person("id_p2", "p2@acc.test", "p2user", 0),
            person("id_p3", "p3@acc.test", "p3user", 0),
            person("id_p4", "p4@acc.test", "p4user", 0),
        ]
    )
    probe.reset(world)

    def once(_i: int):
        client = Probe(origin)
        try:
            token, _ = client.login("src@acc.test", PASSWORD)
            return client.call(
                "POST",
                "/payments",
                body={"to_handle": "dstuser", "amount": 10},
                bearer=token,
                idem=fresh_key(),
            )
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        resps = list(pool.map(once, range(10)))
    assert all(r.status_code in (201, 409) for r in resps)
    assert sum(1 for r in resps if r.status_code == 201) == 2
    src, _ = probe.login("src@acc.test", PASSWORD)
    dst, _ = probe.login("dst@acc.test", PASSWORD)
    assert probe.me(src)["balance"] == 5
    assert probe.me(dst)["balance"] == 20
    assert probe.me(src)["balance"] >= 0
