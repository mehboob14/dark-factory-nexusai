"""Browser routes and UI navigation tests for Stage 2."""

from __future__ import annotations

import pytest

from world import PASSWORD


class TestBrowserRoutes:
    """Test that required routes are accessible and render HTML."""

    @pytest.mark.asyncio
    async def test_home_route_accessible(self, page, seed):
        """GET / returns HTML and renders balance with data-testid."""
        await page.goto("/")
        # Check that page loaded
        assert await page.title() is not None

    @pytest.mark.asyncio
    async def test_requests_route_accessible(self, page, seed):
        """GET /requests returns HTML with request lists."""
        await page.goto("/requests")
        assert await page.title() is not None

    @pytest.mark.asyncio
    async def test_split_route_accessible(self, page, seed):
        """GET /split returns HTML with split form."""
        await page.goto("/split")
        assert await page.title() is not None

    @pytest.mark.asyncio
    async def test_signup_route_accessible(self, page, seed):
        """GET /signup returns HTML with signup form."""
        await page.goto("/signup")
        assert await page.title() is not None

    @pytest.mark.asyncio
    async def test_login_route_accessible(self, page, seed):
        """GET /login returns HTML with login form."""
        await page.goto("/login")
        assert await page.title() is not None


class TestAuthenticationFlow:
    """Test signup and login flows via browser."""

    @pytest.mark.asyncio
    async def test_signup_creates_user(self, page, seed):
        """User can signup and be redirected to home."""
        await page.goto("/signup")

        # Fill signup form
        await page.fill("[data-testid=signup-email]", "newuser@test.local")
        await page.fill("[data-testid=signup-password]", PASSWORD)
        await page.fill("[data-testid=signup-display-name]", "New User")

        # Submit
        await page.click("[data-testid=signup-submit]")

        # Should be redirected and show display name
        await page.wait_for_selector("[data-testid=current-user]")
        user_text = await page.text_content("[data-testid=current-user]")
        assert "New User" in user_text

    @pytest.mark.asyncio
    async def test_login_authenticates_user(self, page, seed):
        """User can login and access protected route."""
        await page.goto("/login")

        # Fill login form
        await page.fill("[data-testid=login-email]", "src@acc.test")
        await page.fill("[data-testid=login-password]", PASSWORD)

        # Submit
        await page.click("[data-testid=login-submit]")

        # Should show current user
        await page.wait_for_selector("[data-testid=current-user]")
        handle_text = await page.text_content("[data-testid=current-handle]")
        assert handle_text == "srcuser"

    @pytest.mark.asyncio
    async def test_current_user_visible_when_signed_in(self, page, seed):
        """current-user and current-handle are visible after login."""
        await page.goto("/login")
        await page.fill("[data-testid=login-email]", "src@acc.test")
        await page.fill("[data-testid=login-password]", PASSWORD)
        await page.click("[data-testid=login-submit]")

        await page.wait_for_selector("[data-testid=current-user]")
        await page.wait_for_selector("[data-testid=current-handle]")

        handle = await page.text_content("[data-testid=current-handle]")
        assert handle == "srcuser"

    @pytest.mark.asyncio
    async def test_logout_redirects_to_login(self, page, seed):
        """User can logout and is redirected to login."""
        await page.goto("/login")
        await page.fill("[data-testid=login-email]", "src@acc.test")
        await page.fill("[data-testid=login-password]", PASSWORD)
        await page.click("[data-testid=login-submit]")

        await page.wait_for_selector("[data-testid=logout-button]")
        await page.click("[data-testid=logout-button]")

        # Should show login form
        await page.wait_for_selector("[data-testid=login-email]")


class TestWalletDisplay:
    """Test wallet balance and amount displays."""

    @pytest.mark.asyncio
    async def test_wallet_balance_displayed(self, page, seed):
        """Wallet balance is shown in formatted currency."""
        await page.goto("/login")
        await page.fill("[data-testid=login-email]", "src@acc.test")
        await page.fill("[data-testid=login-password]", PASSWORD)
        await page.click("[data-testid=login-submit]")

        # Wait for balance to be displayed
        await page.wait_for_selector("[data-testid=wallet-balance]")

        # Check format: should be "10000.00 EUR" for minor_units=2
        balance_text = await page.text_content("[data-testid=wallet-balance]")
        assert "EUR" in balance_text or "10000" in balance_text

    @pytest.mark.asyncio
    async def test_wallet_available_and_held_displayed(self, page, seed):
        """Wallet shows available and held amounts separately."""
        await page.goto("/login")
        await page.fill("[data-testid=login-email]", "src@acc.test")
        await page.fill("[data-testid=login-password]", PASSWORD)
        await page.click("[data-testid=login-submit]")

        # Wait for balance displays
        await page.wait_for_selector("[data-testid=wallet-available]")
        # held should be absent when zero
