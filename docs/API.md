# API Reference

All REST endpoints are prefixed with `/api/v1`. The base URL for a local development server is `http://localhost:8000/api/v1`.

Interactive documentation is available at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc`.

## Authentication

Every endpoint (except register and login) requires a bearer token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Authentication Endpoints

| Method | Path | Description | Auth required |
|---|---|---|---|
| `POST` | `/auth/register` | Create a new user account | No |
| `POST` | `/auth/login` | Obtain access + refresh token pair | No |
| `POST` | `/auth/refresh` | Exchange a refresh token for a new token pair | No |
| `POST` | `/auth/logout` | Acknowledge logout (client discards tokens) | Yes |
| `GET` | `/auth/me` | Return the current authenticated user | Yes |
| `PUT` | `/auth/me` | Update the current user's profile | Yes |
| `POST` | `/auth/change-password` | Change the current user's password | Yes |
| `GET` | `/auth/api-key` | Regenerate and return a new API key | Yes |

#### POST /auth/register

Request body:
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "strongpassword",
  "full_name": "John Doe"
}
```

Response `201 Created`:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### POST /auth/login

Request body:
```json
{
  "email": "user@example.com",
  "password": "strongpassword"
}
```

Response `200 OK`:
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### POST /auth/refresh

Request body:
```json
{ "refresh_token": "<jwt>" }
```

Returns a new token pair identical in shape to the login response.

---

## Business Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/businesses` | Paginated list with optional filters |
| `GET` | `/businesses/search` | Full-text search across name, category, city, industry |
| `GET` | `/businesses/export` | Trigger async export job (CSV / Excel / PDF) |
| `GET` | `/businesses/{id}` | Single business by UUID |
| `POST` | `/businesses` | Manually create a business record |
| `PUT` | `/businesses/{id}` | Update a business record |
| `DELETE` | `/businesses/{id}` | Permanently delete a business (cascades) |
| `POST` | `/businesses/{id}/audit` | Trigger a single website audit |
| `GET` | `/businesses/{id}/audits` | Paginated audit history for a business |
| `GET` | `/businesses/{id}/screenshots` | Paginated screenshots for a business |
| `POST` | `/businesses/bulk-audit` | Queue audit tasks for up to 100 businesses |

### Common Query Parameters for GET /businesses

| Parameter | Type | Description |
|---|---|---|
| `industry` | string | Filter by exact industry name |
| `country` | string | Filter by country |
| `city` | string | Filter by city |
| `has_website` | boolean | `true` / `false` |
| `min_score` | float 0–100 | Minimum overall score |
| `max_score` | float 0–100 | Maximum overall score |
| `page` | int ≥ 1 | Page number (default 1) |
| `page_size` | int 1–200 | Items per page (default 20) |

### Paginated Response Shape

```json
{
  "items": [ ... ],
  "total": 1234,
  "page": 1,
  "page_size": 20,
  "pages": 62
}
```

### Business Object Fields

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Primary key |
| `name` | string | Business name |
| `slug` | string | URL-safe identifier |
| `industry` | string | Industry classification |
| `category` | string | Business category |
| `city`, `state`, `country` | string | Location |
| `website_url` | string | Website URL if known |
| `has_website` | boolean | Whether a website was found |
| `website_status` | enum | `active`, `inactive`, `error`, `unknown` |
| `overall_score` | float 0–100 | Composite audit score |
| `opportunity_score` | float 0–100 | Lead opportunity score |
| `priority_score` | float 0–100 | Prioritisation score |
| `revenue_potential` | float | Estimated revenue potential (USD) |
| `audit_count` | int | Number of completed audits |
| `discovered_at` | ISO datetime | When the business was first found |
| `last_audited_at` | ISO datetime | When the last audit completed |

---

## Discovery Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/discovery/jobs` | Paginated list of discovery jobs |
| `POST` | `/discovery/jobs` | Create and immediately queue a discovery job |
| `GET` | `/discovery/jobs/{id}` | Full details of a single job |
| `POST` | `/discovery/jobs/{id}/pause` | Pause a running or pending job |
| `POST` | `/discovery/jobs/{id}/resume` | Resume a paused job |
| `POST` | `/discovery/jobs/{id}/cancel` | Cancel a pending or running job |
| `DELETE` | `/discovery/jobs/{id}` | Delete a job record (cancel first if running) |
| `GET` | `/discovery/providers` | List all providers with availability status |
| `POST` | `/discovery/providers/{name}/test` | Test connectivity of a provider |
| `GET` | `/discovery/jobs/{id}/results` | Paginated raw discovery results for a job |

### POST /discovery/jobs Request Body

```json
{
  "name": "Restaurants in Austin TX",
  "keywords": "restaurant",
  "country": "United States",
  "city": "Austin",
  "industry": "Food & Beverage",
  "sources": ["duckduckgo", "nominatim"],
  "max_results": 500
}
```

`sources` defaults to `["duckduckgo"]`. Available values: `duckduckgo`, `serpapi`, `nominatim`, `web_search`.

### Discovery Job Object Fields

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Job ID |
| `status` | enum | `pending`, `running`, `paused`, `completed`, `cancelled`, `failed` |
| `config` | object | Original job configuration |
| `total_found` | int | Raw results found so far |
| `total_processed` | int | Results successfully saved as businesses |
| `total_errors` | int | Results that failed processing |
| `started_at` | ISO datetime | When the worker picked up the job |
| `completed_at` | ISO datetime | When the job finished |
| `estimated_completion` | ISO datetime | ETA (if available) |

---

## Audit Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/audits` | Paginated list of all audit reports |
| `GET` | `/audits/stats` | Aggregate statistics across all audits |
| `POST` | `/audits/bulk` | Queue audit tasks for multiple businesses |
| `GET` | `/audits/{id}` | Full audit report by UUID |
| `POST` | `/audits` | Trigger an audit for a URL |
| `DELETE` | `/audits/{id}` | Delete an audit report (screenshots cascade) |
| `GET` | `/audits/{id}/screenshots` | All screenshots captured during an audit |

### Audit Report Score Fields

| Field | Score range | Description |
|---|---|---|
| `ui_score` | 0–100 | Visual design and layout quality |
| `ux_score` | 0–100 | User experience and navigation |
| `mobile_score` | 0–100 | Mobile responsiveness |
| `seo_score` | 0–100 | Search engine optimisation |
| `accessibility_score` | 0–100 | WCAG compliance (axe-core) |
| `speed_score` | 0–100 | Page load performance (Lighthouse) |
| `security_score` | 0–100 | HTTPS, security headers |
| `branding_score` | 0–100 | Brand consistency |
| `content_score` | 0–100 | Content quality and clarity |
| `conversion_score` | 0–100 | CTA effectiveness |
| `overall_score` | 0–100 | Weighted composite |

### Audit Report Additional Fields

| Field | Type | Description |
|---|---|---|
| `status` | enum | `pending`, `running`, `completed`, `failed` |
| `recommendations` | array | List of actionable improvement recommendations |
| `ai_analysis` | object | Claude AI narrative analysis |
| `tech_stack` | object | Detected technologies (CMS, frameworks, CDN, etc.) |
| `performance_metrics` | object | Lighthouse raw metrics |
| `seo_issues` | array | Specific SEO problems found |
| `accessibility_issues` | array | WCAG violations |
| `broken_links` | array | URLs returning 4xx/5xx |

---

## Analytics Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/analytics/dashboard` | Top-level KPI metrics |
| `GET` | `/analytics/industries` | Business counts and scores by industry |
| `GET` | `/analytics/geography` | Business counts grouped by country, state, or city |
| `GET` | `/analytics/opportunities` | Opportunity tier breakdown |
| `GET` | `/analytics/trends` | Daily time-series of discoveries and audits |
| `GET` | `/analytics/revenue` | Revenue potential estimates by industry |
| `GET` | `/analytics/scores-distribution` | Histogram of scores across all businesses |

### GET /analytics/dashboard Response

```json
{
  "total_businesses": 4821,
  "total_audited": 1203,
  "total_without_website": 982,
  "total_with_website": 3839,
  "avg_overall_score": 54.2,
  "avg_opportunity_score": 61.7,
  "avg_revenue_potential": 3400.00,
  "total_discovery_jobs": 47,
  "total_audits_completed": 1203,
  "businesses_added_last_30_days": 318
}
```

### GET /analytics/geography Query Parameters

| Parameter | Values | Default |
|---|---|---|
| `group_by` | `country`, `state`, `city` | `country` |
| `limit` | 1–200 | 30 |

### GET /analytics/trends Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `days` | int 7–365 | 30 |

### GET /analytics/scores-distribution Query Parameters

| Parameter | Type | Default |
|---|---|---|
| `buckets` | int 5–20 | 10 |
| `score_field` | `overall_score`, `opportunity_score`, `priority_score` | `overall_score` |

---

## WebSocket Protocol

### Connection

Connect to `ws://localhost:8000/ws/live?token=<access_token>`.

The JWT access token must be passed as the `token` query parameter. Invalid or missing tokens cause the connection to close immediately with code `4001`.

### Server-to-Client Messages

All messages are JSON objects with a `type` field and an `ts` (ISO 8601 timestamp) field.

| `type` | Additional fields | Description |
|---|---|---|
| `connected` | `client_id`, `user_id`, `active_connections` | Sent immediately after the handshake is accepted |
| `ping` | — | Heartbeat sent every 30 seconds |
| `pong` | — | Response to a client ping |
| `job_progress` | `job_id`, `status`, `total_found`, `total_processed` | Discovery job status update |
| `audit_complete` | `audit_id`, `business_id`, `scores` | Fired when an audit finishes |
| `new_business` | `business` | Fired when a new business is created |
| `error_event` | `code`, `message` | Server-side error notification |

### Client-to-Server Messages

| `type` | Description |
|---|---|
| `ping` | Request a pong reply |

### Example Session

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/live?token=' + accessToken);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'ping') {
    ws.send(JSON.stringify({ type: 'pong' }));
  }

  if (msg.type === 'audit_complete') {
    console.log('Audit done:', msg.audit_id, msg.scores);
  }
};
```

### Redis Pub/Sub Integration

Workers publish events on Redis channels matching `bi:ws:<event_type>`. The WebSocket handler subscribes to `bi:ws:*` via Redis pub/sub, enabling cross-worker broadcast in multi-process deployments.

---

## Error Responses

All errors follow the standard FastAPI error shape:

```json
{
  "detail": "Human-readable error message"
}
```

| HTTP Status | Meaning |
|---|---|
| `400` | Bad request or validation error |
| `401` | Missing or invalid authentication token |
| `403` | Insufficient permissions or inactive account |
| `404` | Resource not found |
| `409` | Conflict (duplicate email, running job, etc.) |
| `422` | Request body failed schema validation |
| `500` | Unexpected server error |
