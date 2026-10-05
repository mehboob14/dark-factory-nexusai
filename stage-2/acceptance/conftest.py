from __future__ import annotations

import os

import pytest
from playwright.async_api import async_playwright

from httpapi import Probe
from world import default_world, seeded_total


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        action="store",
        default=os.environ.get("POCKETFUL_BASE_URL", "http://127.0.0.1:8080"),
        help="Origin of the service under test",
    )


@pytest.fixture(scope="session")
def origin(request) -> str:
    return request.config.getoption("--base-url").rstrip("/")


@pytest.fixture
def probe(origin) -> Probe:
    client = Probe(origin)
    yield client
    client.close()


@pytest.fixture
def world():
    return default_world()


@pytest.fixture
def seed(probe, world):
    probe.reset(world)
    return world


@pytest.fixture
def total(world) -> int:
    return seeded_total(world)


@pytest.fixture
async def page(origin):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(base_url=origin)
        page_obj = await context.new_page()
        yield page_obj
        await context.close()
        await browser.close()
