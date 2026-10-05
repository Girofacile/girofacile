from app.services.api_usage import (
    API_COST_DEFAULTS,
    _cost_for_profile,
    _deep_merge_profile,
    _tiered_cost,
)


def test_google_geocoding_free_tier_then_standard_cost():
    profile = API_COST_DEFAULTS["google_geocoding"]
    assert _tiered_cost(10_000, profile) == 0
    assert _tiered_cost(10_001, profile) == 0.005
    assert _tiered_cost(15_000, profile) == 25.0


def test_mapbox_directions_uses_progressive_public_tiers():
    profile = API_COST_DEFAULTS["mapbox_traffic"]
    assert _tiered_cost(100_000, profile) == 0
    assert _tiered_cost(100_001, profile) == 0.002
    # 400k at $2/1k + 100k at $1.60/1k.
    assert _tiered_cost(600_000, profile) == 960.0


def test_subscription_provider_does_not_invent_payg_cost():
    profile = API_COST_DEFAULTS["mycarplate"]
    assert _cost_for_profile(100, profile, 0) is None


def test_openai_uses_logged_token_cost():
    profile = API_COST_DEFAULTS["openai"]
    assert _cost_for_profile(12, profile, 0.1234567) == 0.123457


def test_profile_override_keeps_non_editable_metadata():
    default = API_COST_DEFAULTS["google_geocoding"]
    merged = _deep_merge_profile(default, {
        "free_quota": 20_000,
        "currency": "USD",
        "tiers": [{"up_to": None, "price_per_1000": 4.5}],
    })
    assert merged["label"] == "Google Geocoding"
    assert merged["services"] == ["google_geocoding"]
    assert merged["free_quota"] == 20_000
    assert merged["tiers"][0]["price_per_1000"] == 4.5
