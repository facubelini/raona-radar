"""
Google Ads Transparency Center.

No tiene API oficial. La estrategia es:

1. DEEP-LINK (siempre funciona):
   Genera la URL pública del Transparency Center filtrada por país y dominio.
   El usuario hace clic y ve los anuncios del competidor en su navegador.

2. SCRAPING LIVIANO (best-effort, opcional):
   La página devuelve datos embebidos en `AF_initDataCallback`. Cuando funciona,
   podemos extraer el conteo aproximado y los nombres de las creatividades.
   Cuando no funciona (porque Google cambió el HTML, o porque hace falta
   render JS), devolvemos None y nos quedamos con el deep-link.

Sin auth, sin API key. Solo HTTP.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)


def deep_link(domain: str, region: str = "AR") -> str:
    """URL pública del Transparency Center para ese dominio en ese país."""
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    params = {"region": region.upper(), "domain": domain}
    return f"https://adstransparency.google.com/?{urlencode(params)}"


def deep_link_by_advertiser(advertiser_name: str, region: str = "AR") -> str:
    """Alternativa: buscar por nombre del anunciante."""
    params = {"region": region.upper(), "advertiser": advertiser_name}
    return f"https://adstransparency.google.com/?{urlencode(params)}"


def scrape_ad_count(domain: str, region: str = "AR") -> dict[str, Any]:
    """
    Best-effort: intenta extraer cuántos anuncios activos tiene el dominio.

    Devuelve:
        {
          "ads_visible": int | None,   # None = no se pudo determinar
          "verified_advertiser": bool | None,
          "deep_link": str
        }

    Si Google cambia el HTML o sirve solo JS, todos los campos quedan en None
    y queda el deep_link igual para que el usuario lo abra a mano.
    """
    out = {
        "ads_visible": None,
        "verified_advertiser": None,
        "deep_link": deep_link(domain, region),
    }

    try:
        r = requests.get(
            out["deep_link"],
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            },
        )
        if r.status_code >= 400:
            return out
        html = r.text

        # Patrón 1: anuncios totales declarados en el HTML inicial
        # Google a veces inserta "N creatividades" o "N ads"
        m = re.search(r'"(\d+)\s+(?:creatividades|ads|anuncios|creative ads)"', html, re.IGNORECASE)
        if m:
            out["ads_visible"] = int(m.group(1))

        # Verificación del anunciante
        if "verified advertiser" in html.lower() or "anunciante verificado" in html.lower():
            out["verified_advertiser"] = True

    except Exception as e:
        log.debug("Google Transparency scrape '%s' falló: %s", domain, e)

    return out
