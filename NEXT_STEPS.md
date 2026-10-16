# Post-Launch Enhancement Roadmap

This document captures planned enhancements beyond the initial release. Items are ordered roughly by impact and implementation complexity.

---

## 1. Additional Discovery Providers

**Goal:** Increase business discovery coverage and data quality.

**Planned providers:**

- **Google Maps direct** — Use the Google Places API to query businesses with structured fields (name, address, phone, website, rating, reviews, hours). Significantly higher data quality than SerpAPI scraping. Requires a Google Cloud billing account.
- **Yelp Fusion API** — Yelp provides rich business data including category taxonomy, price range, and review counts. Particularly valuable for restaurants, retail, and services. Free tier available.
- **Yellow Pages / YP.com** — Scrape or use an API to access the Yellow Pages directory, which covers many businesses not indexed by search engines.
- **LinkedIn Company Search** — Discover B2B companies via LinkedIn's API or scraping. Useful for targeting businesses with specific employee counts or verticals.
- **Facebook Business Search** — Many local businesses maintain a Facebook page even without a website. The Facebook Graph API or unofficial scraping can surface these.
- **Apple Maps** — Apple Maps has distinct local business data and covers businesses missing from Google. Access via MapKit JS or the Apple Maps Server API.

**Implementation:** Each new provider is a self-contained class implementing `BaseDiscoveryProvider`. See [docs/PROVIDERS.md](docs/PROVIDERS.md) for the step-by-step guide.

---

## 2. Machine Learning Opportunity Scoring

**Goal:** Replace the current heuristic scoring model with ML-based predictions.

**Approach:**

- Collect ground-truth conversion data (which leads actually converted to clients) and label historical business records.
- Train a gradient boosting model (XGBoost or LightGBM) on features: audit scores, website status, industry, location, revenue potential, social presence, review count.
- Replace the `ScoringEngine` output with model-predicted probability-of-conversion scores.
- Serve the model via an ONNX runtime or a lightweight FastAPI `/predict` endpoint.
- Retrain monthly with new labels from CRM integration (see item 4).

**Libraries:** scikit-learn, XGBoost, LightGBM, ONNX Runtime.

---

## 3. Email Campaign Integration

**Goal:** Allow users to send targeted outreach emails directly from the platform to leads discovered and scored by the system.

**Features:**

- Email template editor with personalization tokens (`{{business_name}}`, `{{city}}`, `{{audit_score}}`, `{{top_recommendation}}`).
- Campaign manager: create campaigns targeting filtered lead segments (e.g., "restaurants in Austin with score < 40").
- Send via transactional email providers: SendGrid, Mailgun, or Amazon SES.
- Track open rates, click rates, and reply rates via webhooks.
- Automatic unsubscribe / CAN-SPAM / GDPR compliance tools.
- Campaign analytics dashboard: send volume, engagement rates, campaign ROI.

**Backend additions:** Campaign model, EmailTemplate model, CampaignRecipient model, email sending Celery task.

---

## 4. CRM Integrations

**Goal:** Sync discovered and scored leads with the CRM tools teams already use.

**Planned integrations:**

### HubSpot
- Push leads as HubSpot Contacts + Companies using the CRM v3 API.
- Sync audit scores to custom HubSpot properties.
- Pull deal stage updates back to keep opportunity scores fresh.
- OAuth 2.0 app with a per-user token store.

### Salesforce
- Create/update Leads and Accounts via the Salesforce REST API.
- Map audit dimensions to Salesforce custom fields.
- Trigger Salesforce flows when a high-opportunity lead is identified.

### Pipedrive / Close.io
- Webhook-based push of new high-score leads.
- Two-way sync of contact status.

**Implementation:** A generic CRM adapter interface similar to the discovery provider pattern. Each CRM ships as a connector class with `push_lead`, `update_lead`, and `sync_status` methods. Users configure their CRM credentials in the Settings page.

---

## 5. White-Labeling Support

**Goal:** Allow agencies to rebrand and resell the platform to their own clients.

**Features:**

- Per-tenant custom logo, color scheme, and domain (via subdomain or CNAME).
- Configurable platform name and email sender identity.
- Remove all "BI Platform" branding from exported PDFs and emails.
- Tenant-scoped data isolation (all queries scoped to `tenant_id`).
- Custom report templates per tenant.
- Billing integration (Stripe) for tenant subscription management.

**Architecture impact:**
- Add `Tenant` model with branding config stored in JSONB.
- Add `tenant_id` foreign key to User, Business, DiscoveryJob, AuditReport.
- Middleware to resolve the current tenant from the request hostname.
- Next.js theming via CSS custom properties injected server-side per tenant.

---

## 6. Multi-Tenant SaaS Features

**Goal:** Evolve from a single-organization tool to a proper SaaS platform with plans, usage limits, and self-service billing.

**Features:**

- **Subscription plans** — Free, Starter, Professional, Agency tiers with monthly discovery and audit quotas.
- **Usage metering** — Track API calls, audits run, and businesses stored per tenant per billing period.
- **Self-service onboarding** — Email verification, password reset, tenant creation without admin intervention.
- **Team management** — Invite team members with role-based access control (Owner, Admin, Analyst, Viewer).
- **Billing portal** — Stripe Billing integration for plan upgrades, invoices, and payment method management.
- **Admin console** — Super-admin dashboard to view all tenants, usage, and revenue metrics.

---

## 7. Mobile App

**Goal:** A native mobile companion app for on-the-go lead management.

**Platform:** React Native (Expo) to share business logic with the existing TypeScript codebase.

**Planned features:**

- Browse and filter discovered businesses.
- View audit scores and AI recommendations.
- Trigger audits for a URL from the mobile camera (QR scan or URL share extension).
- Push notifications for completed audits and new high-opportunity leads.
- Offline mode with local cache of recent leads.
- Quick-action buttons: email lead, call business, add to CRM.

**API requirements:**
- REST API is already mobile-ready (JSON, pagination, filtering).
- Add push notification tokens endpoint and Firebase Cloud Messaging (FCM) integration.
- Consider rate limit adjustments for mobile clients.

---

## Technical Debt & Improvements

Beyond new features, the following technical improvements are planned:

- **End-to-end test suite** using Playwright Test for full browser-based flows.
- **OpenAPI client generation** — auto-generate a TypeScript SDK from the OpenAPI spec to replace manual `api.ts` calls.
- **Database query optimization** — add indexes on frequently filtered columns (industry, city, country, overall_score) and profile slow queries under production load.
- **Celery task priorities** — separate queues for time-sensitive audit tasks vs. bulk discovery jobs to prevent starvation.
- **Screenshot CDN** — store screenshots in S3 or Cloudflare R2 instead of local disk for scalability and durability.
- **Structured audit logging** — ship JSON logs to a log aggregation service (Datadog, Grafana Loki) for operational visibility.
- **Rate limit headers** — expose `X-RateLimit-Remaining` headers on API responses.
- **GraphQL API** — optional GraphQL endpoint for frontend flexibility (complementing the REST API, not replacing it).
