# Raona Radar

Webapp de inteligencia competitiva auto-actualizable, alojada gratis en GitHub.

Cada lunes a las 5 AM (hora Argentina), una GitHub Action corre el analizador, genera métricas frescas sobre los competidores de Raona en Argentina, y republica el sitio en GitHub Pages. Sin servidor, sin costo, sin mantenimiento.

## Qué ves cuando entrás

Cinco vistas:

1. **Dashboard** — KPIs propios, matriz competitiva ordenable, gráficos de share of voice y velocidad de contenido.
2. **Competidores** — Tarjeta por jugador con scores de Lighthouse, autoridad de dominio, tech stack. Click → ficha completa.
3. **Anuncios** — Acceso directo a Meta Ad Library y Google Ads Transparency Center filtrado por Argentina, por competidor. Si configurás el token de Meta, se llena el conteo automáticamente.
4. **Insights** — Observaciones generadas automáticamente: gaps de SEO, de contenido, de presencia en GitHub, etc.
5. **Histórico** — Lista de snapshots semanales para detectar qué cambió de una corrida a otra.

## Stack

- **Analyzer** (Python): orquesta APIs gratuitas, genera `webapp/data/latest.json`.
- **Webapp** (HTML + vanilla JS): carga el JSON y renderiza las vistas. Cero build step.
- **CI/CD** (GitHub Actions): corre la pipeline semanalmente, commitea el JSON, deploya a Pages.

## Fuentes de datos

| Dimensión | API | Necesita key | Costo |
|---|---|---|---|
| Lighthouse (SEO, Perf, A11y, BP) | Google PageSpeed Insights | opcional | gratis |
| Autoridad de dominio | OpenPageRank | sí (registro instantáneo) | gratis |
| Antigüedad digital | Wayback CDX | no | gratis |
| Stack tecnológico | Heurística HTML/headers | no | — |
| Velocidad de contenido | RSS/Atom del blog | no | — |
| Presencia open source | GitHub REST | sí (token público) | gratis |
| Menciones en HN | Algolia HN Search | no | gratis |
| Menciones en Reddit | Reddit JSON endpoint | no | gratis |
| Menciones en prensa | GDELT DOC API | no | gratis |
| Descubrimiento auto | Serper.dev | sí | 2.500/mes gratis |
| Anuncios Meta | Ad Library deep-link | no | gratis |
| Anuncios Meta (conteo auto) | Graph /ads_archive | sí | gratis |
| Anuncios Google | Transparency deep-link | no | gratis |

Costo total con todas las APIs: **0 USD/mes** en uso semanal normal.

## Deploy en 6 pasos

### 1. Crear el repo

```bash
# En GitHub, creá un repo vacío (puede ser público o privado)
git clone https://github.com/TU_USUARIO/raona-radar.git
cd raona-radar
# Copiá todo el contenido de este zip
```

### 2. Habilitar GitHub Pages

En el repo → **Settings → Pages**:
- Source: **GitHub Actions**
- Guardá.

### 3. Cargar los secrets

En el repo → **Settings → Secrets and variables → Actions → New repository secret**.
Agregá:

| Secret | Valor | Cómo obtenerlo |
|---|---|---|
| `SERPER_API_KEY` | tu key | https://serper.dev/ → Sign up → Copiar API key |
| `PAGESPEED_API_KEY` | tu key | https://console.cloud.google.com/ → APIs → habilitar "PageSpeed Insights API" → Credentials |
| `OPENPAGERANK_API_KEY` | tu key | https://www.domcop.com/openpagerank/auth/signup |
| `META_ACCESS_TOKEN` | (opcional) | https://developers.facebook.com/ → tu app → Tools → Graph API Explorer |

`GITHUB_TOKEN` se inyecta solo (no hace falta crearlo).

### 4. Ajustar la lista de competidores

Editá `analyzer/seed_argentina.json`. La estructura es obvia:

```json
{
  "own_company": { "name": "Raona", "domain": "raona.com", "country": "AR" },
  "keywords": ["intranet corporativa", "digital workplace"],
  "competitors": [
    { "domain": "baufest.com", "name": "Baufest", "note": "..." }
  ]
}
```

### 5. Primera corrida

Andá a **Actions → Weekly competitive analysis → Run workflow**. Hacé clic. En ~5 minutos:

- Corre el analyzer.
- Commitea `webapp/data/latest.json`.
- Deploya el webapp a Pages.

La URL final es `https://TU_USUARIO.github.io/raona-radar/`.

### 6. (Opcional) Correrlo en local

Para testear cambios sin esperar el lunes:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # editá .env con tus keys
python -m analyzer.pipeline --verbose
# servir webapp en localhost
cd webapp && python -m http.server 8080
# abrir http://localhost:8080
```

## Personalizar el alcance

La pipeline está cableada a Argentina (`country: "AR"`). Para sumar Colombia, México u otros mercados de Raona:

1. Duplicá `seed_argentina.json` → `seed_colombia.json`, ajustá `country` y `competitors`.
2. En `weekly-update.yml`, agregá un step que corra `python -m analyzer.pipeline --config analyzer/seed_colombia.json --out-dir webapp/data/co`.
3. Adaptá el webapp para tener un selector de país arriba (sería un cambio chico en `app.js`).

## Sobre los anuncios — qué esperar realmente

**Meta Ad Library**: la API oficial (`/ads_archive`) cubre 100% de los anuncios políticos/sociales sin trámite, pero los anuncios comerciales requieren acceso al [programa de investigación](https://www.facebook.com/ads/library/research/) (gratis, formulario corto, ~1-3 semanas de espera). Sin ese acceso, lo que sí funciona siempre es el **deep-link**: cuando hacés click en "Abrir Ad Library" en la vista de Anuncios, te lleva a la búsqueda pública filtrada por país + empresa y ves todos los creativos activos.

**Google Ads Transparency Center**: no tiene API. La estrategia es la misma — deep-link a `adstransparency.google.com` filtrado por dominio + país. La función `scrape_ad_count()` intenta extraer el conteo del HTML inicial pero Google sirve mucho con JavaScript, así que es **best-effort**: a veces hay número, a veces no, pero el deep-link funciona siempre.

Si querés conteos 100% automatizados, los caminos son:
- Pedir acceso al programa de investigación de Meta (gratis).
- Usar Playwright para scrapear Transparency Center con un navegador real (sumar como step opcional en la action).
- Pagar un servicio tipo PowerAdSpy o AdClarity.

## Limitaciones honestas

- **Tráfico real estimado**: ninguna fuente gratuita lo da bien. Lo que dejé como proxy es la suma de menciones (HN + Reddit + GDELT). Para tráfico real necesitás Similarweb o similar.
- **Keywords por las que rankea cada competidor**: requiere Ahrefs/SEMrush/SerpApi en escala.
- **Detección de tech stack**: heurística simple, ~20 tecnologías. Para profundidad real, instalar `python-Wappalyzer` y reemplazar `apis.detect_tech()`.
- **HN y Reddit subestiman empresas locales argentinas** porque la conversación está en inglés. GDELT compensa parcialmente. El SOV cobra más sentido relativo entre competidores que en valor absoluto.

## Cómo extenderlo

La arquitectura es modular a propósito:

```
analyzer/
├── apis.py          ← wrappers de fuentes externas; agregar API = agregar función
├── ads_meta.py      ← Meta Ad Library (deep-link + Graph)
├── ads_google.py    ← Google Ads Transparency
├── discover.py      ← descubrimiento automático
├── enrich.py        ← orquesta el enriquecimiento de cada competidor
└── pipeline.py      ← entry point + insights generator

webapp/
├── index.html
├── styles.css
├── app.js           ← lógica de SPA, una función por vista
└── data/
    ├── latest.json
    └── history/
```

Próximos pasos naturales:

- **Diff entre corridas**: leer la última corrida y la anterior, mostrar deltas con flechas ↑↓ en cada métrica.
- **Análisis del messaging**: meter las homes en Claude API y extraer las propuestas de valor.
- **Alertas por email**: si un competidor cambia significativamente (ej: publica 20 posts en una semana), mandar email al equipo.
- **Multi-país**: como mencioné arriba.

## Licencia

MIT. Hacé lo que quieras.
