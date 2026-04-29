/* app.js — data loading and rendering for the AI Trend Intelligence site.
   Loads docs/data/*.json and populates the UI. Degrades gracefully if files are
   missing or empty (pipeline hasn't run yet). */

'use strict';

const DATA_DIR = 'data/';
const SOURCE_CLASSES = ['primary', 'operator', 'practitioner', 'media', 'market'];

/* ── Bootstrap ──────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  await loadAll();
});

function setupTabs() {
  const buttons = document.querySelectorAll('.tab-btn');
  const panels  = document.querySelectorAll('.tab-panel');

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      buttons.forEach(b => b.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const target = document.getElementById('tab-' + btn.dataset.tab);
      if (target) target.classList.add('active');
    });
  });
}

async function loadAll() {
  const [meta, trendsData, themesData, sourcesData] = await Promise.all([
    fetchJson('meta.json'),
    fetchJson('trends.json'),
    fetchJson('themes.json'),
    fetchJson('sources.json'),
  ]);

  renderMeta(meta);
  renderTrendsTab(trendsData);
  renderThemesTab(themesData);
  renderSourcesTab(sourcesData);
}

async function fetchJson(filename) {
  try {
    const res = await fetch(DATA_DIR + filename + '?v=' + Date.now());
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/* ── Meta bar ───────────────────────────────────────────────────────── */

function renderMeta(meta) {
  const lastRun = document.getElementById('last-updated');
  const itemCount = document.getElementById('item-count');
  const themeCount = document.getElementById('theme-count');

  if (!meta) {
    if (lastRun) lastRun.textContent = 'not yet available';
    return;
  }

  if (lastRun && meta.last_run) {
    const d = new Date(meta.last_run);
    lastRun.textContent = d.toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short',
    });
  }

  if (itemCount) itemCount.textContent = (meta.item_count ?? '—') + ' items';
  if (themeCount) themeCount.textContent = (meta.theme_count ?? '—') + ' themes';
}

/* ── Trends tab ─────────────────────────────────────────────────────── */

function renderTrendsTab(data) {
  const trends = data?.trends;

  if (!trends || trends.length === 0) {
    showEmpty('trend-chart-wrap', 'No trend data yet', 'Run the pipeline at least twice to populate trend history.');
    showEmpty('hype-evidence-wrap', 'No hype data yet', '');
    return;
  }

  // Trend phase chart
  renderTrendChart('trend-chart', trends);

  // Hype vs substantiation
  renderHypeCharts('hype-chart-evidence', 'hype-chart-media', trends);

  // Trend summary table
  renderTrendTable(trends);
}

function renderTrendTable(trends) {
  const tbody = document.getElementById('trend-table-body');
  if (!tbody) return;

  tbody.innerHTML = trends.map(t => {
    const state = t.state || 'unknown';
    const hypeClass = (t.hype_risk ?? 0) > 0.6 ? 'hype-high'
                    : (t.hype_risk ?? 0) > 0.35 ? 'hype-mid'
                    : 'hype-low';
    const confPct = Math.round((t.confidence ?? 0) * 100);
    const vel = t.velocity >= 0 ? `+${t.velocity.toFixed(2)}` : t.velocity.toFixed(2);

    return `
      <tr>
        <td><strong>${escHtml(t.theme)}</strong></td>
        <td><span class="state-badge state-${escHtml(state)}">${escHtml(state)}</span></td>
        <td>${(t.volume ?? 0).toFixed(1)}</td>
        <td>${vel}</td>
        <td>${t.diversity ?? '—'}</td>
        <td>
          <span class="${hypeClass}">${Math.round((t.hype_risk ?? 0) * 100)}%</span>
        </td>
        <td>
          <span class="confidence-bar" title="${confPct}% confidence">
            <span class="confidence-fill" style="width:${confPct}%"></span>
          </span>
          ${confPct}%
        </td>
      </tr>`;
  }).join('');
}

/* ── Themes tab ─────────────────────────────────────────────────────── */

function renderThemesTab(data) {
  const themes = data?.themes;

  if (!themes || themes.length === 0) {
    showEmpty('theme-grid', 'No themes yet', 'Themes appear after the trend pipeline runs.');
    showEmpty('heatmap-container', '', '');
    return;
  }

  renderThemeCards(themes);
  renderHeatmap('heatmap-container', themes, SOURCE_CLASSES);
}

function renderThemeCards(themes) {
  const grid = document.getElementById('theme-grid');
  if (!grid) return;

  grid.innerHTML = themes.map(t => {
    const state = t.state || 'unknown';
    const hype  = t.hype_risk ?? 0;
    const hypeClass = hype > 0.6 ? 'hype-high' : hype > 0.35 ? 'hype-mid' : 'hype-low';
    const classesList = (t.source_classes || []).join(', ') || '—';
    const domain = t.domain || '';
    const lastSeen = t.last_seen
      ? new Date(t.last_seen).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      : '—';

    return `
      <div class="theme-card">
        <div class="theme-card-header">
          <span class="theme-name">${escHtml(t.name)}</span>
          <span class="state-badge state-${escHtml(state)}">${escHtml(state)}</span>
        </div>
        <div class="theme-meta">
          ${domain ? `<span class="theme-domain">${escHtml(domain)}</span>` : ''}
          Last seen: ${lastSeen}
        </div>
        ${t.definition ? `<p style="font-size:13px;color:#555;margin:0 0 8px;line-height:1.5">${escHtml(t.definition)}</p>` : ''}
        <div class="theme-metrics">
          <span class="metric">
            <span class="metric-label">Items</span>
            <span class="metric-value">${t.item_count ?? '—'}</span>
          </span>
          <span class="metric">
            <span class="metric-label">Hype risk</span>
            <span class="metric-value ${hypeClass}">${Math.round(hype * 100)}%</span>
          </span>
          <span class="metric">
            <span class="metric-label">Sources</span>
            <span class="metric-value" title="${escHtml(classesList)}">${(t.source_classes || []).length}</span>
          </span>
        </div>
      </div>`;
  }).join('');
}

/* ── Sources tab ────────────────────────────────────────────────────── */

function renderSourcesTab(data) {
  const classes = data?.classes;

  const grid = document.getElementById('source-class-grid');
  if (!grid) return;

  if (!classes) {
    showEmpty('source-class-grid', 'No source data yet', '');
    return;
  }

  const classColors = {
    primary:      '#4a7c59',
    operator:     '#1a5c96',
    practitioner: '#856404',
    media:        '#5a2a8a',
    market:       '#721c24',
  };

  grid.innerHTML = SOURCE_CLASSES.map(cls => {
    const info   = classes[cls] || { count: 0, sources: [] };
    const color  = classColors[cls] || '#555';
    const list   = (info.sources || []).join(', ') || 'none configured';
    const desc   = sourceClassDesc(cls);

    return `
      <div class="source-class-card" style="border-top-color:${color}">
        <div class="source-class-name" style="color:${color}">${escHtml(cls)}</div>
        <div class="source-class-count">${info.count ?? 0}</div>
        <div class="source-class-list">${escHtml(list)}</div>
        <p style="font-size:11px;color:#aaa;margin:6px 0 0;line-height:1.4">${desc}</p>
      </div>`;
  }).join('');
}

function sourceClassDesc(cls) {
  const descs = {
    primary:      'Papers, benchmarks, model cards. Closest to the claim.',
    operator:     'Vendor changelogs, pricing, API updates. Incentive-driven.',
    practitioner: 'Blogs, HN, conference talks. Anecdotal but fast.',
    media:        'Press, newsletters, analysis. Narrative framing.',
    market:       'Funding, filings, job postings. Lagging but real.',
  };
  return descs[cls] || '';
}

/* ── Helpers ────────────────────────────────────────────────────────── */

function showEmpty(containerId, title, message) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `
    <div class="empty-state">
      <div class="empty-state-icon">📭</div>
      ${title ? `<h3>${escHtml(title)}</h3>` : ''}
      ${message ? `<p>${escHtml(message)}</p>` : ''}
    </div>`;
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
