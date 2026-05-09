/* app.js — data loading and rendering for the AI Trend Intelligence site.
   Loads docs/data/*.json and populates the UI. Degrades gracefully if files are
   missing or empty (pipeline hasn't run yet). */

'use strict';

const DATA_DIR = 'data/';
const SOURCE_CLASSES = ['primary', 'operator', 'practitioner', 'media', 'market'];

/* ── Theme Colour System ─────────────────────────────────────────────── */

// 20-slot palette with hues distributed evenly across the wheel.
// Designed for legibility on the dark (#0d0d0d) background.
// Sequence is perceptually ordered to maximise contrast between neighbours.
const THEME_PALETTE = [
  '#00C3A5', // teal
  '#ff6348', // red-orange
  '#a29bfe', // lavender
  '#ffa502', // amber
  '#74b9ff', // sky blue
  '#2ed573', // green
  '#fd79a8', // bubblegum
  '#eccc68', // yellow
  '#6c5ce7', // violet
  '#ff6b81', // rose
  '#00cec9', // cyan
  '#e17055', // salmon
  '#55efc4', // aquamarine
  '#d63031', // scarlet
  '#fdcb6e', // gold
  '#1e90ff', // dodger blue
  '#b8e994', // lime
  '#5352ed', // indigo
  '#f8c291', // peach
  '#00b894', // mint
];

// Maps theme name → hex colour. Built once from all loaded theme names.
// Sorted alphabetically before assignment so the mapping is stable across
// page reloads even if theme order in the JSON changes.
let THEME_COLOR_MAP = {};

// Tracks which theme is currently showing in the drill-down panel (module level
// so both the card click handler and the close button share the same state).
let _selectedTheme = null;

// Hex colour validator — guards against unexpected values reaching inline styles.
// Accepts valid CSS hex formats: #RGB, #RGBA, #RRGGBB, #RRGGBBAA (3, 4, 6, or 8 digits).
const _HEX_RE = /^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$/;
function safeColor(value, fallback) {
  return _HEX_RE.test(value) ? value : fallback;
}

function buildThemeColorMap(allThemeNames) {
  const sorted = [...new Set(allThemeNames)].sort();
  THEME_COLOR_MAP = {};
  sorted.forEach((name, i) => {
    THEME_COLOR_MAP[name] = THEME_PALETTE[i % THEME_PALETTE.length];
  });
}

function themeColor(name) {
  return THEME_COLOR_MAP[name] || '#999';
}

// Return hex + 2-digit alpha (e.g. '#00C3A580' for 50% opacity)
// Defined in charts.js (loaded before app.js); redeclared here to allow
// app.js to be used standalone in tests without charts.js.
function hexAlpha(hex, alpha) {
  return hex + Math.round(alpha * 255).toString(16).padStart(2, '0');
}

/* ── Date / time helpers (all output in browser local timezone) ─────── */

// Format an ISO datetime string (e.g. "2026-05-03T07:12:00Z") for display.
// Uses the browser's local timezone — no timeZone override.
function formatLocalDateTime(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  if (isNaN(d)) return isoString;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

// Format a YYYY-MM-DD date string as a short local date (e.g. "3 May 2026").
// Parses as local midnight to avoid UTC-offset surprises on date-only values.
function formatLocalDate(dateStr) {
  if (!dateStr) return '—';
  const parts = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!parts) return dateStr;
  const d = new Date(+parts[1], +parts[2] - 1, +parts[3]);
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

// Short variant: "3 May" (no year) — used where space is tight.
function formatLocalDateShort(dateStr) {
  if (!dateStr) return '—';
  const parts = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!parts) return dateStr;
  const d = new Date(+parts[1], +parts[2] - 1, +parts[3]);
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

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
  const [meta, trendsData, themesData, sourcesData, itemsData, logData] = await Promise.all([
    fetchJson('meta.json'),
    fetchJson('trends.json'),
    fetchJson('themes.json'),
    fetchJson('sources.json'),
    fetchJson('items.json'),
    fetchJson('log.json'),
  ]);

  // Build colour map from all theme names across both data files before rendering.
  const allNames = [
    ...(trendsData?.trends || []).map(t => t.theme),
    ...(themesData?.themes  || []).map(t => t.name),
  ];
  buildThemeColorMap(allNames);

  const items = itemsData?.items || [];

  renderMeta(meta);
  renderTrendsTab(trendsData);
  renderThemesTab(themesData, items);
  renderSourcesTab(sourcesData);
  renderInsightsTab(trendsData, meta, items, logData);

  // Close button for the drill-down panel (set up once after render).
  document.getElementById('drill-down-close')?.addEventListener('click', () => {
    _selectedTheme = null;
    document.querySelectorAll('#theme-grid .theme-card.selected').forEach(c => c.classList.remove('selected'));
    renderItemDrillDown(null, items);
  });
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
    lastRun.textContent = formatLocalDateTime(meta.last_run);
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
  renderTrendChart('trend-chart', trends, THEME_COLOR_MAP);

  // Hype vs substantiation
  renderHypeCharts('hype-chart-evidence', 'hype-chart-media', trends, THEME_COLOR_MAP);

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
    const color = themeColor(t.theme);

    return `
      <tr>
        <td>
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:7px;flex-shrink:0;vertical-align:middle"></span><strong>${escHtml(t.theme)}</strong>
        </td>
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

function renderThemesTab(data, items) {
  const themes = data?.themes;

  if (!themes || themes.length === 0) {
    showEmpty('theme-grid', 'No themes yet', 'Themes appear after the trend pipeline runs.');
    showEmpty('heatmap-container', '', '');
    return;
  }

  renderThemeCards(themes, items);
  renderHeatmap('heatmap-container', themes, SOURCE_CLASSES, THEME_COLOR_MAP);
}

function renderThemeCards(themes, items) {
  const grid = document.getElementById('theme-grid');
  if (!grid) return;

  grid.innerHTML = themes.map(t => {
    const state = t.state || 'unknown';
    const hype  = t.hype_risk ?? 0;
    const hypeClass = hype > 0.6 ? 'hype-high' : hype > 0.35 ? 'hype-mid' : 'hype-low';
    const classesList = (t.source_classes || []).join(', ') || '—';
    const domain = t.domain || '';
    const lastSeen = formatLocalDateShort(t.last_seen);
    const color = safeColor(themeColor(t.name), '#999');

    return `
      <div class="theme-card" data-theme="${escHtml(t.name)}" style="border-left-color:${color}">
        <div class="theme-card-header">
          <span class="theme-name" style="color:${color}">${escHtml(t.name)}</span>
          <span class="state-badge state-${escHtml(state)}">${escHtml(state)}</span>
        </div>
        <div class="theme-meta">
          ${domain ? `<span class="theme-domain">${escHtml(domain)}</span>` : ''}
          Last seen: ${lastSeen}
        </div>
        ${t.definition ? `<p style="font-size:0.75rem;color:#999;margin:0 0 8px;line-height:1.5">${escHtml(t.definition)}</p>` : ''}
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
        <div class="theme-card-hint">view items ↓</div>
      </div>`;
  }).join('');

  // Click delegation — selecting a card opens the drill-down panel.
  // Uses module-level _selectedTheme so the close button can reset it correctly.
  grid.addEventListener('click', e => {
    const card = e.target.closest('.theme-card');
    if (!card) return;
    const themeName = card.dataset.theme;

    if (_selectedTheme === themeName) {
      // Toggle off: clicking the active card again closes the panel.
      _selectedTheme = null;
      card.classList.remove('selected');
      renderItemDrillDown(null, items);
      return;
    }

    grid.querySelectorAll('.theme-card.selected').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    _selectedTheme = themeName;
    // Scroll panel into view after rendering.
    renderItemDrillDown(themeName, items);
    document.getElementById('drill-down-panel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
}

/* ── Item drill-down provenance panel ──────────────────────────────── */

function renderItemDrillDown(themeName, allItems) {
  const panel = document.getElementById('drill-down-panel');
  const title = document.getElementById('drill-down-title');
  const body  = document.getElementById('drill-down-body');
  if (!panel) return;

  if (!themeName) {
    panel.hidden = true;
    return;
  }

  const items = allItems
    .filter(i => i.theme === themeName)
    .sort((a, b) => (b.fetch_date || '').localeCompare(a.fetch_date || ''));

  const color = safeColor(themeColor(themeName), '#999');
  panel.style.borderLeftColor = color;
  panel.hidden = false;

  if (title) {
    title.textContent = `${themeName} — ${items.length} item${items.length !== 1 ? 's' : ''}`;
    title.style.color = color;
  }

  if (!body) return;

  if (items.length === 0) {
    body.innerHTML = '<p style="color:var(--text-muted);font-size:0.75rem;margin:0">No items in current data window.</p>';
    return;
  }

  const rows = items.map(item => {
    const cls      = item.source_class || 'practitioner';
    const clsColor = safeColor(CLASS_COLORS[cls], '#555');
    const badge    = `<span class="source-badge" style="background:${hexAlpha(clsColor, 0.12)};color:${clsColor};border:1px solid ${hexAlpha(clsColor, 0.25)}">${escHtml(cls)}</span>`;
    return `
      <tr>
        <td class="date-cell">${formatLocalDate(item.fetch_date)}</td>
        <td class="source-name-cell">${escHtml(item.source_name || '—')}</td>
        <td>${badge}</td>
      </tr>`;
  }).join('');

  body.innerHTML = `
    <table class="provenance-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Source</th>
          <th>Class</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ── Sources tab ────────────────────────────────────────────────────── */

const CLASS_COLORS = {
  primary:      '#00C3A5',
  operator:     '#6495ed',
  practitioner: '#f5c842',
  media:        '#9b7ed4',
  market:       '#E8A1A8',
};

function renderSourcesTab(data) {
  const classes = data?.classes;
  const sources = data?.sources || [];

  const grid = document.getElementById('source-class-grid');
  const table = document.getElementById('source-detail-table');
  if (!grid) return;

  if (!classes) {
    showEmpty('source-class-grid', 'No source data yet', '');
    return;
  }

  // ── Class summary cards ──────────────────────────────────────────
  grid.innerHTML = SOURCE_CLASSES.map(cls => {
    const info  = classes[cls] || { count: 0, sources: [] };
    const color = CLASS_COLORS[cls] || '#555';
    const list  = (info.sources || []).join(', ') || 'none configured';
    const desc  = sourceClassDesc(cls);
    return `
      <div class="source-class-card" style="border-top-color:${color}">
        <div class="source-class-name" style="color:${color}">${escHtml(cls)}</div>
        <div class="source-class-count">${info.count ?? 0}</div>
        <div class="source-class-list">${escHtml(list)}</div>
        <p style="font-size:0.7rem;color:#555;margin:6px 0 0;line-height:1.4">${desc}</p>
      </div>`;
  }).join('');

  // ── Per-source detail table ──────────────────────────────────────
  if (!table) return;

  if (sources.length === 0) {
    table.innerHTML = '<p style="color:#555;font-size:0.75rem">No per-source data available yet.</p>';
    return;
  }

  const rows = sources.map(s => {
    const cls   = s.source_class || 'practitioner';
    const color = CLASS_COLORS[cls] || '#555';
    const badge = `<span class="source-badge" style="background:${hexAlpha(color, 0.12)};color:${color};border:1px solid ${hexAlpha(color, 0.25)}">${escHtml(cls)}</span>`;
    const dateRange = s.first_seen && s.last_seen
      ? `${formatLocalDate(s.first_seen)} → ${formatLocalDate(s.last_seen)}`
      : '—';
    const themes = (s.top_themes || []).slice(0, 3)
      .map(t => {
        const tc = themeColor(t);
        return `<span class="theme-pill" style="border-color:${hexAlpha(tc, 0.25)};color:${tc}">${escHtml(t)}</span>`;
      })
      .join(' ');
    return `
      <tr>
        <td class="source-name-cell">${escHtml(s.name)}</td>
        <td>${badge}</td>
        <td class="num-cell">${s.item_count ?? 0}</td>
        <td class="num-cell">${s.days_active ?? 0}</td>
        <td class="date-cell">${escHtml(dateRange)}</td>
        <td class="themes-cell">${themes || '—'}</td>
      </tr>`;
  }).join('');

  table.innerHTML = `
    <table class="source-table">
      <thead>
        <tr>
          <th>Source</th>
          <th>Class</th>
          <th>Items</th>
          <th>Active days</th>
          <th>Date range</th>
          <th>Top themes</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
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

/* ── Insights tab ───────────────────────────────────────────────────── */

function renderInsightsTab(trendsData, meta, items, logData) {
  const trends = trendsData?.trends || [];
  renderInsightCards(trends, meta);
  renderLogSection(logData, meta);
  renderItemsExplorer(items);
}

function renderInsightCards(trends, meta) {
  const container = document.getElementById('insights-container');
  if (!container) return;

  if (trends.length === 0) {
    showEmpty('insights-container', 'No insights yet', 'Run the pipeline at least once to generate trend data.');
    return;
  }

  const cards = [];

  // ── Data health ──────────────────────────────────────────────────
  const totalItems  = meta?.total_items  || 0;
  const themedItems = meta?.themed_items || 0;
  const enrichRate  = meta?.enrichment_rate ?? (totalItems ? themedItems / totalItems : 0);

  if (totalItems > 0 && enrichRate < 0.5) {
    const pct = Math.round(enrichRate * 100);
    cards.push({
      kind: 'warning',
      title: 'AI enrichment incomplete',
      body: `Only ${themedItems} of ${totalItems} items (${pct}%) have been AI-enriched with themes and summaries. `
          + 'Themes, trend states, and insights will be incomplete until GEMINI_API_KEY is active in the pipeline.',
    });
  }

  // ── All themes declining ─────────────────────────────────────────
  const allDeclining = trends.length > 0 && trends.every(t => t.state === 'declining');
  if (allDeclining) {
    cards.push({
      kind: 'warning',
      title: 'All trends currently declining',
      body: 'Every tracked theme shows a declining state. This typically means no new AI-enriched items have '
          + 'been added in the last 14 days. Check that the pipeline is running and GEMINI_API_KEY is set.',
    });
  }

  // ── Confirmed signals (diversity ≥ 2) ───────────────────────────
  const confirmed = trends.filter(t => (t.diversity || 0) >= 2);
  if (confirmed.length > 0) {
    const names = confirmed.map(t => t.theme).join(', ');
    cards.push({
      kind: 'signal',
      title: `${confirmed.length} theme${confirmed.length > 1 ? 's' : ''} confirmed by ≥ 2 source types`,
      body: names,
      themes: confirmed.map(t => t.theme),
    });
  } else {
    cards.push({
      kind: 'gap',
      title: 'No cross-source confirmation yet',
      body: 'All themes currently have only a single source type (practitioner). '
          + 'Adding primary (arXiv) or operator (Anthropic, OpenAI) sources will enable cross-class confirmation.',
    });
  }

  // ── Hype alerts ──────────────────────────────────────────────────
  const hyped = trends.filter(t => (t.hype_risk || 0) > 0.5);
  if (hyped.length > 0) {
    const names = hyped.map(t => `${t.theme} (${Math.round(t.hype_risk * 100)}%)`).join(', ');
    cards.push({
      kind: 'hype',
      title: `${hyped.length} high-hype theme${hyped.length > 1 ? 's' : ''}`,
      body: 'These themes have high media/language intensity relative to evidence density: ' + names,
      themes: hyped.map(t => t.theme),
    });
  }

  // ── Top theme by volume ──────────────────────────────────────────
  const byVolume = [...trends].sort((a, b) => (b.volume || 0) - (a.volume || 0));
  if (byVolume.length > 0) {
    const top = byVolume[0];
    cards.push({
      kind: 'signal',
      title: `Most active: ${top.theme}`,
      body: `Volume score ${top.volume.toFixed(2)}, ${top.item_count} item${top.item_count !== 1 ? 's' : ''}, `
          + `diversity ${top.diversity} source type${top.diversity !== 1 ? 's' : ''}. `
          + `State: ${top.state}.`,
      themes: [top.theme],
    });
  }

  // ── Source coverage gap ──────────────────────────────────────────
  const practitionerOnly = trends.filter(t =>
    (t.source_classes || []).length === 1 &&
    (t.source_classes || [])[0] === 'practitioner'
  );
  if (practitionerOnly.length === trends.length && trends.length > 0) {
    cards.push({
      kind: 'gap',
      title: 'Practitioner-only coverage',
      body: `All ${trends.length} themes are covered only by practitioner-class sources (YouTube, Hacker News). `
          + 'Enable arXiv, operator blog, or media RSS sources in config/sources.yaml to enable triangulation.',
    });
  }

  // ── Render cards ─────────────────────────────────────────────────
  container.innerHTML = cards.map(card => {
    const kindColor = {
      signal:  '#00C3A5',
      warning: '#ffa502',
      hype:    '#ff6348',
      gap:     '#555',
    }[card.kind] || '#555';

    const themeChips = (card.themes || []).map(t => {
      const tc = safeColor(themeColor(t), '#999');
      return `<span class="theme-pill" style="border-color:${hexAlpha(tc, 0.3)};color:${tc}">${escHtml(t)}</span>`;
    }).join(' ');

    return `
      <div class="insight-card" style="border-left:3px solid ${kindColor};padding:14px 16px;
           background:var(--surface);border-radius:4px;margin-bottom:12px">
        <div style="font-size:0.8rem;font-weight:600;color:${kindColor};letter-spacing:0.04em;margin-bottom:6px">
          ${escHtml(card.title)}
        </div>
        <p style="font-size:0.75rem;color:var(--text-muted);margin:0 0 ${themeChips ? '8px' : '0'};line-height:1.6">
          ${escHtml(card.body)}
        </p>
        ${themeChips ? `<div style="display:flex;flex-wrap:wrap;gap:4px">${themeChips}</div>` : ''}
      </div>`;
  }).join('');
}

function renderLogSection(logData, meta) {
  const container = document.getElementById('log-container');
  if (!container) return;

  const data = logData || meta;
  if (!data) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:0.75rem">No log data available.</p>';
    return;
  }

  const totalItems   = data.total_items   ?? '—';
  const themedItems  = data.themed_items  ?? '—';
  const unthemed     = data.unthemed_items ?? '—';
  const enrichRate   = data.enrichment_rate != null ? Math.round(data.enrichment_rate * 100) + '%' : '—';
  const themeCount   = data.qualifying_themes ?? data.theme_count ?? '—';
  const sourceCount  = data.source_count ?? '—';
  const dateFirst    = data.date_range?.first || '—';
  const dateLast     = data.date_range?.last  || '—';
  const aiNote       = data.ai_note || '';
  const files        = data.files || [];
  const generated    = formatLocalDateTime(data.generated || '');

  const aiNoteColor = data.enrichment_rate != null && data.enrichment_rate < 0.5 ? '#ffa502' : '#00C3A5';

  const fileRows = files.map(f =>
    `<tr>
      <td style="font-size:0.7rem;color:var(--text);padding:3px 8px">${escHtml(f.file)}</td>
      <td style="font-size:0.7rem;text-align:right;padding:3px 8px">${f.total}</td>
      <td style="font-size:0.7rem;text-align:right;padding:3px 8px">${f.valid}</td>
      <td style="font-size:0.7rem;text-align:right;padding:3px 8px;color:${f.themed === 0 ? '#ffa502' : 'var(--text-muted)'}">${f.themed}</td>
      <td style="font-size:0.7rem;text-align:right;padding:3px 8px;color:${f.filtered_hist > 0 ? '#555' : 'var(--text-muted)'}">${f.filtered_hist}</td>
    </tr>`
  ).join('');

  container.innerHTML = `
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:16px;font-size:0.75rem">
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:16px">
        ${_logStat('Total items loaded', totalItems)}
        ${_logStat('AI-enriched (themed)', themedItems)}
        ${_logStat('Unenriched', unthemed)}
        ${_logStat('Enrichment rate', enrichRate, data.enrichment_rate != null ? (data.enrichment_rate < 0.5 ? '#ffa502' : '#00C3A5') : 'var(--text)')}
        ${_logStat('Qualifying themes', themeCount)}
        ${_logStat('Active sources', sourceCount)}
        ${_logStat('Data from', dateFirst)}
        ${_logStat('Data to', dateLast)}
      </div>
      ${aiNote ? `<p style="color:${aiNoteColor};margin:0 0 14px;line-height:1.5">${escHtml(aiNote)}</p>` : ''}
      ${files.length > 0 ? `
        <div style="overflow-x:auto">
          <table style="border-collapse:collapse;width:100%">
            <thead>
              <tr style="color:var(--text-muted);font-size:0.65rem;letter-spacing:0.06em;text-transform:uppercase">
                <th style="text-align:left;padding:3px 8px">File</th>
                <th style="text-align:right;padding:3px 8px">Total</th>
                <th style="text-align:right;padding:3px 8px">Valid</th>
                <th style="text-align:right;padding:3px 8px">Themed</th>
                <th style="text-align:right;padding:3px 8px">Hist filtered</th>
              </tr>
            </thead>
            <tbody>${fileRows}</tbody>
          </table>
        </div>` : ''}
      <p style="color:#333;font-size:0.65rem;margin:12px 0 0">Generated: ${generated}</p>
    </div>`;
}

function _logStat(label, value, color) {
  const c = color || 'var(--text)';
  return `<div>
    <div style="font-size:0.65rem;color:var(--text-muted);letter-spacing:0.06em;text-transform:uppercase;margin-bottom:3px">${escHtml(label)}</div>
    <div style="font-size:1.1rem;font-weight:600;color:${c}">${escHtml(String(value))}</div>
  </div>`;
}

/* ── Items explorer ─────────────────────────────────────────────────── */

let _allItems = [];

function renderItemsExplorer(items) {
  _allItems = items || [];

  const sourceSelect = document.getElementById('items-source-filter');
  const themeSelect  = document.getElementById('items-theme-filter');

  if (sourceSelect && themeSelect) {
    // Populate filter dropdowns from data
    const sources = [...new Set(_allItems.map(i => i.source_name).filter(Boolean))].sort();
    const themes  = [...new Set(_allItems.map(i => i.theme).filter(Boolean))].sort();

    sourceSelect.innerHTML = '<option value="">All sources</option>'
      + sources.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('');
    themeSelect.innerHTML  = '<option value="">All themes</option>'
      + themes.map(t => `<option value="${escHtml(t)}">${escHtml(t)}</option>`).join('');

    sourceSelect.addEventListener('change', _applyItemsFilter);
    themeSelect.addEventListener('change',  _applyItemsFilter);
  }

  const searchInput = document.getElementById('items-search');
  if (searchInput) {
    searchInput.addEventListener('input', _applyItemsFilter);
  }

  _applyItemsFilter();
}

function _applyItemsFilter() {
  const query  = (document.getElementById('items-search')?.value  || '').toLowerCase();
  const source = document.getElementById('items-source-filter')?.value || '';
  const theme  = document.getElementById('items-theme-filter')?.value  || '';

  let filtered = _allItems;
  if (source) filtered = filtered.filter(i => i.source_name === source);
  if (theme)  filtered = filtered.filter(i => i.theme === theme);
  if (query)  filtered = filtered.filter(i =>
    (i.title        || '').toLowerCase().includes(query) ||
    (i.source_name  || '').toLowerCase().includes(query) ||
    (i.theme        || '').toLowerCase().includes(query) ||
    (i.summary      || '').toLowerCase().includes(query)
  );

  const countBar = document.getElementById('items-count-bar');
  if (countBar) {
    countBar.textContent = `Showing ${filtered.length} of ${_allItems.length} items`;
  }

  _renderItemsTable(filtered);
}

function _renderItemsTable(items) {
  const container = document.getElementById('items-table-container');
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:0.75rem;letter-spacing:0.04em">No items match the current filter.</p>';
    return;
  }

  // Show at most 200 rows for performance
  const visible = items.slice(0, 200);
  const truncated = items.length > 200;

  const rows = visible.map(item => {
    const cls      = item.source_class || 'practitioner';
    const clsColor = safeColor(CLASS_COLORS[cls], '#555');
    const badge    = `<span class="source-badge" style="background:${hexAlpha(clsColor, 0.12)};color:${clsColor};border:1px solid ${hexAlpha(clsColor, 0.25)}">${escHtml(cls)}</span>`;
    const themeStr = item.theme || '';
    const tc       = themeStr ? safeColor(themeColor(themeStr), '#555') : '#333';
    const themePill = themeStr
      ? `<span class="theme-pill" style="border-color:${hexAlpha(tc, 0.25)};color:${tc}">${escHtml(themeStr)}</span>`
      : '<span style="color:#333;font-size:0.7rem">—</span>';
    const hype   = item.hype_risk != null ? Math.round(item.hype_risk * 100) + '%' : '—';
    const cred   = item.credibility_score != null ? item.credibility_score.toFixed(2) : '—';
    const safeUrl = (item.url || '').match(/^https?:\/\//) ? item.url : '';
    const titleHtml = safeUrl
      ? `<a href="${escHtml(safeUrl)}" target="_blank" rel="noopener"
             style="color:var(--text);text-decoration:none;font-size:0.75rem"
             title="${escHtml(item.summary || item.title)}">${escHtml(item.title || '—')}</a>`
      : `<span style="font-size:0.75rem;color:var(--text-muted)">${escHtml(item.title || '—')}</span>`;

    return `<tr>
      <td class="date-cell">${formatLocalDate(item.fetch_date)}</td>
      <td>${titleHtml}</td>
      <td class="source-name-cell">${escHtml(item.source_name || '—')}</td>
      <td>${badge}</td>
      <td>${themePill}</td>
      <td class="num-cell" style="font-size:0.7rem">${hype}</td>
      <td class="num-cell" style="font-size:0.7rem">${cred}</td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <table class="source-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Title</th>
          <th>Source</th>
          <th>Class</th>
          <th>Theme</th>
          <th>Hype</th>
          <th>Cred</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${truncated ? `<p style="font-size:0.7rem;color:#555;margin:8px 0 0;letter-spacing:0.04em">Showing first 200 of ${items.length}. Apply a filter to narrow results.</p>` : ''}`;
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
