"""
Wrappers para todas las APIs gratuitas que usa el analizador.

Cada función:
- Tiene timeout razonable.
- Falla silenciosamente (devuelve None / {} si algo falla) para que un error
  puntual no rompa el enriquecimiento de los otros competidores.

APIs incluidas:
- Google PageSpeed Insights (opcional con key)
- OpenPageRank (con key gratuita)
- GitHub REST API
- Hacker News Search (Algolia)
- Reddit JSON endpoints
- GDELT DOC API
- Wayback Machine CDX API
- Serper.dev (búsqueda Google) — opcional
- Detección heurística de tech stack
- Discovery de feed RSS/Atom

(Para anuncios de Meta y Google ver ads_meta.py / ads_google.py)
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
USER_AGENT = (
    "raona-radar/1.0 (+competitive intelligence research; "
    "contact: marketing@raona.com)"
)


def _get(url: str, **kwargs) -> requests.Response | None:
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", USER_AGENT)
    try:
        r = requests.get(url, timeout=DEFAULT_TIMEOUT, headers=headers, **kwargs)
        if r.status_code >= 400:
            log.debug("GET %s -> %s", url, r.status_code)
            return None
        return r
    except requests.RequestException as e:
        log.debug("GET %s failed: %s", url, e)
        return None


# ============================================================================
# Google PageSpeed Insights
# ============================================================================
def pagespeed(url: str, strategy: str = "mobile") -> dict[str, Any]:
    """Devuelve los scores de Lighthouse."""
    api_key = os.getenv("PAGESPEED_API_KEY", "")
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "seo", "accessibility", "best-practices"],
    }
    if api_key:
        params["key"] = api_key

    r = _get(endpoint, params=params)
    if not r:
        return {}
    try:
        cats = r.json().get("lighthouseResult", {}).get("categories", {})
        return {
            "performance": round((cats.get("performance", {}).get("score") or 0) * 100),
            "seo": round((cats.get("seo", {}).get("score") or 0) * 100),
            "accessibility": round((cats.get("accessibility", {}).get("score") or 0) * 100),
            "best_practices": round((cats.get("best-practices", {}).get("score") or 0) * 100),
        }
    except (ValueError, KeyError):
        return {}


# ============================================================================
# OpenPageRank
# ============================================================================
def open_page_rank(domains: list[str]) -> dict[str, dict[str, Any]]:
    api_key = os.getenv("OPENPAGERANK_API_KEY", "")
    if not api_key:
        return {}
    endpoint = "https://openpagerank.com/api/v1.0/getPageRank"
    headers = {"API-OPR": api_key, "User-Agent": USER_AGENT}
    params = [("domains[]", d) for d in domains]
    try:
        r = requests.get(endpoint, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        if r.status_code >= 400:
            return {}
        out = {}
        for entry in r.json().get("response", []):
            out[entry["domain"]] = {
                "page_rank": float(entry.get("page_rank_decimal") or 0),
                "rank": int(entry.get("rank")) if entry.get("rank") else None,
            }
        return out
    except Exception:
        return {}


# ============================================================================
# GitHub
# ============================================================================
def github_org(org_slug: str) -> dict[str, Any] | None:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    r = _get(f"https://api.github.com/orgs/{org_slug}", headers=headers)
    if not r:
        return None
    org = r.json()
    repos_r = _get(f"https://api.github.com/orgs/{org_slug}/repos?per_page=100&sort=updated", headers=headers)
    repos = repos_r.json() if repos_r else []

    cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
    langs: dict[str, int] = {}
    for repo in repos:
        if repo.get("language"):
            langs[repo["language"]] = langs.get(repo["language"], 0) + 1

    return {
        "name": org.get("name") or org.get("login"),
        "public_repos": org.get("public_repos", 0),
        "followers": org.get("followers", 0),
        "total_stars": sum(r.get("stargazers_count", 0) for r in repos),
        "total_forks": sum(r.get("forks_count", 0) for r in repos),
        "recent_active_repos": len([r for r in repos if (r.get("pushed_at") or "") > cutoff]),
        "top_languages": sorted(langs.items(), key=lambda x: -x[1])[:5],
        "created_at": org.get("created_at"),
    }


# ============================================================================
# Hacker News
# ============================================================================
def hn_mentions(query: str, months_back: int = 12) -> dict[str, Any]:
    since = int((datetime.utcnow() - timedelta(days=30 * months_back)).timestamp())
    r = _get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": query, "numericFilters": f"created_at_i>{since}", "hitsPerPage": 30},
    )
    if not r:
        return {"total": 0, "hits": []}
    data = r.json()
    return {
        "total": data.get("nbHits", 0),
        "hits": [
            {
                "title": h.get("title") or h.get("story_title") or "",
                "url": h.get("url") or "",
                "points": h.get("points"),
                "comments": h.get("num_comments"),
                "date": h.get("created_at"),
            }
            for h in data.get("hits", [])[:8]
        ],
    }


# ============================================================================
# Reddit
# ============================================================================
def reddit_mentions(query: str) -> dict[str, Any]:
    r = _get(f"https://www.reddit.com/search.json?q={quote_plus(query)}&sort=new&t=year&limit=30")
    if not r:
        return {"total": 0, "hits": []}
    try:
        children = r.json().get("data", {}).get("children", [])
        return {
            "total": len(children),
            "hits": [
                {
                    "title": c["data"].get("title", ""),
                    "subreddit": c["data"].get("subreddit", ""),
                    "score": c["data"].get("score"),
                    "url": f"https://reddit.com{c['data'].get('permalink', '')}",
                }
                for c in children[:8]
            ],
        }
    except Exception:
        return {"total": 0, "hits": []}


# ============================================================================
# GDELT
# ============================================================================
def gdelt_news(query: str, months_back: int = 6, country_filter: str | None = None) -> dict[str, Any]:
    q = f'"{query}"'
    if country_filter:
        q += f" sourcecountry:{country_filter.upper()}"
    r = _get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": q,
            "mode": "ArtList",
            "timespan": f"{months_back}months",
            "format": "json",
            "maxrecords": 75,
            "sort": "datedesc",
        },
    )
    if not r:
        return {"total": 0, "hits": []}
    try:
        articles = r.json().get("articles", [])
    except ValueError:
        return {"total": 0, "hits": []}
    return {
        "total": len(articles),
        "hits": [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("domain", ""),
                "date": a.get("seendate", ""),
                "language": a.get("language", ""),
            }
            for a in articles[:8]
        ],
    }


# ============================================================================
# Wayback Machine
# ============================================================================
def wayback_first_snapshot(domain: str) -> str | None:
    r = _get(
        "https://web.archive.org/cdx/search/cdx",
        params={"url": domain, "limit": 1, "output": "json", "fl": "timestamp", "from": "1995"},
    )
    if not r:
        return None
    try:
        rows = r.json()
        if len(rows) > 1:
            return rows[1][0]
    except (ValueError, IndexError):
        pass
    return None


# ============================================================================
# Serper.dev
# ============================================================================
def serper_search(query: str, num: int = 15, gl: str = "ar", hl: str = "es") -> list[dict]:
    api_key = os.getenv("SERPER_API_KEY", "")
    if not api_key:
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": num, "gl": gl, "hl": hl},
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            timeout=DEFAULT_TIMEOUT,
        )
        if r.status_code >= 400:
            return []
        return r.json().get("organic", [])
    except Exception:
        return []


# ============================================================================
# Tech stack (heurística)
# ============================================================================
TECH_SIGNATURES = {
    "WordPress": ["wp-content", "wp-includes", "wp-json"],
    "HubSpot": ["hs-scripts.com", "hubspot.com", "_hsq.push", "hs-fs.com"],
    "Drupal": ["Drupal.settings", "/sites/default/files"],
    "Webflow": ["webflow.js", "wf-domain"],
    "Next.js": ["__NEXT_DATA__", "/_next/static"],
    "React": ["react-dom", "data-reactroot"],
    "Google Tag Manager": ["googletagmanager.com/gtm"],
    "Pardot": ["pi.pardot.com"],
    "Marketo": ["marketo.com", "munchkin.js"],
    "Intercom": ["intercom.io", "intercomcdn.com"],
    "Drift": ["js.driftt.com"],
    "Tailwind CSS": ["cdn.tailwindcss"],
    "Bootstrap": ["bootstrap.min.css", "bootstrap.bundle"],
    "WP Rocket": ["wp-rocket"],
    "Elementor": ["elementor"],
    "Mailchimp": ["mailchimp.com", "list-manage.com"],
    "Hotjar": ["hotjar.com", "hjid"],
    "LinkedIn Insight": ["snap.licdn.com"],
    "Meta Pixel": ["connect.facebook.net", "fbevents.js"],
}


def detect_tech(url: str) -> list[str]:
    if not url.startswith("http"):
        url = f"https://{url}"
    r = _get(url)
    if not r:
        return []
    html = r.text.lower()
    headers = {k.lower(): v.lower() for k, v in r.headers.items()}

    detected = []
    for tech, patterns in TECH_SIGNATURES.items():
        if any(p.lower() in html for p in patterns):
            detected.append(tech)

    server = headers.get("server", "")
    if "cloudflare" in server or "cf-ray" in headers:
        detected.append("Cloudflare")
    if "nginx" in server:
        detected.append("Nginx")
    powered = headers.get("x-powered-by", "")
    if "php" in powered:
        detected.append("PHP")
    if "asp.net" in powered or "asp.net" in server:
        detected.append("ASP.NET")

    return sorted(set(detected))


# ============================================================================
# Blog / RSS
# ============================================================================
def discover_feed(url: str) -> str | None:
    if not url.startswith("http"):
        url = f"https://{url}"
    r = _get(url)
    if not r:
        return None
    m = re.search(
        r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
        r.text,
        re.IGNORECASE,
    )
    if m:
        return urljoin(url, m.group(1)) if m.group(1).startswith("/") else m.group(1)

    for cand in ["/feed", "/feed/", "/rss", "/blog/feed/", "/rss.xml"]:
        test = url.rstrip("/") + cand
        rr = _get(test)
        if rr and ("xml" in rr.headers.get("Content-Type", "").lower() or "<rss" in rr.text[:500].lower()):
            return test
    return None


def feed_summary(feed_url: str) -> dict[str, Any]:
    r = _get(feed_url)
    if not r:
        return {}
    try:
        import feedparser
    except ImportError:
        return {}

    parsed = feedparser.parse(r.content)
    cutoff = datetime.utcnow() - timedelta(days=90)
    last_90d, titles = 0, []
    for entry in parsed.entries[:50]:
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub and datetime(*pub[:6]) > cutoff:
            last_90d += 1
        titles.append(entry.get("title", ""))
    return {
        "total_entries_in_feed": len(parsed.entries),
        "posts_last_90d": last_90d,
        "recent_titles": titles[:8],
    }
