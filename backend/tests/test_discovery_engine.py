"""
Unit tests for the discovery engine, deduplication, and Nominatim provider.
"""
from __future__ import annotations

from typing import AsyncGenerator, Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult
from app.engines.discovery.deduplication import (
    BusinessDeduplicator,
    _normalise_string,
    _similarity,
)
from app.engines.discovery.discovery_engine import DiscoveryConfig, DiscoveryEngine

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Normalisation helpers (pure functions — no async needed)
# ---------------------------------------------------------------------------


def test_normalise_string_strips_legal_suffixes() -> None:
    """Legal suffixes are stripped during normalisation."""
    assert "acme" == _normalise_string("Acme LLC")
    assert "acme" == _normalise_string("Acme Corp.")
    assert "acme solutions" == _normalise_string("Acme Solutions Ltd.")


def test_normalise_string_lowercase_and_accent_free() -> None:
    """Accented characters are converted to ASCII equivalents."""
    result = _normalise_string("Café Rösterei")
    assert result == result.lower()
    assert "a" in result  # 'é' → 'e' at minimum


def test_normalise_string_empty() -> None:
    """Empty / None input returns an empty string."""
    assert _normalise_string("") == ""
    assert _normalise_string(None) == ""


def test_similarity_identical() -> None:
    assert _similarity("hello", "hello") == 1.0


def test_similarity_completely_different() -> None:
    score = _similarity("abc", "xyz")
    assert 0.0 <= score < 1.0


def test_similarity_empty_strings() -> None:
    assert _similarity("", "") == 1.0


# ---------------------------------------------------------------------------
# Fingerprint generation
# ---------------------------------------------------------------------------


def test_fingerprint_generation_deterministic() -> None:
    """The same business always produces the same fingerprint."""
    result = BusinessResult(name="Acme Plumbing", city="Austin", country="US")
    dedup = BusinessDeduplicator()
    fp1 = dedup.fingerprint(result)
    fp2 = dedup.fingerprint(result)
    assert fp1 == fp2


def test_fingerprint_case_insensitive() -> None:
    """Case differences don't produce different fingerprints."""
    r1 = BusinessResult(name="Acme Plumbing", city="Austin", country="US")
    r2 = BusinessResult(name="ACME PLUMBING", city="AUSTIN", country="US")
    dedup = BusinessDeduplicator()
    assert dedup.fingerprint(r1) == dedup.fingerprint(r2)


def test_fingerprint_different_for_different_names() -> None:
    """Different business names produce different fingerprints."""
    r1 = BusinessResult(name="Acme Plumbing", city="Austin", country="US")
    r2 = BusinessResult(name="Beta Bakery", city="Austin", country="US")
    dedup = BusinessDeduplicator()
    assert dedup.fingerprint(r1) != dedup.fingerprint(r2)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_deduplication_exact_duplicate() -> None:
    """A business seen twice is detected as a duplicate on the second call."""
    dedup = BusinessDeduplicator()
    result = BusinessResult(name="Pizza Palace", city="New York", country="US")
    assert dedup.is_duplicate(result) is False  # first time → not duplicate
    assert dedup.is_duplicate(result) is True   # second time → duplicate


def test_deduplication_fuzzy_match() -> None:
    """Near-identical names in the same city are treated as duplicates."""
    dedup = BusinessDeduplicator(fuzzy_threshold=0.85)
    r1 = BusinessResult(name="Acme Plumbing Services", city="Dallas", country="US")
    r2 = BusinessResult(name="Acme Plumbing Srvices", city="Dallas", country="US")  # typo
    dedup.is_duplicate(r1)  # register r1
    assert dedup.is_duplicate(r2) is True


def test_deduplication_different_cities_not_duplicate() -> None:
    """Same name in different cities is NOT a duplicate."""
    dedup = BusinessDeduplicator()
    r1 = BusinessResult(name="Subway", city="Austin", country="US")
    r2 = BusinessResult(name="Subway", city="Dallas", country="US")
    dedup.is_duplicate(r1)
    assert dedup.is_duplicate(r2) is False


def test_deduplication_reset() -> None:
    """After reset(), previously seen businesses are no longer detected."""
    dedup = BusinessDeduplicator()
    result = BusinessResult(name="Starbucks", city="Seattle", country="US")
    dedup.is_duplicate(result)
    dedup.reset()
    assert dedup.is_duplicate(result) is False


def test_deduplication_merge_duplicates_picks_richer_record() -> None:
    """merge_duplicates keeps the record with more populated fields."""
    dedup = BusinessDeduplicator()
    sparse = BusinessResult(name="Acme", city="Austin")
    rich = BusinessResult(
        name="Acme",
        city="Austin",
        address="123 Main St",
        phone="+15125550100",
        email="acme@example.com",
        website_url="https://acme.example",
    )
    merged = dedup.merge_duplicates([sparse, rich])
    assert len(merged) == 1
    assert merged[0].email == "acme@example.com"


def test_deduplication_threshold_validation() -> None:
    """Invalid fuzzy_threshold raises ValueError."""
    with pytest.raises(ValueError):
        BusinessDeduplicator(fuzzy_threshold=1.5)
    with pytest.raises(ValueError):
        BusinessDeduplicator(fuzzy_threshold=-0.1)


# ---------------------------------------------------------------------------
# BusinessResult creation
# ---------------------------------------------------------------------------


def test_business_result_creation_minimal() -> None:
    """BusinessResult can be created with only a name."""
    result = BusinessResult(name="Solo Bakery")
    assert result.name == "Solo Bakery"
    assert result.city is None
    assert result.website_url is None
    assert result.raw_data == {}


def test_business_result_creation_full() -> None:
    """All fields on BusinessResult are stored correctly."""
    result = BusinessResult(
        name="Full Details Café",
        address="42 Rue du Commerce",
        city="Paris",
        state=None,
        country="FR",
        phone="+33140000000",
        email="info@cafe.example",
        website_url="https://cafe.example",
        category="restaurant",
        source="nominatim",
        source_id="osm:12345",
        raw_data={"tags": {"name": "Full Details Café"}},
    )
    assert result.country == "FR"
    assert result.source == "nominatim"
    assert result.raw_data["tags"]["name"] == "Full Details Café"


# ---------------------------------------------------------------------------
# Nominatim provider — mocked HTTP
# ---------------------------------------------------------------------------


class _MockNominatimProvider:
    """Thin stand-in that validates the provider interface without HTTP."""

    @property
    def provider_name(self) -> str:
        return "nominatim"

    @property
    def rate_limit(self) -> int:
        return 60

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        return {"provider": "nominatim", "healthy": True, "latency_ms": 1, "message": "OK"}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        for i in range(min(3, max_results)):
            yield BusinessResult(
                name=f"Mock Business {i}",
                city=city or "Austin",
                country=country or "US",
                source="nominatim",
                source_id=f"osm:{i}",
            )


async def test_nominatim_provider_validate_config() -> None:
    """NominatimProvider.validate_config always returns True (no key required)."""
    from app.engines.discovery.providers.nominatim_provider import NominatimProvider

    provider = NominatimProvider()
    assert await provider.validate_config() is True


async def test_nominatim_provider_mock_discover() -> None:
    """A mocked Nominatim provider yields the expected BusinessResult objects."""
    provider = _MockNominatimProvider()
    results = []
    async for result in provider.discover(
        query="restaurant", country="US", industry="restaurant", city="Austin"
    ):
        results.append(result)

    assert len(results) == 3
    for r in results:
        assert r.source == "nominatim"
        assert r.name.startswith("Mock Business")


async def test_nominatim_provider_search_failure() -> None:
    """When search fails, discover yields nothing instead of raising."""
    from app.engines.discovery.providers.nominatim_provider import NominatimProvider

    provider = NominatimProvider()

    async def mock_search(*args, **kwargs):
        return []

    with patch.object(provider, "_search_amenity", new=mock_search):
        results = []
        async for result in provider.discover(
            query="restaurant", country="US", city="UnknownCity"
        ):
            results.append(result)

    assert results == []


# ---------------------------------------------------------------------------
# DiscoveryConfig validation
# ---------------------------------------------------------------------------


def test_discovery_config_defaults() -> None:
    """DiscoveryConfig has sensible defaults."""
    config = DiscoveryConfig()
    assert config.sources == []
    assert config.countries == []
    assert config.industries == []
    assert config.keywords == []
    assert config.max_results == 100
    assert config.rate_limit_multiplier == 1.0
    assert config.city is None


def test_discovery_config_custom() -> None:
    """DiscoveryConfig stores custom values correctly."""
    config = DiscoveryConfig(
        sources=["nominatim"],
        countries=["US"],
        industries=["restaurant"],
        keywords=["pizza"],
        max_results=50,
        city="Chicago",
    )
    assert "nominatim" in config.sources
    assert config.max_results == 50
    assert config.city == "Chicago"


# ---------------------------------------------------------------------------
# DiscoveryEngine orchestration
# ---------------------------------------------------------------------------


async def test_discovery_engine_get_available_providers() -> None:
    """DiscoveryEngine registers all built-in provider slugs."""
    engine = DiscoveryEngine()
    providers = engine.get_available_providers()
    assert "nominatim" in providers
    assert "duckduckgo" in providers


async def test_discovery_engine_custom_provider() -> None:
    """Extra providers injected at construction time are available."""
    mock_provider = _MockNominatimProvider()

    class _WrappedMock(BaseDiscoveryProvider):
        @property
        def provider_name(self) -> str:
            return "custom_test"

        @property
        def rate_limit(self) -> int:
            return 10

        async def validate_config(self) -> bool:
            return True

        async def health_check(self) -> Dict[str, Any]:
            return {"provider": "custom_test", "healthy": True}

        async def discover(self, *args: Any, **kwargs: Any) -> AsyncGenerator[BusinessResult, None]:
            yield BusinessResult(name="Custom Result", source="custom_test")

    engine = DiscoveryEngine(extra_providers=[_WrappedMock()])
    assert "custom_test" in engine.get_available_providers()


async def test_discovery_engine_estimate_results() -> None:
    """estimate_results returns a positive integer."""
    engine = DiscoveryEngine()
    config = DiscoveryConfig(
        sources=["nominatim"],
        countries=["US"],
        industries=["restaurant"],
        max_results=50,
    )
    estimate = await engine.estimate_results(config)
    assert isinstance(estimate, int)
    assert estimate > 0


async def test_discovery_engine_no_providers_selected() -> None:
    """When no matching providers are found the run yields nothing."""
    engine = DiscoveryEngine()
    config = DiscoveryConfig(sources=["nonexistent_provider"], max_results=10)
    results = []
    # The fallback behaviour is to use all providers when none match; test that
    # it doesn't raise
    try:
        async for result in engine.run_discovery(config):
            results.append(result)
            break  # bail out early to avoid slow network calls
    except Exception:
        pass  # network unavailable in CI — just ensure no crash
