/* ============================================================
   Raona Radar — SPA logic
   ============================================================ */

const state = {
  data: null,
  view: 'dashboard',
  sortKey: 'voice_total',
  sortDir: 'desc',
};

// ============================================================
// Bootstrap
// ============================================================
async function init() {
  try {
    const res = await fetch('data/latest.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
  } catch (e) {
    document.getElementById('main').innerHTML = `
      <div class="view-head">
        <div class="eyebrow">Error</div>
        <h1>No se pudieron <em>cargar los datos</em></h1>
        <p class="lead">Verificá que <code>webapp/data/latest.json</code> exista. Si recién clonaste el repo, primero corré la pipeline: <code>python -m analyzer.pipeline</code></p>
      </div>`;
    return;
  }

  renderMeta();
  route();
  window.addEventListener('hashchange', route);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-bg').addEventListener('click', (e) => {
    if (e.target.id === 'modal-bg') closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
}

function renderMeta() {
  const d = new Date(state.data.generated_at);
  document.getElementById('meta-date').textContent =
    d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
  document.getElementById('meta-scope').textContent = state.data.scope_label || '—';
  document.getElementById('meta-count').textContent = state.data.competitors.length;
}

function route() {
  const hash = location.hash.replace('#/', '') || 'dashboard';
  state.view = hash;
  document.querySelectorAll('.nav a').forEach(a => {
    a.classList.toggle('active', a.dataset.view === hash);
  });
  render();
}

function render() {
  const main = document.getElementById('main');
  switch (state.view) {
    case 'dashboard':    main.innerHTML = renderDashboard(); attachMatrixHandlers(); break;
    case 'competidores': main.innerHTML = renderCompetidores(); attachCardHandlers(); break;
    case 'anuncios':     main.innerHTML = renderAnuncios(); break;
    case 'insights':     main.innerHTML = renderInsights(); break;
    case 'historico':    renderHistorico(main); break;
    default:             main.innerHTML = renderDashboard(); attachMatrixHandlers();
  }
  window.scrollTo(0, 0);
}

// ============================================================
// Helpers
// ============================================================
const fmt = {
  num: (n) => (n === null || n === undefined ? '—' : n),
  score: (n) => {
    if (n === null || n === undefined) return '—';
    const cls = n >= 90 ? 'good' : n >= 70 ? 'ok' : 'bad';
    return `<span class="score-pill"><span class="dot ${cls}"></span>${n}</span>`;
  },
  perf: (n) => {
    if (n === null || n === undefined) return '—';
    const cls = n >= 80 ? 'good' : n >= 50 ? 'ok' : 'bad';
    return `<span class="score-pill"><span class="dot ${cls}"></span>${n}</span>`;
  },
};

function getMetric(c, ...path) {
  let v = c;
  for (const k of path) {
    if (v === null || v === undefined) return null;
    v = v[k];
  }
  return v ?? null;
}

function rankOwn(field, descending = true) {
  const all = [state.data.own, ...state.data.competitors];
  all.sort((a, b) => {
    const va = field(a) || 0;
    const vb = field(b) || 0;
    return descending ? vb - va : va - vb;
  });
  return all.findIndex(c => c.source === 'self') + 1;
}

// ============================================================
// View: Dashboard
// ============================================================
function renderDashboard() {
  const { own, competitors } = state.data;
  const all = [own, ...competitors];

  const ownSeoRank = rankOwn(c => getMetric(c, 'metrics', 'pagespeed', 'seo'));
  const ownContentRank = rankOwn(c => getMetric(c, 'metrics', 'blog', 'posts_last_90d'));

  const maxVoice = Math.max(...all.map(c => c.voice_total || 0), 1);
  const maxPosts = Math.max(...all.map(c => getMetric(c, 'metrics', 'blog', 'posts_last_90d') || 0), 1);

  return `
    <div class="view-head">
      <div class="eyebrow">Dashboard · ${state.data.scope_label}</div>
      <h1>${own.name}<br><em>vs. el mercado</em></h1>
      <p class="lead">Posicionamiento digital comparado: SEO técnico, voz en medios, velocidad de contenido y anuncios activos. Click en cualquier fila para ver el detalle de la compañía.</p>
    </div>

    <div class="tiles">
      <div class="tile">
        <div class="label">Posición SEO</div>
        <div class="value">#${ownSeoRank}<span class="unit">/ ${all.length}</span></div>
        <div class="note">Score: ${getMetric(own, 'metrics', 'pagespeed', 'seo') ?? '—'}</div>
      </div>
      <div class="tile">
        <div class="label">Velocidad contenido</div>
        <div class="value">#${ownContentRank}<span class="unit">/ ${all.length}</span></div>
        <div class="note">${getMetric(own, 'metrics', 'blog', 'posts_last_90d') ?? 0} posts/90d</div>
      </div>
      <div class="tile">
        <div class="label">Share of voice</div>
        <div class="value">${own.voice_share_pct || 0}<span class="unit">%</span></div>
        <div class="note">${own.voice_total || 0} menciones</div>
      </div>
      <div class="tile">
        <div class="label">Antigüedad digital</div>
        <div class="value">${getMetric(own, 'metrics', 'age_years') ?? '—'}<span class="unit">años</span></div>
        <div class="note">Primer Wayback snapshot</div>
      </div>
    </div>

    <div class="sect">
      <span class="num">01</span>
      <h2>Matriz competitiva</h2>
      <span class="desc">Click en una fila para abrir su ficha. Click en una columna para ordenar.</span>
    </div>
    ${renderMatrix(all)}

    <div class="sect">
      <span class="num">02</span>
      <h2>Share of voice</h2>
      <span class="desc">Menciones agregadas: Hacker News + Reddit + prensa global (GDELT) · últimos 12 meses.</span>
    </div>
    ${renderBars(all, 'voice_total', maxVoice, (c) => c.voice_total || 0)}

    <div class="sect">
      <span class="num">03</span>
      <h2>Velocidad de contenido</h2>
      <span class="desc">Posts en blog corporativo en los últimos 90 días. Multiplicalo por 4 para ver la diferencia anual indexable.</span>
    </div>
    ${renderBars(all, 'posts', maxPosts, (c) => getMetric(c, 'metrics', 'blog', 'posts_last_90d') || 0, (v) => `${v} posts`)}
  `;
}

function renderMatrix(all) {
  const sorted = sortRows(all, state.sortKey, state.sortDir);
  const head = (key, label) => {
    const cls = state.sortKey === key ? `sort-${state.sortDir}` : '';
    return `<th data-sort="${key}" class="${cls}">${label}</th>`;
  };

  return `
    <div class="matrix-wrap">
    <table class="matrix">
      <thead><tr>
        ${head('name', 'Compañía')}
        ${head('seo', 'SEO')}
        ${head('perf', 'Perf')}
        ${head('pagerank', 'Autoridad')}
        ${head('posts', 'Posts/90d')}
        ${head('voice_total', 'Menciones')}
        ${head('age', 'Antigüedad')}
        ${head('meta_ads', 'Ads Meta')}
      </tr></thead>
      <tbody>
        ${sorted.map(c => {
          const ownStack = new Set(getMetric(state.data.own, 'metrics', 'tech_stack') || []);
          const stack = getMetric(c, 'metrics', 'tech_stack') || [];
          return `
            <tr class="${c.source === 'self' ? 'own' : ''}" data-domain="${c.domain}">
              <td>
                <div class="company-cell">
                  ${c.source === 'self' ? '<span class="own-badge">▸ TÚ</span>' : ''}${c.name}
                  <span class="domain">${c.domain}</span>
                </div>
              </td>
              <td class="num">${fmt.score(getMetric(c, 'metrics', 'pagespeed', 'seo'))}</td>
              <td class="num">${fmt.perf(getMetric(c, 'metrics', 'pagespeed', 'performance'))}</td>
              <td class="num">${getMetric(c, 'metrics', 'pagerank', 'page_rank') ?? '—'}</td>
              <td class="num">${getMetric(c, 'metrics', 'blog', 'posts_last_90d') ?? 0}</td>
              <td class="num">${c.voice_total || 0}</td>
              <td class="num">${getMetric(c, 'metrics', 'age_years') ?? '—'} a.</td>
              <td class="num">${getMetric(c, 'metrics', 'meta_ads', 'total') || 0}</td>
            </tr>
          `;
        }).join('')}
      </tbody>
    </table>
    </div>
  `;
}

function sortRows(rows, key, dir) {
  const mul = dir === 'asc' ? 1 : -1;
  const getter = {
    name: c => c.name?.toLowerCase() || '',
    seo: c => getMetric(c, 'metrics', 'pagespeed', 'seo') || 0,
    perf: c => getMetric(c, 'metrics', 'pagespeed', 'performance') || 0,
    pagerank: c => getMetric(c, 'metrics', 'pagerank', 'page_rank') || 0,
    posts: c => getMetric(c, 'metrics', 'blog', 'posts_last_90d') || 0,
    voice_total: c => c.voice_total || 0,
    age: c => getMetric(c, 'metrics', 'age_years') || 0,
    meta_ads: c => getMetric(c, 'metrics', 'meta_ads', 'total') || 0,
  }[key] || (c => c.name);

  return [...rows].sort((a, b) => {
    const va = getter(a), vb = getter(b);
    if (va < vb) return -1 * mul;
    if (va > vb) return 1 * mul;
    return 0;
  });
}

function renderBars(all, key, max, getter, labelFn) {
  const sorted = [...all].sort((a, b) => getter(b) - getter(a));
  return `
    <div class="barchart">
      ${sorted.map(c => {
        const v = getter(c);
        const pct = (v / max) * 100;
        return `
          <div class="bar-row ${c.source === 'self' ? 'own' : ''}">
            <div class="name">${c.source === 'self' ? '▸ ' : ''}${c.name}</div>
            <div class="bar-track"><div class="bar-fill" style="width: ${pct}%"></div></div>
            <div class="val">${labelFn ? labelFn(v) : v}</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function attachMatrixHandlers() {
  document.querySelectorAll('.matrix th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortKey = key;
        state.sortDir = key === 'name' ? 'asc' : 'desc';
      }
      render();
    });
  });
  document.querySelectorAll('.matrix tbody tr').forEach(tr => {
    tr.addEventListener('click', () => openDetail(tr.dataset.domain));
  });
}

// ============================================================
// View: Competidores
// ============================================================
function renderCompetidores() {
  const { own, competitors } = state.data;
  const all = [own, ...competitors];
  const ownStack = new Set(getMetric(own, 'metrics', 'tech_stack') || []);

  return `
    <div class="view-head">
      <div class="eyebrow">Catálogo · 02</div>
      <h1>Compañías <em>analizadas</em></h1>
      <p class="lead">Una tarjeta por jugador. Click en cualquiera para ver el perfil completo.</p>
    </div>

    <div class="cards">
      ${all.map(c => renderCard(c, ownStack)).join('')}
    </div>
  `;
}

function renderCard(c, ownStack) {
  const ps = getMetric(c, 'metrics', 'pagespeed') || {};
  const cls = (n) => n >= 90 ? 'good' : n >= 70 ? 'ok' : 'bad';
  const clsP = (n) => n >= 80 ? 'good' : n >= 50 ? 'ok' : 'bad';
  const stack = getMetric(c, 'metrics', 'tech_stack') || [];

  return `
    <div class="card ${c.source === 'self' ? 'own' : ''}" data-domain="${c.domain}">
      <h3>${c.source === 'self' ? '▸ ' : ''}${c.name}</h3>
      <span class="dom">${c.domain}</span>

      ${ps.performance !== undefined ? `
      <div class="lh-scores">
        <div class="ls ${clsP(ps.performance)}"><div class="n">${ps.performance ?? '—'}</div><div class="l">Perf</div></div>
        <div class="ls ${cls(ps.seo)}"><div class="n">${ps.seo ?? '—'}</div><div class="l">SEO</div></div>
        <div class="ls ${cls(ps.accessibility)}"><div class="n">${ps.accessibility ?? '—'}</div><div class="l">A11y</div></div>
        <div class="ls ${cls(ps.best_practices)}"><div class="n">${ps.best_practices ?? '—'}</div><div class="l">BP</div></div>
      </div>` : ''}

      <div class="stat-grid">
        <span class="k">Antigüedad</span><span class="v right">${getMetric(c, 'metrics', 'age_years') ?? '—'} a.</span>
        <span class="k">Autoridad</span><span class="v right">${getMetric(c, 'metrics', 'pagerank', 'page_rank') ?? '—'}</span>
        <span class="k">Posts 90d</span><span class="v right">${getMetric(c, 'metrics', 'blog', 'posts_last_90d') ?? 0}</span>
        <span class="k">Menciones</span><span class="v right">${c.voice_total || 0}</span>
        <span class="k">Ads Meta</span><span class="v right">${getMetric(c, 'metrics', 'meta_ads', 'total') || 0}</span>
        <span class="k">GitHub repos</span><span class="v right">${getMetric(c, 'metrics', 'github', 'public_repos') ?? '—'}</span>
      </div>

      <div class="chips">
        ${stack.length === 0 ? '<span class="chip muted">— sin datos —</span>' :
          stack.slice(0, 8).map(t =>
            `<span class="chip ${ownStack.has(t) && c.source !== 'self' ? 'match' : ''}">${t}</span>`
          ).join('')}
      </div>
    </div>
  `;
}

function attachCardHandlers() {
  document.querySelectorAll('.card').forEach(card => {
    card.addEventListener('click', () => openDetail(card.dataset.domain));
  });
}

// ============================================================
// View: Anuncios
// ============================================================
function renderAnuncios() {
  const { own, competitors } = state.data;
  const all = [own, ...competitors];

  return `
    <div class="view-head">
      <div class="eyebrow">Inteligencia publicitaria · 03</div>
      <h1>Anuncios <em>activos</em></h1>
      <p class="lead">Acceso directo a Meta Ad Library (Facebook + Instagram) y Google Ads Transparency Center filtrado por Argentina, por compañía. Si configuraste el token de Meta, vas a ver también el conteo automatizado.</p>
    </div>

    <table class="ads-table">
      <thead>
        <tr>
          <th>Compañía</th>
          <th>Meta (Facebook + IG)</th>
          <th>Google Ads</th>
        </tr>
      </thead>
      <tbody>
        ${all.map(c => {
          const meta = getMetric(c, 'metrics', 'meta_ads') || {};
          const google = getMetric(c, 'metrics', 'google_ads') || {};
          const metaCount = meta.total || 0;
          return `
            <tr class="${c.source === 'self' ? 'own' : ''}">
              <td>
                <div class="company-cell">
                  ${c.source === 'self' ? '<span class="own-badge">▸ TÚ</span>' : ''}${c.name}
                  <span class="domain">${c.domain}</span>
                </div>
              </td>
              <td>
                <span class="ads-count ${metaCount > 0 ? 'has' : ''}">${metaCount}</span>
                ${meta.scope === 'political_only' ? '<span class="chip">solo políticos</span>' : ''}
                <a class="btn-ad meta" href="${meta.deep_link}" target="_blank" rel="noopener">
                  Abrir Ad Library
                </a>
              </td>
              <td>
                ${google.ads_visible !== null && google.ads_visible !== undefined
                  ? `<span class="ads-count ${google.ads_visible > 0 ? 'has' : ''}">${google.ads_visible}</span>`
                  : ''}
                <a class="btn-ad google" href="${google.deep_link}" target="_blank" rel="noopener">
                  Abrir Transparency
                </a>
              </td>
            </tr>
          `;
        }).join('')}
      </tbody>
    </table>

    <div style="margin-top:32px;padding:20px;background:var(--paper-2);border:1px solid var(--line);font-size:13px;color:var(--ink-2);">
      <strong style="font-family:'Geist Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:var(--ink);">Nota</strong><br>
      Por defecto, las dos plataformas se consultan vía deep-link (lo abrís y ves los anuncios en tu navegador). Si configurás <code>META_ACCESS_TOKEN</code> en los secrets del repo, el conteo de Meta se llena automáticamente.
      Google Ads Transparency no tiene API oficial, así que el conteo automático es best-effort.
    </div>
  `;
}

// ============================================================
// View: Insights
// ============================================================
function renderInsights() {
  const ins = state.data.insights || [];
  return `
    <div class="view-head">
      <div class="eyebrow">Lecturas estratégicas · 04</div>
      <h1>Qué dice <em>la data</em></h1>
      <p class="lead">Observaciones automáticas generadas comparando ${state.data.own.name} contra los competidores. Una lista corta de cosas que probablemente quieras discutir en marketing.</p>
    </div>

    ${ins.length === 0 ? `
      <div class="history-empty">No hay insights todavía. La pipeline los genera en base a gaps detectados.</div>
    ` : ins.map((it, i) => `
      <div class="insight-card severity-${it.severity || 'info'}">
        <div class="num">${String(i + 1).padStart(2, '0')}</div>
        <div>
          <h3>${it.title}</h3>
          <p>${it.body}</p>
        </div>
      </div>
    `).join('')}
  `;
}

// ============================================================
// View: Histórico
// ============================================================
async function renderHistorico(main) {
  main.innerHTML = `
    <div class="view-head">
      <div class="eyebrow">Snapshots · 05</div>
      <h1>Histórico de <em>corridas</em></h1>
      <p class="lead">Cada ejecución de la pipeline guarda un snapshot. Útil para detectar cambios: que un competidor publicó 20 posts de golpe, lanzó una campaña en Meta, o rediseñó su home.</p>
    </div>
    <div class="loading"><div class="spinner"></div><span>Buscando snapshots...</span></div>
  `;

  try {
    const res = await fetch('data/history/index.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error('no index');
    const data = await res.json();
    const snaps = (data.snapshots || []).filter(s => s !== 'index.json').reverse();

    main.querySelector('.loading').remove();
    if (snaps.length === 0) {
      main.insertAdjacentHTML('beforeend', `
        <div class="history-empty">Todavía no hay snapshots históricos. La pipeline los genera en cada corrida.</div>
      `);
      return;
    }

    main.insertAdjacentHTML('beforeend', `
      <div class="history-list">
        ${snaps.map(s => {
          const date = s.replace('.json', '');
          return `
            <div class="history-row">
              <span>${date}</span>
              <a class="btn-ad" href="data/history/${s}" target="_blank">Ver JSON</a>
            </div>
          `;
        }).join('')}
      </div>
    `);
  } catch (e) {
    main.querySelector('.loading').remove();
    main.insertAdjacentHTML('beforeend', `
      <div class="history-empty">No se encontró índice de snapshots. Corré la pipeline al menos una vez.</div>
    `);
  }
}

// ============================================================
// Modal: detalle por competidor
// ============================================================
function openDetail(domain) {
  const all = [state.data.own, ...state.data.competitors];
  const c = all.find(x => x.domain === domain);
  if (!c) return;

  const ps = getMetric(c, 'metrics', 'pagespeed') || {};
  const blog = getMetric(c, 'metrics', 'blog') || {};
  const gh = getMetric(c, 'metrics', 'github') || {};
  const hn = getMetric(c, 'metrics', 'hn') || {};
  const reddit = getMetric(c, 'metrics', 'reddit') || {};
  const gdelt = getMetric(c, 'metrics', 'gdelt') || {};
  const metaAds = getMetric(c, 'metrics', 'meta_ads') || {};
  const googleAds = getMetric(c, 'metrics', 'google_ads') || {};
  const tech = getMetric(c, 'metrics', 'tech_stack') || [];
  const ownStack = new Set(getMetric(state.data.own, 'metrics', 'tech_stack') || []);

  const cls = (n) => n >= 90 ? 'good' : n >= 70 ? 'ok' : 'bad';
  const clsP = (n) => n >= 80 ? 'good' : n >= 50 ? 'ok' : 'bad';

  document.getElementById('modal-content').innerHTML = `
    <h2>${c.source === 'self' ? '▸ ' : ''}${c.name}</h2>
    <span class="dom-big"><a href="${c.url || 'https://' + c.domain}" target="_blank">${c.domain} ↗</a></span>

    ${ps.performance !== undefined ? `
    <div class="modal-section">
      <h4>Lighthouse · Mobile</h4>
      <div class="lh-scores">
        <div class="ls ${clsP(ps.performance)}"><div class="n">${ps.performance ?? '—'}</div><div class="l">Performance</div></div>
        <div class="ls ${cls(ps.seo)}"><div class="n">${ps.seo ?? '—'}</div><div class="l">SEO</div></div>
        <div class="ls ${cls(ps.accessibility)}"><div class="n">${ps.accessibility ?? '—'}</div><div class="l">A11y</div></div>
        <div class="ls ${cls(ps.best_practices)}"><div class="n">${ps.best_practices ?? '—'}</div><div class="l">Best Practices</div></div>
      </div>
    </div>` : ''}

    <div class="modal-section">
      <h4>Métricas clave</h4>
      <div class="modal-row"><span class="k">Antigüedad digital</span><span class="v">${getMetric(c, 'metrics', 'age_years') ?? '—'} años</span></div>
      <div class="modal-row"><span class="k">Autoridad OpenPageRank</span><span class="v">${getMetric(c, 'metrics', 'pagerank', 'page_rank') ?? '—'} / 10</span></div>
      <div class="modal-row"><span class="k">Posts blog últimos 90d</span><span class="v">${blog.posts_last_90d ?? 0}</span></div>
      ${blog.feed_url ? `<div class="modal-row"><span class="k">Feed RSS</span><span class="v"><a href="${blog.feed_url}" target="_blank">abrir ↗</a></span></div>` : ''}
    </div>

    <div class="modal-section">
      <h4>Share of voice (últimos 6-12 meses)</h4>
      <div class="modal-row"><span class="k">Hacker News</span><span class="v">${hn.total || 0} menciones</span></div>
      <div class="modal-row"><span class="k">Reddit</span><span class="v">${reddit.total || 0} menciones</span></div>
      <div class="modal-row"><span class="k">Prensa global (GDELT)</span><span class="v">${gdelt.total || 0} menciones</span></div>
      <div class="modal-row"><span class="k">Total</span><span class="v">${c.voice_total || 0} (${c.voice_share_pct || 0}% del total)</span></div>
    </div>

    <div class="modal-section">
      <h4>Anuncios activos</h4>
      <div class="modal-row"><span class="k">Meta (Facebook + IG)</span><span class="v">${metaAds.total || 0} anuncios · <a href="${metaAds.deep_link}" target="_blank">Ad Library ↗</a></span></div>
      <div class="modal-row"><span class="k">Google Ads</span><span class="v">${googleAds.ads_visible ?? '—'} · <a href="${googleAds.deep_link}" target="_blank">Transparency ↗</a></span></div>
    </div>

    ${gh && gh.public_repos ? `
    <div class="modal-section">
      <h4>GitHub · ${gh.name || ''}</h4>
      <div class="modal-row"><span class="k">Repos públicos</span><span class="v">${gh.public_repos}</span></div>
      <div class="modal-row"><span class="k">Estrellas totales</span><span class="v">★ ${gh.total_stars}</span></div>
      <div class="modal-row"><span class="k">Repos activos (90d)</span><span class="v">${gh.recent_active_repos}</span></div>
      ${gh.top_languages && gh.top_languages.length ? `<div class="modal-row"><span class="k">Top lenguajes</span><span class="v">${gh.top_languages.map(l => l[0] || l).join(', ')}</span></div>` : ''}
    </div>` : ''}

    <div class="modal-section">
      <h4>Stack tecnológico detectado</h4>
      <div class="chips">
        ${tech.length === 0 ? '<span class="muted">— sin datos —</span>' :
          tech.map(t => `<span class="chip ${ownStack.has(t) && c.source !== 'self' ? 'match' : ''}">${t}</span>`).join('')}
      </div>
    </div>

    ${blog.recent_titles && blog.recent_titles.length ? `
    <div class="modal-section">
      <h4>Últimos posts del blog</h4>
      <ul style="list-style:none;padding:0;">
        ${blog.recent_titles.slice(0, 6).map(t => `<li style="padding:4px 0;font-size:13px;color:var(--ink-2);">— ${t}</li>`).join('')}
      </ul>
    </div>` : ''}
  `;

  document.getElementById('modal-bg').hidden = false;
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modal-bg').hidden = true;
  document.body.style.overflow = '';
}

// ============================================================
// Go
// ============================================================
init();
