"""Tests for failed-auth throttling on MCP/API auth surfaces."""

import pytest


@pytest.mark.asyncio
async def test_auth_failure_rate_limit_blocks_after_threshold(monkeypatch):
    from src import usage

    usage._local_auth_failure_limits.clear()

    async def no_redis():
        return None

    monkeypatch.setattr(usage, "get_redis", no_redis)
    monkeypatch.setattr(usage.settings, "auth_failure_rate_limit_requests", 2)
    monkeypatch.setattr(usage.settings, "auth_failure_rate_limit_window", 300)

    assert await usage.check_auth_failure_rate_limit("203.0.113.1", "rlm_invalid") is True
    assert await usage.check_auth_failure_rate_limit("203.0.113.1", "rlm_invalid") is True
    assert await usage.check_auth_failure_rate_limit("203.0.113.1", "rlm_invalid") is False


@pytest.mark.asyncio
async def test_auth_failure_rate_limit_is_scoped_by_ip(monkeypatch):
    from src import usage

    usage._local_auth_failure_limits.clear()

    async def no_redis():
        return None

    monkeypatch.setattr(usage, "get_redis", no_redis)
    monkeypatch.setattr(usage.settings, "auth_failure_rate_limit_requests", 1)
    monkeypatch.setattr(usage.settings, "auth_failure_rate_limit_window", 300)

    assert await usage.check_auth_failure_rate_limit("203.0.113.1", "rlm_invalid") is True
    assert await usage.check_auth_failure_rate_limit("203.0.113.1", "rlm_invalid") is False
    assert await usage.check_auth_failure_rate_limit("203.0.113.2", "rlm_invalid") is True


def test_plan_ip_rate_limit_only_applies_to_free():
    from src import usage

    assert usage.should_apply_plan_ip_rate_limit("FREE") is True
    assert usage.should_apply_plan_ip_rate_limit("PRO") is False
    assert usage.should_apply_plan_ip_rate_limit("TEAM") is False
    assert usage.should_apply_plan_ip_rate_limit("ENTERPRISE") is False
    assert usage.should_apply_plan_ip_rate_limit("PARTNER") is False
    assert usage.should_apply_plan_ip_rate_limit(None) is False


@pytest.mark.asyncio
async def test_paid_plans_bypass_plan_ip_rate_limit(monkeypatch):
    from src import usage

    called = False

    async def fake_ip_rate_limit(client_ip):
        nonlocal called
        called = True
        return False

    monkeypatch.setattr(usage, "check_ip_rate_limit", fake_ip_rate_limit)

    assert await usage.check_plan_ip_rate_limit("203.0.113.1", "ENTERPRISE") is True
    assert await usage.check_plan_ip_rate_limit("203.0.113.1", "PARTNER") is True
    assert called is False


@pytest.mark.asyncio
async def test_free_plan_uses_plan_ip_rate_limit(monkeypatch):
    from src import usage

    calls = []

    async def fake_ip_rate_limit(client_ip):
        calls.append(client_ip)
        return False

    monkeypatch.setattr(usage, "check_ip_rate_limit", fake_ip_rate_limit)

    assert await usage.check_plan_ip_rate_limit("203.0.113.1", "FREE") is False
    assert calls == ["203.0.113.1"]
