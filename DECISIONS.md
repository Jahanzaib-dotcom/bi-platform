# Architecture Decision Log

This document records the significant technical choices made during the design and build of BI Platform, along with the reasoning and alternatives considered.

---

## ADR-001: FastAPI over Django

**Decision:** Use FastAPI as the backend web framework.

**Context:** The platform requires a high-throughput API that handles concurrent discovery jobs, audit tasks, and real-time WebSocket connections. The backend is I/O-bound (network requests to discovery providers, database queries, Playwright browser sessions).

**Rationale:**

- **Native async/await** — FastAPI is built on Starlette and runs natively on ASGI with `asyncio`. Django's async support is bolted on and incomplete in many areas (the ORM being the primary example). Every database query, HTTP request to discovery providers, and Playwright call in this codebase is async; a sync-first framework would force thread-pool workarounds everywhere.
- **WebSocket support** — Starlette's WebSocket primitive is clean and first-class. Django Channels requires a separate ASGI layer and significant additional configuration.
- **Automatic documentation** — FastAPI generates OpenAPI 3 specs from type annotations with zero extra configuration. Having live Swagger UI at `/docs` was a requirement from day one.
- **Pydantic integration** — FastAPI uses Pydantic for request/response validation. The same Pydantic models also serve as the schema layer, eliminating duplication between serializers and validators that is common in Django REST Framework.
- **Performance** — FastAPI consistently benchmarks 2–10x faster than Django REST Framework on I/O-bound workloads due to async execution.

**Alternatives considered:**

- **Django + DRF** — Mature ecosystem and ORM, but sync-first. Async Django ORM is still incomplete and not production-recommended for all query types.
- **Litestar** — Similar design to FastAPI; slightly more opinionated. FastAPI has a larger community and more third-party integrations.
- **Flask** — Too low-level; would require assembling many libraries (marshmallow, flask-sqlalchemy, etc.) to reach feature parity.

---

## ADR-002: Next.js App Router

**Decision:** Use Next.js 14 with the App Router instead of the Pages Router.

**Context:** The frontend is a data-heavy dashboard requiring server-side rendering for initial page loads, client-side interactivity for real-time updates, and efficient data fetching patterns.

**Rationale:**

- **Server Components** — The App Router's React Server Components allow initial data fetching to happen on the server, reducing the JavaScript payload and improving time-to-first-contentful-paint for the dashboard.
- **Nested layouts** — The `layout.tsx` hierarchy maps cleanly to the dashboard's structure (auth shell vs. dashboard shell with sidebar).
- **Colocated loading/error states** — `loading.tsx` and `error.tsx` files provide automatic suspense boundaries and error boundaries without manual wrapping.
- **Built-in code splitting** — Each page is automatically code-split; the heavy Recharts and Framer Motion libraries are only loaded when their pages are visited.
- **Forward compatibility** — The App Router is Next.js's primary development focus. New features (partial prerendering, server actions) will only be available in App Router.

**Alternatives considered:**

- **Next.js Pages Router** — Stable and well-understood, but lacks Server Components and the improved layouts model. Migrating later would be significant work.
- **Remix** — Strong data loading primitives (loaders/actions), but smaller ecosystem and less mature than Next.js for complex dashboard UIs.
- **Vite + React SPA** — Simpler mental model, but no SSR means the dashboard would show loading spinners on every page load. Worse SEO (relevant if any pages are public-facing in the future).

---

## ADR-003: PostgreSQL with SQLite Fallback

**Decision:** Use PostgreSQL as the primary database, with an SQLite fallback for local development and testing.

**Context:** The platform stores millions of business records, audit reports, and discovery results. Queries filter, sort, and aggregate across large datasets.

**Rationale for PostgreSQL:**

- **JSONB columns** — Audit results, AI analysis output, tech stack detections, and discovery raw data are stored in JSONB columns. PostgreSQL's JSONB type supports indexing and querying inside JSON objects efficiently. SQLite's JSON support is limited.
- **Full-text search** — PostgreSQL's `tsvector`/`tsquery` and GIN indexes support efficient full-text search on business names and categories without an additional search service.
- **Concurrent writes** — PostgreSQL's MVCC handles many concurrent Celery workers writing discovery and audit results simultaneously without row-level locking issues.
- **Advanced aggregations** — The analytics endpoints use window functions, `FILTER` clauses, and `date_trunc` — all standard PostgreSQL features that SQLite does not fully support.
- **Production reliability** — PostgreSQL has decades of production hardening, point-in-time recovery, logical replication, and a rich operational tooling ecosystem.

**Rationale for SQLite fallback:**

- New contributors can run the backend locally without installing PostgreSQL. SQLite is zero-config.
- The SQLAlchemy ORM abstracts most dialect differences, so tests and simple dev workflows work identically.
- The `aiosqlite` driver provides async support matching the async PostgreSQL driver interface.

**Alternatives considered:**

- **MySQL / MariaDB** — Weaker JSON support and less capable full-text search than PostgreSQL.
- **MongoDB** — Document-native storage for JSON audit data, but lacks transactional integrity for cross-model operations (e.g., creating a Business and linking it to a DiscoveryResult atomically). Adds operational complexity without clear benefit given PostgreSQL's JSONB.
- **CockroachDB** — PostgreSQL-compatible distributed SQL, useful for multi-region deployments. Overkill for the initial release; can be adopted later with minimal schema changes.

---

## ADR-004: Celery + Redis for Async Jobs

**Decision:** Use Celery with Redis as both the broker and result backend for all async processing.

**Context:** Discovery jobs (scraping hundreds of search results), website audits (launching Playwright browsers), screenshot captures, and export generation are all long-running operations that cannot block HTTP request handlers.

**Rationale:**

- **Task isolation** — CPU- and memory-intensive Playwright sessions run in Celery worker processes, completely isolated from the FastAPI API process. A crashing browser session does not affect API availability.
- **Horizontal scaling** — Celery workers can be scaled independently of the API. Adding two more Celery worker containers doubles audit throughput without touching the API layer.
- **Priority queues** — Separate queues (`default`, `reports`, `scraping`, `audit-queue`, `discovery-queue`, `export-queue`) allow prioritising interactive audit requests over background bulk discovery jobs.
- **Task retry** — Celery's `max_retries` and `countdown` parameters handle transient failures (network timeouts, rate limit hits) without custom retry logic in every worker.
- **Redis pub/sub** — Redis is already the Celery broker; using its pub/sub feature for WebSocket event broadcasting adds zero infrastructure complexity. Workers publish progress events to `bi:ws:*` channels; the WebSocket handler subscribes and forwards them to connected clients.
- **Mature ecosystem** — Celery has been the Python async task standard for over 15 years. Extensive documentation, monitoring tooling (Flower), and operational playbooks exist.

**Alternatives considered:**

- **FastAPI BackgroundTasks** — Lightweight, no extra infrastructure, but tasks run in the same process as the API and die if the process restarts. Not suitable for long-running jobs.
- **RQ (Redis Queue)** — Simpler than Celery but lacks priority queues, scheduled tasks (beat), and the mature retry/routing system. Would likely need to be replaced as the platform scales.
- **ARQ** — Async-native Redis job queue. Promising, but much smaller community than Celery. Fewer production battle-test reports for heavy workloads.
- **RabbitMQ as broker** — More reliable message delivery semantics than Redis, but adds operational complexity. Redis's durability (AOF) is sufficient for the job queue use case; losing a few queued tasks on Redis restart is acceptable given Celery's retry mechanism.

---

## ADR-005: Provider Plugin Architecture

**Decision:** Implement discovery providers as interchangeable plugin classes adhering to a shared abstract interface, rather than hard-coding discovery logic.

**Context:** Business data is scattered across many sources (search engines, map services, directories). No single source has complete coverage. New sources should be addable without modifying the core discovery engine.

**Rationale:**

- **Extensibility without modification** — Adding a new data source requires only creating a new class implementing `BaseDiscoveryProvider` and registering it. The discovery engine, API endpoints, and job workers require no changes.
- **Graceful degradation** — Each provider implements `validate_config()`. If credentials are missing or the service is unavailable, the provider returns `False` and is silently skipped. Discovery jobs continue with remaining providers.
- **Independent rate limiting** — Each provider manages its own rate limiter instance. The DuckDuckGo provider allows 10 RPM; SerpAPI allows 100 RPM. These limits can be tuned per-provider without global configuration.
- **Testability** — Providers are standalone classes with no global state. Unit tests can instantiate a provider, mock the HTTP client, and verify yielded `BusinessResult` objects in isolation.
- **Parallel execution** — The `DiscoveryEngine` fan-outs requests to all configured providers concurrently using `asyncio.gather`. The plugin interface makes it trivial to add providers to the parallel execution pool.

**Alternatives considered:**

- **Single monolithic scraper** — All source-specific logic in one file. Simple initially but becomes unmaintainable as sources multiply and each has distinct pagination, authentication, and parsing logic.
- **Strategy pattern with configuration** — Similar to the current design but with configuration-driven provider selection rather than code-based. The current approach is simpler and more type-safe.

---

## ADR-006: Claude API for AI Analysis

**Decision:** Use Anthropic's Claude API for the AI-powered website analysis component of the audit engine.

**Context:** The audit engine collects structured data (scores, tech stack, SEO issues, accessibility violations) and raw HTML/screenshots. The final AI step synthesises this into actionable narrative recommendations.

**Rationale:**

- **Long context window** — Claude's large context window accommodates full audit data (scores, issues lists, scraped text, tech stack) in a single prompt without chunking.
- **Instruction following** — Claude reliably follows detailed structured output instructions, producing consistent JSON-formatted recommendations that the frontend can render directly.
- **Content safety** — Anthropic's Constitutional AI training means Claude is less likely to generate inappropriate analysis content or hallucinate dangerous security advice.
- **Developer experience** — The `anthropic` Python SDK integrates cleanly with async Python. Streaming responses can be forwarded to the WebSocket for real-time typing effects in the frontend.
- **Existing relationship** — The project is built using Claude Code. Using the same provider for the AI analysis feature simplifies vendor management and API key handling.

**Configuration:** The model is configurable via the `AI_MODEL` environment variable (default: `claude-opus-4-8`). Switching to a faster/cheaper model (e.g., Haiku for bulk audits) requires only an env var change.

**Alternatives considered:**

- **OpenAI GPT-4** — Comparable capability, but Anthropic's Constitutional AI approach provides stronger guardrails for business advice generation. GPT-4 can be enabled by replacing the `AiAnalyzer` class without changing the rest of the system.
- **Open-source models (Llama 3, Mistral)** — Could run on self-hosted GPU infrastructure for cost control. However, deployment complexity (GPU provisioning, model serving) is high, and output quality for structured analysis tasks is lower than frontier models at the current state of the art.
- **Google Gemini** — Comparable to Claude; a viable alternative. No strong differentiation for this use case; Claude was chosen based on integration familiarity.
- **No AI** — The scoring engine alone (heuristic-based scores) provides value without AI, but the narrative recommendations and tech-specific advice require language model capabilities to be genuinely useful.
