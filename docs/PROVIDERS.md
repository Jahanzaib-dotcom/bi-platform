# Discovery Provider System

## How Providers Work

The discovery engine uses a plugin-style provider architecture. Each provider is a Python class that implements `BaseDiscoveryProvider` from `app.engines.discovery.base`. The discovery engine can run multiple providers in parallel for a single job, then deduplicates results using a business fingerprinting algorithm before persisting them.

### Provider Interface

Every provider must implement:

```python
class BaseDiscoveryProvider(ABC):

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique slug, e.g. 'duckduckgo'."""

    @property
    @abstractmethod
    def rate_limit(self) -> int:
        """Maximum requests per minute."""

    @abstractmethod
    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        """Yield BusinessResult objects matching the search criteria."""

    @abstractmethod
    async def validate_config(self) -> bool:
        """Return True when required credentials are present."""

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Return a status dict: {"provider": ..., "healthy": bool, "latency_ms": int}"""
```

Results are yielded as `BusinessResult` dataclass instances:

```python
@dataclass
class BusinessResult:
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
```

### Deduplication

After all providers yield their results, the deduplication engine computes a fingerprint for each business using a combination of normalized name, domain, phone, and address. Duplicate fingerprints are collapsed, keeping the result with the most complete data.

---

## Available Providers

### DuckDuckGo (`duckduckgo`)

| Property | Value |
|---|---|
| API key required | No |
| Rate limit | 10 requests/minute |
| Source | DuckDuckGo HTML search (`https://html.duckduckgo.com/html/`) |
| Cost | Free |

Parses organic search results from DuckDuckGo's HTML endpoint. No API key or account is required. Results include the business name, website URL, and any phone numbers or addresses that appear in the snippet text.

The provider uses an internal token-bucket rate limiter and retries transient HTTP errors up to three times with exponential back-off (via `tenacity`).

**Configuration:** None required.

---

### SerpAPI (`serpapi`)

| Property | Value |
|---|---|
| API key required | Yes (`SERPAPI_KEY`) |
| Rate limit | 100 requests/minute |
| Source | SerpAPI Google Maps results endpoint |
| Cost | Paid (SerpAPI plan) |

Queries Google Maps for local businesses using SerpAPI's `search_maps` engine. Returns structured business data including name, address, phone, rating, and website URL directly from Google's local results.

This provider yields the highest-quality structured data and is recommended when budget permits.

**Configuration:**

```bash
SERPAPI_KEY=your_serpapi_key_here
```

If `SERPAPI_KEY` is not set, `validate_config()` returns `False` and the provider is skipped automatically. No error is raised; the discovery job continues using other available providers.

---

### Nominatim / OpenStreetMap (`nominatim`)

| Property | Value |
|---|---|
| API key required | No |
| Rate limit | 1 request/second (OSM policy) |
| Source | OpenStreetMap Nominatim geocoding API |
| Cost | Free (usage policy applies) |

Uses the Nominatim API to search OpenStreetMap data for businesses matching the query. Returns geolocation-rich results including structured address components.

Note: Nominatim's usage policy requires a valid `User-Agent` header and prohibits heavy automated usage without prior approval. The platform sets a descriptive User-Agent and respects the 1 request/second rate limit.

**Configuration:** None required.

---

### Generic Web Search (`web_search`)

| Property | Value |
|---|---|
| API key required | No |
| Rate limit | Configurable |
| Source | Multi-source fallback |
| Cost | Free |

A fallback provider that aggregates results from multiple free search sources when no other provider is available. Lower result quality than dedicated providers; best used as a supplement.

**Configuration:** None required.

---

## How to Add a Custom Provider

Follow these steps to integrate a new data source:

### Step 1: Create the provider module

Create a new file at:

```
backend/app/engines/discovery/providers/my_provider.py
```

### Step 2: Implement the base class

```python
"""My Custom Provider — discovers businesses from MyDataSource."""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)


class MyProvider(BaseDiscoveryProvider):

    @property
    def provider_name(self) -> str:
        return "my_provider"

    @property
    def rate_limit(self) -> int:
        return 60  # requests per minute

    async def validate_config(self) -> bool:
        # Return False if required env vars are missing
        import os
        return bool(os.environ.get("MY_PROVIDER_API_KEY"))

    async def health_check(self) -> Dict[str, Any]:
        import time
        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://api.mydatasource.com/ping", timeout=5)
            latency = int((time.monotonic() - start) * 1000)
            return {
                "provider": self.provider_name,
                "healthy": resp.status_code == 200,
                "latency_ms": latency,
                "message": "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}",
            }
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "healthy": False,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "message": str(exc),
            }

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        import os
        api_key = os.environ.get("MY_PROVIDER_API_KEY", "")

        if not api_key:
            return  # skip gracefully when not configured

        async with httpx.AsyncClient() as client:
            params = {
                "q": f"{industry or ''} {query} {city or ''} {country or ''}".strip(),
                "api_key": api_key,
                "limit": min(max_results, 100),
            }
            resp = await client.get(
                "https://api.mydatasource.com/businesses/search",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        for item in data.get("results", [])[:max_results]:
            yield BusinessResult(
                name=item.get("name", ""),
                address=item.get("address"),
                city=item.get("city") or city,
                state=item.get("state"),
                country=item.get("country") or country,
                phone=item.get("phone"),
                email=item.get("email"),
                website_url=item.get("website"),
                category=item.get("category") or industry,
                source=self.provider_name,
                source_id=str(item.get("id", "")),
                raw_data=item,
            )
```

### Step 3: Register the provider

Open `backend/app/engines/discovery/providers/__init__.py` and add the import and registration:

```python
from .my_provider import MyProvider

_REGISTRY = {
    "duckduckgo": DuckDuckGoProvider,
    "serpapi": SerpAPIProvider,
    "nominatim": NominatimProvider,
    "web_search": WebSearchProvider,
    "my_provider": MyProvider,   # <-- add this line
}
```

### Step 4: Register in the discovery endpoint

Open `backend/app/api/v1/endpoints/discovery.py` and add an entry to `_KNOWN_PROVIDERS`:

```python
{
    "name": "my_provider",
    "display_name": "My Data Source",
    "description": "Discovers businesses from MyDataSource. Requires MY_PROVIDER_API_KEY.",
    "requires_key": True,
    "env_key": "MY_PROVIDER_API_KEY",
},
```

### Step 5: Add the API key to environment configuration

Add to `config/.env.example`:

```bash
# My Custom Provider
MY_PROVIDER_API_KEY=your_key_here
```

### Step 6: Test the provider

```bash
# Using the API
curl -X POST http://localhost:8000/api/v1/discovery/providers/my_provider/test \
  -H "Authorization: Bearer <token>"
```

Or test the class directly:

```python
import asyncio
from app.engines.discovery.providers.my_provider import MyProvider

async def test():
    p = MyProvider()
    print(await p.health_check())
    async for result in p.discover("restaurant", city="Austin", max_results=3):
        print(result)

asyncio.run(test())
```

---

## Provider Configuration Summary

| Provider | Env Variable | Required | Notes |
|---|---|---|---|
| `duckduckgo` | — | None | Always available |
| `serpapi` | `SERPAPI_KEY` | Yes | Skipped if absent |
| `nominatim` | — | None | 1 req/s rate limit |
| `web_search` | — | None | Fallback only |

All providers implement graceful degradation: if `validate_config()` returns `False`, the provider is silently skipped and the discovery job continues with any remaining configured providers.
