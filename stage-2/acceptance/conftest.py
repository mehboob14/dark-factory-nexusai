from __future__ import annotations

import os

import pytest

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


@pytest.fixture(scope="session")
async def browser():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        yield browser
        await browser.close()


@pytest.fixture
def probe(origin) -> Probe:
    client = Probe(origin)
    yield client
    client.close()


@pytest.fixture
async def page(browser, origin):
    context = await browser.new_context()
    page = await context.new_page()
    page.base_url = origin
    yield page
    await context.close()


@pytest.fixture
def world():
    return default_world()


@pytest.fixture
def seed(probe, world):
    probe.reset(world)
    return world
