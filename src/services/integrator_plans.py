"""Integrator tier and client bundle plan definitions."""

from typing import Any

CLIENT_BUNDLES = ("LITE", "STANDARD", "UNLIMITED")

CLIENT_BUNDLE_LIMITS: dict[str, dict[str, int]] = {
    "LITE": {
        "queries_per_month": 500,
        "memories": 100,
        "swarms": 1,
        "agents_per_swarm": 5,
        "documents": 50,
        "storage_mb": 100,
    },
    "STANDARD": {
        "queries_per_month": 5000,
        "memories": 500,
        "swarms": 5,
        "agents_per_swarm": 10,
        "documents": 200,
        "storage_mb": 1024,
    },
    "UNLIMITED": {
        "queries_per_month": -1,
        "memories": -1,
        "swarms": -1,
        "agents_per_swarm": 20,
        "documents": -1,
        "storage_mb": 10240,
    },
}

CLIENT_BUNDLE_PRICES_CENTS = {
    "LITE": 1900,
    "STANDARD": 4900,
    "UNLIMITED": 9900,
}

INTEGRATOR_CLIENT_LIMITS = {
    "STARTER": 100,
    "GROWTH": 500,
    "SCALE": 2000,
    "ENTERPRISE": -1,
}

INTEGRATOR_CLIENT_BUNDLE_DISCOUNTS = {
    "STARTER": 20,
    "GROWTH": 25,
    "SCALE": 30,
}

INTEGRATOR_CLIENT_BUNDLE_DISCOUNT_RANGES = {
    "ENTERPRISE": {"min": 30, "max": 50},
}


def normalize_client_bundle(bundle: Any) -> str:
    """Return a known client bundle, defaulting to LITE."""
    return bundle if bundle in CLIENT_BUNDLES else "LITE"


def normalize_integrator_tier(tier: Any) -> str:
    """Return a known integrator tier, defaulting to STARTER."""
    return tier if tier in INTEGRATOR_CLIENT_LIMITS else "STARTER"


def get_integrator_client_limit(tier: Any) -> int:
    """Return max clients for an integrator tier. -1 means unlimited."""
    return INTEGRATOR_CLIENT_LIMITS[normalize_integrator_tier(tier)]


def get_client_bundle_limits(bundle: Any) -> dict[str, int]:
    """Return resource limits for a client bundle."""
    return CLIENT_BUNDLE_LIMITS[normalize_client_bundle(bundle)]


def get_client_bundle_discount_percent(tier: Any) -> int | None:
    """Return fixed client-bundle discount. Enterprise is custom-range priced."""
    normalized_tier = normalize_integrator_tier(tier)
    return INTEGRATOR_CLIENT_BUNDLE_DISCOUNTS.get(normalized_tier)


def get_client_bundle_discount_range_percent(tier: Any) -> dict[str, int] | None:
    """Return negotiated discount range for custom tiers."""
    return INTEGRATOR_CLIENT_BUNDLE_DISCOUNT_RANGES.get(normalize_integrator_tier(tier))


def get_client_bundle_pricing(bundle: Any, tier: Any) -> dict[str, Any]:
    """Return monthly pricing for a client bundle under an integrator tier."""
    normalized_bundle = normalize_client_bundle(bundle)
    list_monthly_cents = CLIENT_BUNDLE_PRICES_CENTS[normalized_bundle]
    discount_percent = get_client_bundle_discount_percent(tier)
    discounted_monthly_cents = (
        None
        if discount_percent is None
        else round(list_monthly_cents * (100 - discount_percent) / 100)
    )

    return {
        "currency": "USD",
        "interval": "month",
        "list_monthly_cents": list_monthly_cents,
        "discount_percent": discount_percent,
        "discount_range_percent": get_client_bundle_discount_range_percent(tier),
        "discounted_monthly_cents": discounted_monthly_cents,
        "monthly_savings_cents": (
            None
            if discounted_monthly_cents is None
            else list_monthly_cents - discounted_monthly_cents
        ),
        "discount_applies_to": "client_bundles",
    }


def summarize_client_bundle_billing(tier: Any, clients: list[Any]) -> dict[str, Any]:
    """Summarize active-client bundle billing under an integrator tier."""
    bundle_counts = {"LITE": 0, "STANDARD": 0, "UNLIMITED": 0}
    active_clients = [
        client for client in clients if getattr(client, "isActive", True) is not False
    ]

    for client in active_clients:
        bundle_counts[normalize_client_bundle(getattr(client, "bundle", "LITE"))] += 1

    list_monthly_cents = sum(
        bundle_counts[bundle] * CLIENT_BUNDLE_PRICES_CENTS[bundle] for bundle in CLIENT_BUNDLES
    )
    discount_percent = get_client_bundle_discount_percent(tier)
    discounted_monthly_cents = (
        None
        if discount_percent is None
        else round(list_monthly_cents * (100 - discount_percent) / 100)
    )

    return {
        "currency": "USD",
        "interval": "month",
        "discount_percent": discount_percent,
        "discount_range_percent": get_client_bundle_discount_range_percent(tier),
        "active_client_count": len(active_clients),
        "bundle_counts": bundle_counts,
        "list_monthly_cents": list_monthly_cents,
        "discounted_monthly_cents": discounted_monthly_cents,
        "monthly_savings_cents": (
            None
            if discounted_monthly_cents is None
            else list_monthly_cents - discounted_monthly_cents
        ),
        "discount_applies_to": "client_bundles",
    }
