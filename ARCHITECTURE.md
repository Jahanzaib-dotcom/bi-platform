# Architecture Overview

## System Layers

### Frontend (Next.js 14)
- App Router with server/client components
- Zustand for state management
- React Query for server state
- Framer Motion animations
- shadcn/ui component library
- Recharts for data visualization
- WebSocket client for live updates

### Backend (FastAPI)
- Async REST API
- WebSocket server
- JWT auth with refresh tokens
- Background task workers
- Plugin-based engine architecture

### Discovery Engine
- Provider interface pattern
- Built-in: SerpAPI, OpenStreetMap Nominatim, DuckDuckGo
- Configurable rate limiting per provider
- Deduplication via business fingerprinting

### Audit Engine
- Playwright for screenshots and JS rendering
- Lighthouse CI integration
- axe-core for accessibility
- Custom heuristics for UI/UX scoring
- AI analysis via Claude API

### Scoring Engine
- Weighted composite scores
- Opportunity detection algorithms
- Revenue potential estimation
- Priority ranking

### Queue (Redis + Celery)
- Discovery jobs
- Audit jobs
- Screenshot jobs
- Export jobs

### Database (PostgreSQL / SQLite)
- SQLAlchemy ORM
- Alembic migrations
- Async sessions
