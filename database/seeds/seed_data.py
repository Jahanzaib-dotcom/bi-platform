"""
Seed script for bi-platform.

Run from the project root via:
    cd backend && python -m database.seeds.seed_data

Or via the helper script:
    bash scripts/seed.sh

What this script creates
------------------------
* 1  admin user  (admin@biplatform.com / admin123)
* 50 sample businesses across varied industries, countries and cities
* 1  completed discovery job linked to the admin user
* 20 sample audit reports (one per the first 20 businesses)
* 20 screenshot metadata rows (one desktop + one mobile per audit report)
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the backend package importable when the script is executed directly.
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

# Import models *after* sys.path is set up.
import app.models  # noqa: F401 – registers all ORM tables on Base.metadata
from app.core.database import Base
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business, WebsiteStatus
from app.models.discovery_job import DiscoveryJob, JobStatus
from app.models.discovery_result import DiscoveryResult, ResultStatus
from app.models.screenshot import Screenshot, Viewport
from app.models.user import User
from app.core.security import get_password_hash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RNG = random.Random(42)  # fixed seed for reproducible data


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return utcnow() - timedelta(days=n)


def rand_score(lo: float = 20.0, hi: float = 95.0) -> float:
    return round(RNG.uniform(lo, hi), 1)


def rand_float(lo: float, hi: float) -> float:
    return round(RNG.uniform(lo, hi), 2)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

INDUSTRIES = [
    ("Restaurant", "Food & Beverage", "Fast Food"),
    ("Restaurant", "Food & Beverage", "Fine Dining"),
    ("Restaurant", "Food & Beverage", "Cafe"),
    ("Law Firm", "Professional Services", "Family Law"),
    ("Law Firm", "Professional Services", "Personal Injury"),
    ("Law Firm", "Professional Services", "Corporate Law"),
    ("Dental Practice", "Healthcare", "General Dentistry"),
    ("Dental Practice", "Healthcare", "Orthodontics"),
    ("Plumber", "Home Services", "Residential Plumbing"),
    ("Plumber", "Home Services", "Commercial Plumbing"),
    ("Gym", "Health & Fitness", "CrossFit"),
    ("Gym", "Health & Fitness", "Yoga Studio"),
    ("Gym", "Health & Fitness", "Personal Training"),
    ("Retailer", "Retail", "Clothing"),
    ("Retailer", "Retail", "Electronics"),
    ("Retailer", "Retail", "Home Decor"),
    ("Auto Repair", "Automotive", "General Repair"),
    ("Auto Repair", "Automotive", "Body Shop"),
    ("Accountant", "Professional Services", "Tax & Accounting"),
    ("Real Estate", "Real Estate", "Residential"),
    ("Real Estate", "Real Estate", "Commercial"),
    ("Salon", "Beauty", "Hair Salon"),
    ("Salon", "Beauty", "Nail Salon"),
    ("Veterinarian", "Healthcare", "Small Animals"),
    ("Electrician", "Home Services", "Residential"),
    ("Landscaping", "Home Services", "Lawn Care"),
    ("Pharmacy", "Healthcare", "Retail Pharmacy"),
    ("Bakery", "Food & Beverage", "Artisan Bakery"),
    ("Hotel", "Hospitality", "Boutique Hotel"),
    ("Chiropractor", "Healthcare", "General Chiropractic"),
]

# (country, state/province, city, zip_prefix)
LOCATIONS = [
    # United States
    ("United States", "California", "Los Angeles", "900"),
    ("United States", "California", "San Francisco", "941"),
    ("United States", "California", "San Diego", "921"),
    ("United States", "New York", "New York City", "100"),
    ("United States", "New York", "Brooklyn", "112"),
    ("United States", "Texas", "Houston", "770"),
    ("United States", "Texas", "Austin", "787"),
    ("United States", "Texas", "Dallas", "752"),
    ("United States", "Florida", "Miami", "331"),
    ("United States", "Florida", "Orlando", "328"),
    ("United States", "Illinois", "Chicago", "606"),
    ("United States", "Washington", "Seattle", "981"),
    # United Kingdom
    ("United Kingdom", "England", "London", "EC1"),
    ("United Kingdom", "England", "Manchester", "M1"),
    ("United Kingdom", "England", "Birmingham", "B1"),
    ("United Kingdom", "Scotland", "Edinburgh", "EH1"),
    # Canada
    ("Canada", "Ontario", "Toronto", "M5"),
    ("Canada", "British Columbia", "Vancouver", "V6"),
    ("Canada", "Quebec", "Montreal", "H2"),
    ("Canada", "Alberta", "Calgary", "T2"),
    # Australia
    ("Australia", "New South Wales", "Sydney", "2000"),
    ("Australia", "Victoria", "Melbourne", "3000"),
    ("Australia", "Queensland", "Brisbane", "4000"),
    ("Australia", "Western Australia", "Perth", "6000"),
]

# Website status distribution weights: 30% no website, 40% outdated, 30% active
WEBSITE_STATUS_CHOICES = (
    [None] * 30          # 30 % — no website (has_website=False)
    + [WebsiteStatus.abandoned] * 20   # 20 % — outdated/abandoned
    + [WebsiteStatus.parked] * 10      # 10 % — parked / placeholder
    + [WebsiteStatus.inactive] * 10    # 10 % — inactive/broken
    + [WebsiteStatus.active] * 30      # 30 % — active
)

TECH_STACKS = [
    [{"name": "WordPress", "category": "CMS", "version": "6.4"}],
    [{"name": "Squarespace", "category": "Website Builder", "version": None}],
    [{"name": "Wix", "category": "Website Builder", "version": None}],
    [{"name": "Shopify", "category": "E-commerce", "version": None}],
    [{"name": "React", "category": "Frontend Framework", "version": "18"}, {"name": "Next.js", "category": "Meta Framework", "version": "14"}],
    [{"name": "jQuery", "category": "JavaScript Library", "version": "3.6"}, {"name": "Bootstrap", "category": "CSS Framework", "version": "5"}],
    [{"name": "Webflow", "category": "Website Builder", "version": None}],
    [{"name": "Drupal", "category": "CMS", "version": "10"}],
]

SEO_ISSUE_TEMPLATES = [
    {"type": "missing_meta", "severity": "high", "message": "Meta description is missing"},
    {"type": "missing_alt", "severity": "medium", "message": "Images missing alt attributes"},
    {"type": "slow_lcp", "severity": "high", "message": "Largest Contentful Paint exceeds 4 s"},
    {"type": "no_sitemap", "severity": "medium", "message": "XML sitemap not found"},
    {"type": "duplicate_title", "severity": "medium", "message": "Duplicate page titles detected"},
    {"type": "broken_links", "severity": "low", "message": "3 broken internal links found"},
    {"type": "no_canonical", "severity": "low", "message": "Canonical tag not set"},
    {"type": "thin_content", "severity": "medium", "message": "Several pages have fewer than 300 words"},
]

RECOMMENDATION_TEMPLATES = [
    {"category": "seo", "priority": "high", "title": "Add meta descriptions", "description": "Write unique meta descriptions for all pages to improve CTR."},
    {"category": "performance", "priority": "high", "title": "Compress images", "description": "Use WebP format and lazy loading to reduce page weight by ~60 %."},
    {"category": "ux", "priority": "medium", "title": "Improve mobile navigation", "description": "Current hamburger menu is difficult to interact with on small screens."},
    {"category": "security", "priority": "high", "title": "Enable HTTPS", "description": "Site is still served over HTTP — install an SSL certificate immediately."},
    {"category": "content", "priority": "medium", "title": "Update copyright footer", "description": "Footer shows copyright year 2019 — update to current year."},
    {"category": "conversion", "priority": "high", "title": "Add clear call-to-action", "description": "Homepage lacks a primary CTA button; adding one could increase conversions by 20–30 %."},
    {"category": "accessibility", "priority": "medium", "title": "Improve colour contrast", "description": "Text-to-background contrast ratio fails WCAG AA on 5 pages."},
    {"category": "seo", "priority": "low", "title": "Create an XML sitemap", "description": "A sitemap helps search engines discover and index all pages."},
]

BUSINESS_NAME_PREFIXES = [
    "Premier", "Elite", "Pro", "City", "Metro", "Summit", "Apex", "Peak",
    "Cornerstone", "Heritage", "Central", "Golden", "Sunrise", "Lakeside",
    "Riverside", "Harbor", "Highland", "Valley", "Coastal", "Urban",
    "Classic", "Modern", "Alpha", "Omega", "Nexus", "Pinnacle", "Crest",
    "Sterling", "Diamond", "Crystal",
]


def make_business_name(industry: str, prefix: str) -> str:
    """Compose a realistic business name."""
    short = industry.split()[0]
    return f"{prefix} {short}"


def make_slug(name: str, uid: str) -> str:
    """Generate a unique URL-safe slug."""
    base = name.lower().replace(" ", "-").replace("'", "")
    # Keep only alphanumeric and hyphens.
    base = "".join(c for c in base if c.isalnum() or c == "-")
    return f"{base}-{uid[:8]}"


def make_website_url(name: str, country: str) -> str:
    slug = name.lower().replace(" ", "").replace("'", "")
    slug = "".join(c for c in slug if c.isalnum())
    tld = ".co.uk" if country == "United Kingdom" else ".com.au" if country == "Australia" else ".ca" if country == "Canada" else ".com"
    return f"https://www.{slug}{tld}"


def make_phone(country: str) -> str:
    if country == "United States":
        return f"+1 ({RNG.randint(200, 999)}) {RNG.randint(200, 999)}-{RNG.randint(1000, 9999)}"
    if country == "United Kingdom":
        return f"+44 {RNG.randint(1200, 9999)} {RNG.randint(100000, 999999)}"
    if country == "Canada":
        return f"+1 ({RNG.randint(200, 999)}) {RNG.randint(200, 999)}-{RNG.randint(1000, 9999)}"
    return f"+61 {RNG.randint(2, 9)} {RNG.randint(1000, 9999)} {RNG.randint(1000, 9999)}"


# ---------------------------------------------------------------------------
# Seed builders
# ---------------------------------------------------------------------------

def build_admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="admin@biplatform.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        full_name="Platform Admin",
        is_active=True,
        is_superuser=True,
    )


def build_businesses(count: int = 50) -> list[Business]:
    businesses: list[Business] = []
    used_names: set[str] = set()

    prefixes = BUSINESS_NAME_PREFIXES.copy()
    RNG.shuffle(prefixes)

    for i in range(count):
        industry_tuple = INDUSTRIES[i % len(INDUSTRIES)]
        industry, category, subcategory = industry_tuple
        location = LOCATIONS[i % len(LOCATIONS)]
        country, state, city, zip_prefix = location
        prefix = prefixes[i % len(prefixes)]

        # Ensure unique name.
        base_name = make_business_name(industry, prefix)
        name = base_name
        suffix = 2
        while name in used_names:
            name = f"{base_name} {suffix}"
            suffix += 1
        used_names.add(name)

        bid = uuid.uuid4()
        slug = make_slug(name, str(bid))

        ws_status: WebsiteStatus | None = RNG.choice(WEBSITE_STATUS_CHOICES)
        has_website = ws_status is not None
        website_url = make_website_url(name, country) if has_website else None

        # Scores are only meaningful when a website exists.
        overall = rand_score(15, 85) if has_website else None
        opportunity = rand_score(40, 95) if not has_website else rand_score(10, 60)
        priority = rand_score(30, 90)
        revenue = rand_float(5_000, 150_000) if has_website else rand_float(20_000, 200_000)

        discovered = days_ago(RNG.randint(1, 180))

        social: dict | None = None
        if has_website and RNG.random() > 0.3:
            social = {}
            platforms = ["facebook", "instagram", "twitter", "linkedin", "yelp"]
            chosen = RNG.sample(platforms, k=RNG.randint(1, 3))
            for p in chosen:
                handle = name.lower().replace(" ", "")
                social[p] = f"https://{p}.com/{handle}"

        businesses.append(
            Business(
                id=bid,
                name=name,
                slug=slug,
                description=f"{name} is a local {industry.lower()} business serving {city}.",
                industry=industry,
                category=category,
                subcategory=subcategory,
                country=country,
                state=state,
                city=city,
                zip_code=f"{zip_prefix}{RNG.randint(10, 99)}",
                address=f"{RNG.randint(1, 9999)} Main St, {city}",
                phone=make_phone(country),
                email=f"info@{slug[:20]}.com",
                website_url=website_url,
                has_website=has_website,
                website_status=ws_status,
                social_profiles=social,
                source="seed_data",
                source_id=str(i + 1),
                source_url=None,
                discovered_at=discovered,
                overall_score=overall,
                opportunity_score=opportunity,
                priority_score=priority,
                revenue_potential=revenue,
                audit_count=0,
                tags=[industry.lower(), category.lower(), city.lower()],
            )
        )

    return businesses


def build_discovery_job(user: User, businesses: list[Business]) -> DiscoveryJob:
    started = days_ago(7)
    completed = started + timedelta(hours=2, minutes=34)

    job = DiscoveryJob(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Initial Business Discovery — North America + UK + AU",
        status=JobStatus.completed,
        config={
            "sources": ["duckduckgo", "nominatim", "serpapi"],
            "countries": ["United States", "United Kingdom", "Canada", "Australia"],
            "industries": [t[0] for t in INDUSTRIES[:10]],
            "keywords": ["local business", "near me", "professional services"],
            "max_results": 200,
        },
        total_found=len(businesses),
        total_processed=len(businesses),
        total_errors=3,
        started_at=started,
        completed_at=completed,
        logs=[
            {"ts": started.isoformat(), "level": "info", "msg": "Job started"},
            {"ts": (started + timedelta(minutes=30)).isoformat(), "level": "info", "msg": f"Processed 25 businesses"},
            {"ts": (started + timedelta(hours=1)).isoformat(), "level": "info", "msg": f"Processed 50 businesses — halfway"},
            {"ts": completed.isoformat(), "level": "info", "msg": "Job completed successfully"},
        ],
    )
    return job


def build_discovery_results(
    job: DiscoveryJob, businesses: list[Business]
) -> list[DiscoveryResult]:
    results: list[DiscoveryResult] = []
    for biz in businesses:
        processed_at = job.started_at + timedelta(
            seconds=RNG.randint(0, int((job.completed_at - job.started_at).total_seconds()))
        )
        results.append(
            DiscoveryResult(
                id=uuid.uuid4(),
                job_id=job.id,
                business_id=biz.id,
                source="duckduckgo",
                source_id=str(uuid.uuid4()),
                status=ResultStatus.processed,
                processed_at=processed_at,
                raw_data={
                    "name": biz.name,
                    "url": biz.website_url,
                    "phone": biz.phone,
                    "address": biz.address,
                    "city": biz.city,
                    "country": biz.country,
                },
            )
        )
    return results


def build_audit_reports(businesses: list[Business], count: int = 20) -> list[AuditReport]:
    """Create one completed audit report for each of the first *count* businesses."""
    reports: list[AuditReport] = []

    for biz in businesses[:count]:
        started = days_ago(RNG.randint(1, 30))
        completed = started + timedelta(minutes=RNG.randint(3, 12))

        has_site = biz.has_website
        ui = rand_score(20, 90) if has_site else None
        ux = rand_score(20, 85) if has_site else None
        mobile = rand_score(15, 95) if has_site else None
        seo = rand_score(10, 80) if has_site else None
        accessibility = rand_score(25, 90) if has_site else None
        speed = rand_score(10, 95) if has_site else None
        security = rand_score(20, 100) if has_site else None
        branding = rand_score(20, 85) if has_site else None
        content = rand_score(15, 90) if has_site else None
        conversion = rand_score(10, 80) if has_site else None

        scores = [s for s in [ui, ux, mobile, seo, accessibility, speed, security, branding, content, conversion] if s is not None]
        overall = round(sum(scores) / len(scores), 1) if scores else None

        seo_issues_sample = RNG.sample(SEO_ISSUE_TEMPLATES, k=RNG.randint(1, 4)) if has_site else []
        recs_sample = RNG.sample(RECOMMENDATION_TEMPLATES, k=RNG.randint(2, 5)) if has_site else []
        tech_stack = RNG.choice(TECH_STACKS) if has_site else None

        perf_metrics: dict | None = None
        if has_site:
            perf_metrics = {
                "lcp": rand_float(1.2, 8.5),
                "fid": rand_float(10, 300),
                "cls": rand_float(0.0, 0.5),
                "ttfb": rand_float(100, 2000),
                "page_size_kb": RNG.randint(300, 5000),
                "requests": RNG.randint(15, 120),
            }

        ai_analysis: dict | None = None
        if has_site:
            ai_analysis = {
                "strengths": [
                    f"Clear {biz.industry} focus throughout the site",
                    "Contact information is easy to find",
                ],
                "weaknesses": [
                    "Outdated design language",
                    "No clear calls-to-action on key pages",
                ],
                "opportunities": [
                    "Add online booking / appointment scheduling",
                    "Create location-specific landing pages for SEO",
                ],
                "estimated_value": f"${RNG.randint(2, 15)},000 — ${RNG.randint(16, 40)},000 in annual revenue improvement",
            }

        report = AuditReport(
            id=uuid.uuid4(),
            business_id=biz.id,
            status=AuditStatus.completed,
            website_url=biz.website_url,
            ui_score=ui,
            ux_score=ux,
            mobile_score=mobile,
            seo_score=seo,
            accessibility_score=accessibility,
            speed_score=speed,
            security_score=security,
            branding_score=branding,
            content_score=content,
            conversion_score=conversion,
            overall_score=overall,
            seo_issues=seo_issues_sample,
            accessibility_issues=[],
            performance_metrics=perf_metrics,
            recommendations=recs_sample,
            ai_analysis=ai_analysis,
            tech_stack=tech_stack,
            broken_links=[],
            started_at=started,
            completed_at=completed,
        )
        reports.append(report)

        # Update denormalised counters on the business.
        biz.audit_count = 1
        biz.last_audited_at = completed
        if overall is not None:
            biz.overall_score = overall

    return reports


def build_screenshots(
    businesses: list[Business], reports: list[AuditReport]
) -> list[Screenshot]:
    """Create desktop + mobile screenshot metadata rows for each audit report."""
    screenshots: list[Screenshot] = []

    biz_map = {biz.id: biz for biz in businesses}

    for report in reports:
        biz = biz_map[report.business_id]
        if not biz.has_website:
            continue

        captured = report.completed_at or days_ago(RNG.randint(1, 30))

        # Desktop screenshot
        desktop_filename = f"{biz.slug}-desktop.png"
        screenshots.append(
            Screenshot(
                id=uuid.uuid4(),
                business_id=biz.id,
                audit_id=report.id,
                viewport=Viewport.desktop,
                file_path=f"./storage/screenshots/{desktop_filename}",
                file_url=f"/static/screenshots/{desktop_filename}",
                file_size=RNG.randint(150_000, 800_000),
                width=1440,
                height=900,
                captured_at=captured,
                url=biz.website_url,
            )
        )

        # Update audit report screenshot URL.
        report.screenshot_desktop_url = f"/static/screenshots/{desktop_filename}"

        # Mobile screenshot
        mobile_filename = f"{biz.slug}-mobile.png"
        screenshots.append(
            Screenshot(
                id=uuid.uuid4(),
                business_id=biz.id,
                audit_id=report.id,
                viewport=Viewport.mobile,
                file_path=f"./storage/screenshots/{mobile_filename}",
                file_url=f"/static/screenshots/{mobile_filename}",
                file_size=RNG.randint(80_000, 400_000),
                width=390,
                height=844,
                captured_at=captured,
                url=biz.website_url,
            )
        )

        report.screenshot_mobile_url = f"/static/screenshots/{mobile_filename}"

    return screenshots


# ---------------------------------------------------------------------------
# Database initialisation helpers
# ---------------------------------------------------------------------------

def _get_async_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./biplatform.db",
    )
    # Ensure async driver.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("sqlite:///") and "+aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


async def seed() -> None:
    url = _get_async_url()
    engine = create_async_engine(url, echo=False)

    # Create tables if they do not exist yet (idempotent).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with session_factory() as session:
        # ------------------------------------------------------------------
        # Admin user
        # ------------------------------------------------------------------
        from sqlalchemy import select

        existing_admin = await session.execute(
            select(User).where(User.email == "admin@biplatform.com")
        )
        admin = existing_admin.scalar_one_or_none()
        if admin is None:
            admin = build_admin_user()
            session.add(admin)
            await session.flush()
            print(f"  Created admin user: {admin.email}")
        else:
            print(f"  Admin user already exists: {admin.email}")

        # ------------------------------------------------------------------
        # Businesses
        # ------------------------------------------------------------------
        existing_count_result = await session.execute(
            select(Business)
        )
        existing_businesses = existing_count_result.scalars().all()

        if len(existing_businesses) < 50:
            businesses = build_businesses(50)
            session.add_all(businesses)
            await session.flush()
            print(f"  Created {len(businesses)} businesses")
        else:
            businesses = list(existing_businesses)
            print(f"  {len(businesses)} businesses already present — skipping")

        # ------------------------------------------------------------------
        # Discovery job
        # ------------------------------------------------------------------
        existing_jobs = await session.execute(
            select(DiscoveryJob).where(DiscoveryJob.user_id == admin.id)
        )
        job = existing_jobs.scalars().first()
        if job is None:
            job = build_discovery_job(admin, businesses)
            session.add(job)
            await session.flush()
            print(f"  Created discovery job: {job.name}")

            results = build_discovery_results(job, businesses)
            session.add_all(results)
            await session.flush()
            print(f"  Created {len(results)} discovery results")
        else:
            print(f"  Discovery job already exists: {job.name}")

        # ------------------------------------------------------------------
        # Audit reports
        # ------------------------------------------------------------------
        existing_audits = await session.execute(select(AuditReport))
        audit_rows = existing_audits.scalars().all()
        if not audit_rows:
            reports = build_audit_reports(businesses, count=20)
            session.add_all(reports)
            await session.flush()
            print(f"  Created {len(reports)} audit reports")

            screenshots = build_screenshots(businesses, reports)
            session.add_all(screenshots)
            await session.flush()
            print(f"  Created {len(screenshots)} screenshot records")
        else:
            print(f"  {len(audit_rows)} audit reports already present — skipping")

        await session.commit()

    await engine.dispose()
    print("\nSeed complete.")


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(seed())
