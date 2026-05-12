"""
Descubrimiento automático de competidores con foco en Argentina.

Estrategia:
1. Búsquedas en Google con `gl=ar`, `hl=es` y términos en español de AR.
2. Filtra dominios que NO son competidores: prensa, redes sociales,
   directorios, y específicamente medios argentinos (clarin, lanacion,
   infobae, ambito, iprofesional, etc.).
3. Scoring: cada dominio gana puntos cuando aparece en múltiples queries
   y/o en posiciones altas.
"""

from __future__ import annotations

import logging
from collections import Counter
from urllib.parse import urlparse

from . import apis

log = logging.getLogger(__name__)

# Dominios que NO son competidores: agregadores, prensa, redes, directorios.
NON_COMPETITOR_DOMAINS = {
    # Globales
    "g2.com", "capterra.com", "trustradius.com", "softwareadvice.com",
    "gartner.com", "forrester.com", "techcrunch.com", "wikipedia.org",
    "reddit.com", "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "youtube.com", "medium.com", "quora.com", "indeed.com", "glassdoor.com",
    "crunchbase.com", "owler.com", "zoominfo.com", "bloomberg.com",
    "github.com", "stackoverflow.com", "producthunt.com",
    "amazon.com", "microsoft.com", "google.com", "apple.com",
    # Medios y portales argentinos
    "clarin.com", "lanacion.com.ar", "infobae.com", "ambito.com",
    "iprofesional.com", "cronista.com", "pagina12.com.ar",
    "perfil.com", "tn.com.ar", "lacapital.com.ar", "telam.com.ar",
    "infotechnology.com", "iproup.com", "redusers.com",
    "noticiasargentinas.com", "minutouno.com",
    # España (por si filtra restos)
    "elpais.com", "expansion.com", "elmundo.es", "lavanguardia.com",
    "elconfidencial.com", "europapress.es", "computerworld.es",
    # Buscadores
    "bing.com", "duckduckgo.com", "yahoo.com",
}


def _domain_of(url: str) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = f"https://{url}"
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _is_competitor_candidate(domain: str, own_domain: str) -> bool:
    if not domain or domain == own_domain:
        return False
    if domain in NON_COMPETITOR_DOMAINS:
        return False
    if domain.endswith("." + own_domain):
        return False
    return True


def discover_from_search(
    company_name: str,
    own_domain: str,
    keywords: list[str],
    country: str = "ar",
    language: str = "es",
    max_candidates: int = 12,
) -> list[dict]:
    """Genera queries y agrega los dominios más mencionados."""
    queries = [
        f"alternativas a {company_name} Argentina",
        f"empresas similares a {company_name} Argentina",
        f"competidores de {company_name}",
    ]
    for kw in keywords:
        queries += [
            f"mejores empresas de {kw} Argentina",
            f"consultoras {kw} Buenos Aires",
            f"{kw} proveedores Argentina",
            f"top {kw} Argentina 2025",
        ]

    domain_scores: Counter[str] = Counter()
    domain_meta: dict[str, dict] = {}

    for q in queries:
        log.info("Buscando: %s", q)
        results = apis.serper_search(q, num=15, gl=country, hl=language)
        for pos, r in enumerate(results):
            d = _domain_of(r.get("link", ""))
            if not _is_competitor_candidate(d, own_domain):
                continue
            domain_scores[d] += max(1, 5 - pos // 3)
            if d not in domain_meta:
                domain_meta[d] = {
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                }

    return [
        {
            "domain": d,
            "score": score,
            "title": domain_meta[d]["title"],
            "snippet": domain_meta[d]["snippet"],
            "source": "search",
        }
        for d, score in domain_scores.most_common(max_candidates)
    ]


def discover_with_seed(seed_domains: list[str], own_domain: str) -> list[dict]:
    """Lista semilla manual: salteás el descubrimiento."""
    return [
        {
            "domain": _domain_of(d),
            "score": 1,
            "title": "",
            "snippet": "",
            "source": "seed",
        }
        for d in seed_domains
        if _is_competitor_candidate(_domain_of(d), own_domain)
    ]
