"""
Enriquecimiento por competidor con todas las fuentes en paralelo.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from . import apis, ads_meta, ads_google

log = logging.getLogger(__name__)


def _guess_github_slug(name: str, domain: str) -> str:
    base = (name or domain.split(".")[0]).lower()
    return re.sub(r"[^a-z0-9-]", "", base.replace(" ", "-"))


def _years_since(timestamp_str: str | None) -> float | None:
    if not timestamp_str or len(timestamp_str) < 4:
        return None
    try:
        year = int(timestamp_str[:4])
        now = datetime.utcnow()
        return round((now.year - year) + now.month / 12, 1)
    except ValueError:
        return None


def enrich_competitor(competitor: dict, query_name: str | None = None, country: str = "AR") -> dict:
    domain = competitor["domain"]
    name = query_name or domain.split(".")[0].title()
    url = f"https://{domain}"

    result = dict(competitor)
    result.update({"url": url, "name": name})

    jobs = {
        "pagespeed": lambda: apis.pagespeed(url),
        "tech_stack": lambda: apis.detect_tech(url),
        "wayback_first": lambda: apis.wayback_first_snapshot(domain),
        "hn": lambda: apis.hn_mentions(name),
        "reddit": lambda: apis.reddit_mentions(name),
        "gdelt": lambda: apis.gdelt_news(name, country_filter=country),
        "github": lambda: apis.github_org(_guess_github_slug(name, domain)),
        "feed_url": lambda: apis.discover_feed(url),
        "meta_ads": lambda: ads_meta.query_ads_archive(name, country=country),
        "google_ads": lambda: ads_google.scrape_ad_count(domain, region=country),
    }

    enriched: dict = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                enriched[key] = fut.result()
            except Exception as e:
                log.warning("Job %s falló para %s: %s", key, domain, e)
                enriched[key] = None

    feed_url = enriched.get("feed_url")
    enriched["blog"] = apis.feed_summary(feed_url) if feed_url else {}
    if feed_url:
        enriched["blog"]["feed_url"] = feed_url

    enriched["age_years"] = _years_since(enriched.get("wayback_first"))

    result["metrics"] = enriched
    return result


def enrich_all(competitors: list[dict], country: str = "AR") -> list[dict]:
    enriched = []
    for i, c in enumerate(competitors, 1):
        log.info("[%d/%d] Enriqueciendo %s", i, len(competitors), c["domain"])
        name = c.get("name_override") or c.get("name")
        enriched.append(enrich_competitor(c, query_name=name, country=country))
    return enriched


def enrich_own_company(domain: str, name: str, country: str = "AR") -> dict:
    own = {"domain": domain, "score": None, "title": "", "snippet": "", "source": "self"}
    return enrich_competitor(own, query_name=name, country=country)


def score_share_of_voice(enriched: list[dict]) -> list[dict]:
    """Calcula share of voice basado en menciones HN + Reddit + GDELT."""
    for c in enriched:
        m = c.get("metrics", {})
        c["voice_total"] = (
            (m.get("hn") or {}).get("total", 0)
            + (m.get("reddit") or {}).get("total", 0)
            + (m.get("gdelt") or {}).get("total", 0)
        )
    grand = sum(c["voice_total"] for c in enriched) or 1
    for c in enriched:
        c["voice_share_pct"] = round((c["voice_total"] / grand) * 100, 1)
    return enriched
