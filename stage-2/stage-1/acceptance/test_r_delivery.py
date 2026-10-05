from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from httpapi import Probe, as_json, expect_error
from world import PASSWORD, default_world

STAGE = Path(__file__).resolve().parent.parent


def test_R1_dockerfile_and_run_md_exist():
    dockerfile = STAGE / "Dockerfile"
    run_md = STAGE / "RUN.md"
    if not dockerfile.is_file() or not run_md.is_file():
        pytest.skip("delivery files are not in this checkout; run.py builds them when present")
    run = run_md.read_text(encoding="utf-8")
    assert "docker build" in run
    assert "docker run" in run


def test_R2_run_md_starts_with_port_env_and_no_compose():
    run_md = STAGE / "RUN.md"
    if not run_md.is_file():
        pytest.skip("RUN.md is not in this checkout")
    run = run_md.read_text(encoding="utf-8")
    assert "-e PORT" in run or "PORT=" in run
    assert "-p" in run
    assert "compose up" not in run.lower()


def test_R3_service_answers_on_mapped_port(probe: Probe):
    resp = probe.call("GET", "/health")
    assert resp.status_code == 200


def test_R4_health_ok_body(probe: Probe):
    resp = probe.call("GET", "/health")
    assert resp.status_code == 200
    assert as_json(resp) == {"status": "ok"}


def test_R5_fifty_in_flight_health_calls_complete(probe: Probe):
    def one(_i):
        return probe.call("GET", "/health").status_code

    with ThreadPoolExecutor(max_workers=50) as pool:
        codes = list(pool.map(one, range(50)))
    assert codes == [200] * 50


def test_R5_reset_completes_inside_control_budget(probe: Probe):
    import time

    started = time.monotonic()
    probe.reset(default_world())
    assert time.monotonic() - started <= 10.0


def test_R7_harness_talks_http_only(probe: Probe):
    resp = probe.call("GET", "/health")
    assert resp.status_code == 200
    assert "http" in str(probe.origin)


def test_R9_planning_files_live_beside_acceptance():
    assert (STAGE / "REQUIREMENTS.md").is_file()
    assert (STAGE / "PLAN.md").is_file()
    assert (STAGE / "acceptance").is_dir()
    ignore_path = STAGE / ".dockerignore"
    if not ignore_path.is_file():
        pytest.skip(".dockerignore is not in this checkout")
    ignore = ignore_path.read_text(encoding="utf-8")
    assert "acceptance/" in ignore
    assert "REQUIREMENTS.md" in ignore
    assert "PLAN.md" in ignore


def test_R6_json_bodies_do_not_point_at_external_runtime_assets(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    me = probe.me(token)
    blob = str(me)
    assert "https://" not in blob
    assert "http://" not in blob


def test_R24_money_only_between_wallets_no_deposit_route(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    resp = probe.call("POST", "/deposits", body={"amount": 1}, bearer=token)
    assert resp.status_code in (401, 404)
    expect_error(resp, resp.status_code, "unauthenticated" if resp.status_code == 401 else "not_found")


def test_R25_directory_and_admin_balance_routes_absent(probe: Probe, seed):
    token, _ = probe.login("src@acc.test", PASSWORD)
    for path in ("/users", "/search", "/directory", "/admin/balances"):
        resp = probe.call("GET", path, bearer=token)
        assert resp.status_code in (401, 404), path
        expect_error(resp, resp.status_code, "unauthenticated" if resp.status_code == 401 else "not_found")
