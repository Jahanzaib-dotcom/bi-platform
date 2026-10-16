"""
Scraper Engine package.

Exposes the primary entry-point (ScraperEngine) and the supporting
TechStackDetector so callers can import directly from this package.
"""

from app.engines.scraper.scraper_engine import ScrapedData, ScraperEngine
from app.engines.scraper.tech_detector import TechDetectionResult, TechStackDetector

__all__ = [
    "ScraperEngine",
    "ScrapedData",
    "TechStackDetector",
    "TechDetectionResult",
]
