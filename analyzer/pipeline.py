"""
Pipeline principal.

Lee la configuración (seed_argentina.json por defecto), corre el descubrimiento
+ enriquecimiento, y escribe dos JSONs en webapp/data/:

- latest.json    -> el reporte más reciente (lo que carga el webapp por defecto)
- history/YYYY-MM-DD.json -> snapshot histórico para comparaciones temporales

Diseñado para ejecutarse en GitHub Actions cada semana.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import apis, discover, enrich
from . import ads_meta, ads_google


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _generate_insights(own: dict, competitors: list[dict]) -> list[str]:
    """Observaciones automáticas comparando 'own' con los demás."""
    out = []
    own_m = own.get("metrics", {})

    # SEO
    own_seo = (own_m.get("pagespeed") or {}).get("seo")
    if own_seo is not None:
        better = [c for c in competitors if (c.get("metrics", {}).get("pagespeed") or {}).get("seo", 0) > own_seo]
        if len(better) >= len(competitors) / 2:
            top = sorted(competitors, key=lambda c: -((c.get("metrics", {}).get("pagespeed") or {}).get("seo") or 0))[:2]
            out.append({
                "title": "Performance técnica por debajo del promedio",
                "body": f"Tu score SEO Lighthouse ({own_seo}) está por debajo de {len(better)} de {len(competitors)} competidores. Líderes: {', '.join(t['name'] for t in top)}.",
                "severity": "warning",
            })

    # Content velocity
    own_posts = (own_m.get("blog") or {}).get("posts_last_90d", 0)
    posts_ranked = sorted(
        [(c["name"], (c.get("metrics", {}).get("blog") or {}).get("posts_last_90d", 0)) for c in competitors],
        key=lambda x: -x[1],
    )
    if posts_ranked and posts_ranked[0][1] > max(own_posts, 1) * 2:
        out.append({
            "title": "Gap importante de velocidad de contenido",
            "body": f"{posts_ranked[0][0]} publicó {posts_ranked[0][1]} posts en 90 días vs tus {own_posts}. En 12 meses son ~{posts_ranked[0][1]*4 - own_posts*4} artículos indexables de diferencia.",
            "severity": "warning",
        })

    # Share of voice
    voice_sorted = sorted([own] + competitors, key=lambda c: -c.get("voice_total", 0))
    own_pos = next((i for i, c in enumerate(voice_sorted) if c.get("source") == "self"), -1)
    if own_pos > 2:
        leaders = ", ".join(c["name"] for c in voice_sorted[:3])
        out.append({
            "title": f"Share of voice bajo (posición #{own_pos + 1})",
            "body": f"Los tres líderes —{leaders}— concentran la conversación en HN + Reddit + prensa global.",
            "severity": "info",
        })

    # Anuncios activos
    own_ads_meta = (own_m.get("meta_ads") or {}).get("total", 0)
    competitors_with_ads = [
        c for c in competitors
        if (c.get("metrics", {}).get("meta_ads") or {}).get("total", 0) > 0
    ]
    if competitors_with_ads and own_ads_meta == 0:
        names = ", ".join(c["name"] for c in competitors_with_ads[:3])
        out.append({
            "title": "Competidores con anuncios activos en Meta",
            "body": f"{len(competitors_with_ads)} competidores tienen anuncios activos en Facebook/Instagram (ej: {names}). Vale revisar su mensaje y creatividades vía el link de la Ad Library.",
            "severity": "info",
        })

    # GitHub
    gh_active = [c for c in competitors if (c.get("metrics", {}).get("github") or {}).get("public_repos", 0) > 5]
    if not own_m.get("github") and gh_active:
        names = ", ".join(c["name"] for c in gh_active[:3])
        out.append({
            "title": "Falta presencia en GitHub",
            "body": f"{len(gh_active)} competidores tienen organización pública con repos activos ({names}). Para venta a CTOs, una org GitHub abre puertas.",
            "severity": "info",
        })

    return out[:6]


def run(config_path: Path, out_dir: Path) -> Path:
    log = logging.getLogger("pipeline")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    own_info = config["own_company"]
    competitors_seed = config["competitors"]
    country = own_info.get("country", "AR")

    # 1. Preparar lista de competidores con sus name_overrides
    log.info("Preparando lista de %d competidores", len(competitors_seed))
    candidates = [
        {
            "domain": c["domain"],
            "name": c["name"],
            "name_override": c["name"],
            "note": c.get("note", ""),
            "source": "seed",
            "score": 1,
            "title": "",
            "snippet": "",
        }
        for c in competitors_seed
    ]

    # 2. Enriquecer competidores
    log.info("Enriqueciendo competidores con todas las fuentes...")
    enriched = enrich.enrich_all(candidates, country=country)

    # 3. Enriquecer la propia empresa
    log.info("Enriqueciendo %s...", own_info["domain"])
    own = enrich.enrich_own_company(own_info["domain"], own_info["name"], country=country)

    # 4. OpenPageRank en batch
    all_domains = [own_info["domain"]] + [c["domain"] for c in enriched]
    opr = apis.open_page_rank(all_domains)
    if opr:
        own["metrics"]["pagerank"] = opr.get(own_info["domain"])
        for c in enriched:
            c["metrics"]["pagerank"] = opr.get(c["domain"])

    # 5. Anuncios — agregar deep-links siempre
    for c in [own] + enriched:
        m = c["metrics"]
        if not m.get("meta_ads"):
            m["meta_ads"] = {"total": 0, "ads": [], "deep_link": ads_meta.deep_link(c["name"], country=country)}
        if not m.get("google_ads"):
            m["google_ads"] = {"ads_visible": None, "deep_link": ads_google.deep_link(c["domain"], region=country)}

    # 6. Share of voice
    all_companies = [own] + enriched
    enrich.score_share_of_voice(all_companies)

    # 7. Insights
    insights = _generate_insights(own, enriched)

    # 8. Volcar JSON
    out_dir.mkdir(parents=True, exist_ok=True)
    history_dir = out_dir / "history"
    history_dir.mkdir(exist_ok=True)

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scope_label": own_info.get("scope_label", "Argentina"),
        "country": country,
        "own": own,
        "competitors": enriched,
        "insights": insights,
    }

    latest_path = out_dir / "latest.json"
    latest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    # Snapshot histórico con fecha
    snap_path = history_dir / f"{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    snap_path.write_text(latest_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Index de la carpeta history (para que el webapp sepa qué snapshots existen)
    history_files = sorted([p.name for p in history_dir.glob("*.json")])
    (history_dir / "index.json").write_text(
        json.dumps({"snapshots": history_files}, indent=2),
        encoding="utf-8",
    )

    log.info("Reporte JSON: %s (%.1f KB)", latest_path, latest_path.stat().st_size / 1024)
    log.info("Snapshot:    %s", snap_path)
    return latest_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pipeline de análisis competitivo.")
    p.add_argument("--config", type=Path, default=Path("analyzer/seed_argentina.json"))
    p.add_argument("--out-dir", type=Path, default=Path("webapp/data"))
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    setup_logging(args.verbose)
    run(args.config, args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
