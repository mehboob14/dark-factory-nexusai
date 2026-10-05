"""Build the stage-1 image the way RUN.md does, start it, run this suite."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
IMAGE = "pocketful-s1"


def pip_install() -> None:
    req = HERE / "requirements.txt"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
        cwd=str(HERE),
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(url: str, timeout: float = 60.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=2.0)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return
            last = f"{resp.status_code} {resp.text[:80]}"
        except Exception as exc:  # noqa: BLE001 — probe loop
            last = str(exc)
        time.sleep(0.5)
    raise SystemExit(f"health not ready at {url} within {timeout:.0f}s ({last})")


def start_container() -> tuple[str, str]:
    subprocess.check_call(["docker", "build", "-t", IMAGE, "."], cwd=str(STAGE))
    host_port = free_port()
    name = f"pocketful-s1-accept-{uuid.uuid4().hex[:10]}"
    subprocess.check_call(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-e",
            "PORT=8080",
            "-p",
            f"{host_port}:8080",
            IMAGE,
        ]
    )
    return name, f"http://127.0.0.1:{host_port}"


def stop_container(name: str) -> None:
    subprocess.run(["docker", "stop", name], check=False, capture_output=True)


def run_pytest(base_url: str) -> int:
    env = os.environ.copy()
    env["POCKETFUL_BASE_URL"] = base_url
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "pytest",
            str(HERE),
            "-q",
            "--tb=short",
            f"--base-url={base_url}",
        ],
        cwd=str(HERE),
        env=env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Pocketful stage-1 acceptance")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    if not args.skip_install:
        pip_install()
    if args.base_url:
        wait_health(args.base_url.rstrip("/"))
        return run_pytest(args.base_url.rstrip("/"))
    name = ""
    try:
        name, url = start_container()
        wait_health(url)
        return run_pytest(url)
    finally:
        if name:
            stop_container(name)


if __name__ == "__main__":
    raise SystemExit(main())
