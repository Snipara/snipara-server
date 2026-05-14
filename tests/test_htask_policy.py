"""Tests for htask policy defaults."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def htask_policy_module():
    sys.modules.pop("src.services.htask_policy", None)
    return importlib.import_module("src.services.htask_policy")


class FakeHTaskPolicyTable:
    def __init__(self):
        self.created_with: dict | None = None

    async def find_unique(self, **kwargs):
        return None

    async def create(self, **kwargs):
        self.created_with = kwargs
        data = kwargs["data"]
        return SimpleNamespace(
            id="policy-1",
            swarmId=data["swarmId"],
            maxDepth=4,
            closurePolicy="STRICT_ALL_CHILDREN",
            requireEvidenceOnComplete=True,
            allowParentCloseWithWaiver=True,
            failedIsBlockingDefault=True,
            allowStructuralUpdate=False,
            allowHardDelete=False,
            compatMode=data["compatMode"],
            createdAt=None,
            updatedAt=None,
        )


@pytest.mark.asyncio
async def test_get_policy_creates_htask_default(monkeypatch, htask_policy_module):
    table = FakeHTaskPolicyTable()
    db = SimpleNamespace(htaskpolicy=table)

    async def fake_get_db():
        return db

    monkeypatch.setattr(htask_policy_module, "get_db", fake_get_db)

    policy = await htask_policy_module.get_policy("swarm-1")

    assert policy["compat_mode"] == "HTASK"
    assert table.created_with == {"data": {"swarmId": "swarm-1", "compatMode": "HTASK"}}


def test_get_compat_mode_fallback_is_htask(htask_policy_module):
    assert htask_policy_module.get_compat_mode({}) == "HTASK"
