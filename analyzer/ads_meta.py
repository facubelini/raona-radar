"""
Meta Ad Library — anuncios de Facebook e Instagram.

Dos modos:

1. DEEP-LINK (siempre funciona, sin auth):
   Genera la URL pública de la Ad Library filtrada por país y empresa.
   El usuario hace clic y ve los anuncios activos del competidor en su
   navegador. Es la forma robusta de operar sin pelearse con scraping.

2. GRAPH API (si está META_ACCESS_TOKEN):
   Consulta /ads_archive. Funciona oficialmente para anuncios
   políticos/sociales sin trámite. Para anuncios comerciales necesitás
   acceso al programa de investigación de Meta (gratis pero requiere
   verificación). Si lo tenés, podés extraer conteos, fechas y creatividades.

Docs Graph API: https://www.facebook.com/ads/library/api/
Programa de investigación: https://www.facebook.com/ads/library/research/
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)


def deep_link(company_name: str, country: str = "AR") -> str:
    """URL pública de Meta Ad Library para esa empresa en ese país."""
    params = {
        "active_status": "all",
        "ad_type": "all",
        "country": country.upper(),
        "q": company_name,
        "search_type": "keyword_unordered",
        "media_type": "all",
    }
    return f"https://www.facebook.com/ads/library/?{urlencode(params)}"


def query_ads_archive(
    search_terms: str,
    country: str = "AR",
    limit: int = 25,
    active_only: bool = True,
) -> dict[str, Any]:
    """
    Consulta /ads_archive. Solo funciona si META_ACCESS_TOKEN está seteado.

    Devuelve:
        {
          "total": int,
          "ads": [{ad_id, ad_creation_time, ad_creative_link_titles, ...}],
          "scope": "political_only" | "all_ads",
          "deep_link": str
        }
    """
    token = os.getenv("META_ACCESS_TOKEN", "")
    out = {
        "total": 0,
        "ads": [],
        "scope": None,
        "deep_link": deep_link(search_terms, country),
    }
    if not token:
        return out

    fields = ",".join([
        "id",
        "ad_creation_time",
        "ad_delivery_start_time",
        "ad_delivery_stop_time",
        "ad_creative_bodies",
        "ad_creative_link_titles",
        "page_name",
        "publisher_platforms",
        "ad_snapshot_url",
        "impressions",
        "spend",
    ])
    params = {
        "access_token": token,
        "search_terms": search_terms,
        "ad_reached_countries": f'["{country.upper()}"]',
        "ad_type": "ALL",
        "ad_active_status": "ACTIVE" if active_only else "ALL",
        "limit": limit,
        "fields": fields,
    }

    try:
        r = requests.get(
            "https://graph.facebook.com/v19.0/ads_archive",
            params=params,
            timeout=20,
        )
        if r.status_code >= 400:
            log.info("Meta ads_archive %s -> %s. Reintentando solo políticos.", search_terms, r.status_code)
            # Fallback al scope de políticos (no necesita verificación)
            params["ad_type"] = "POLITICAL_AND_ISSUE_ADS"
            r = requests.get("https://graph.facebook.com/v19.0/ads_archive", params=params, timeout=20)
            if r.status_code >= 400:
                return out
            out["scope"] = "political_only"
        else:
            out["scope"] = "all_ads"

        data = r.json().get("data", [])
        out["total"] = len(data)
        out["ads"] = [
            {
                "id": a.get("id"),
                "page_name": a.get("page_name"),
                "title": (a.get("ad_creative_link_titles") or [""])[0],
                "body": (a.get("ad_creative_bodies") or [""])[0][:200],
                "started": a.get("ad_delivery_start_time"),
                "ended": a.get("ad_delivery_stop_time"),
                "platforms": a.get("publisher_platforms", []),
                "snapshot_url": a.get("ad_snapshot_url"),
            }
            for a in data
        ]
    except Exception as e:
        log.warning("Meta ads_archive error para '%s': %s", search_terms, e)

    return out
