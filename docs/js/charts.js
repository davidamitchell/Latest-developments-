/* charts.js — Chart.js wrappers for the trend intelligence site.
   All functions are no-ops if data is missing or empty.
   Dark mode palette matches css/style.css: bg #0d0d0d, teal #00C3A5, dusk #E8A1A8.
   Theme-specific colours are passed in via the colorMap parameter and assigned
   by app.js::buildThemeColorMap() before any chart is rendered. */

'use strict';

// Dark-mode chart defaults applied globally
Chart.defaults.color = '#666';
Chart.defaults.borderColor = '#252b33';
Chart.defaults.backgroundColor = '#0f1115';

// Fallback state colours — used only when no colorMap entry is found for a theme
const STATE_COLORS = {
  emerging:  'rgba(245, 200,  66, 0.85)',
  scaling:   'rgba(  0, 195, 165, 0.85)',
  mature:    'rgba(100, 149, 237, 0.85)',
  declining: 'rgba(232, 161, 168, 0.85)',
};

// Phase band thresholds in items/week (integer scale used by history snapshots)
const PHASE_BANDS = [
  { label: 'Low activity',  yMin: 0, yMax: 2,  color: 'rgba(245,200,66,0.07)' },
  { label: 'Active',        yMin: 2, yMax: 5,  color: 'rgba(0,195,165,0.07)' },
  { label: 'High activity', yMin: 5, yMax: 10, color: 'rgba(100,149,237,0.07)' },
];

let _trendChart  = null;
let _hypaBarEvidence = null;
let _hypaBarMedia    = null;

/* ── Trend Phase Chart ──────────────────────────────────────────────── */

/**
 * Render a multi-line time-series chart showing composite score per theme.
 * Each theme line uses its unique colour from colorMap.
 * @param {string}   canvasId  - ID of <canvas> element
 * @param {Array}    trends    - trends.json .trends array
 * @param {Object}   colorMap  - { themeName: hexColor } from buildThemeColorMap()
 */
function renderTrendChart(canvasId, trends, colorMap) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !trends || trends.length === 0) return;

  if (_trendChart) { _trendChart.destroy(); _trendChart = null; }

  // Collect all dates from history snapshots across all themes
  const dateSet = new Set();
  trends.forEach(t => (t.history || []).forEach(h => dateSet.add(h.date)));
  const labels = [...dateSet].sort();

  if (labels.length === 0) return;

  const datasets = trends.slice(0, 12).map((t, i) => {
    // Prefer theme-specific colour; fall back to state colour or hsl spread
    const color = (colorMap && colorMap[t.theme])
      || STATE_COLORS[t.state]
      || `hsl(${i * 30}, 70%, 60%)`;
    const pointMap = {};
    (t.history || []).forEach(h => { pointMap[h.date] = h.volume ?? 0; });
    return {
      label: t.theme,
      data: labels.map(d => pointMap[d] ?? null),
      borderColor: color,
      backgroundColor: color + '1a',  // hex alpha ≈ 10% fill under the line
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.2,
      spanGaps: false,   // don't connect across weeks with no data
    };
  });

  _trendChart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 12,
            font: { size: 11 },
            color: '#999',
            // Draw a circle rather than a box so the legend matches the dot on the chart
            usePointStyle: true,
            pointStyle: 'circle',
          },
        },
        tooltip: {
          callbacks: {
            label: ctx => ctx.parsed.y === null ? null
              : ` ${ctx.dataset.label}: ${ctx.parsed.y} item${ctx.parsed.y !== 1 ? 's' : ''}`,
          },
          filter: item => item.parsed.y !== null,
        },
        annotation: buildPhaseBandAnnotations(),
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8, font: { size: 11 }, color: '#666' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y: {
          min: 0,
          ticks: { stepSize: 1, precision: 0, color: '#666' },
          title: { display: true, text: 'Items per week', font: { size: 11 }, color: '#666' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
      },
    },
  });
}

function buildPhaseBandAnnotations() {
  // chartjs-plugin-annotation is optional; guard against its absence
  if (typeof window.ChartAnnotation === 'undefined') return {};
  const boxes = {};
  PHASE_BANDS.forEach((b, i) => {
    boxes[`band${i}`] = {
      type: 'box',
      yMin: b.yMin,
      yMax: b.yMax,
      backgroundColor: b.color,
      borderWidth: 0,
      label: { content: b.label, display: true, position: 'start', font: { size: 10 }, color: '#888' },
    };
  });
  return { annotations: boxes };
}

/* ── Hype vs Substantiation Bar Charts ─────────────────────────────── */

/**
 * Render paired horizontal bar charts: evidence-weighted vs media-weighted.
 * Each bar is coloured by its theme colour for consistency across the dashboard.
 * @param {string} evidenceCanvasId
 * @param {string} mediaCanvasId
 * @param {Array}  trends
 * @param {Object} colorMap  - { themeName: hexColor }
 */
function renderHypeCharts(evidenceCanvasId, mediaCanvasId, trends, colorMap) {
  const evCanvas  = document.getElementById(evidenceCanvasId);
  const medCanvas = document.getElementById(mediaCanvasId);
  if (!evCanvas || !medCanvas || !trends || trends.length === 0) return;

  if (_hypaBarEvidence) { _hypaBarEvidence.destroy(); _hypaBarEvidence = null; }
  if (_hypaBarMedia)    { _hypaBarMedia.destroy();    _hypaBarMedia = null; }

  const top = trends.slice(0, 10);
  const labels = top.map(t => t.theme);

  // Per-theme colours with hex alpha
  const bgColors     = top.map(t => ((colorMap && colorMap[t.theme]) || '#00C3A5') + '55');
  const borderColors = top.map(t => (colorMap && colorMap[t.theme]) || '#00C3A5');

  // Evidence-weighted score: volume * (1 - hype_risk) * confidence
  const evidenceScores = top.map(t =>
    +(((t.volume ?? 0) * (1 - (t.hype_risk ?? 0)) * (t.confidence ?? 0.5))).toFixed(2)
  );

  // Media-weighted score: volume * hype_risk (simplified proxy)
  const mediaScores = top.map(t =>
    +(((t.volume ?? 0) * (t.hype_risk ?? 0)).toFixed(2))
  );

  const sharedOptions = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: { legend: { display: false } },
    scales: {
      x: {
        min: 0,
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { font: { size: 11 }, color: '#666' },
      },
      y: { ticks: { font: { size: 11 }, color: '#999' } },
    },
  };

  _hypaBarEvidence = new Chart(evCanvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data: evidenceScores, backgroundColor: bgColors, borderColor: borderColors, borderWidth: 1 }],
    },
    options: { ...sharedOptions },
  });

  _hypaBarMedia = new Chart(medCanvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data: mediaScores, backgroundColor: bgColors, borderColor: borderColors, borderWidth: 1 }],
    },
    options: { ...sharedOptions },
  });
}

/* ── Source-class heatmap (CSS table, not canvas) ───────────────────── */

/**
 * Build a DOM heatmap table: rows=themes, cols=source classes.
 * Theme names in the first column are coloured by their theme colour.
 * @param {string}  containerId
 * @param {Array}   themes   - themes.json .themes array
 * @param {Array}   classes  - ordered list of class names
 * @param {Object}  colorMap - { themeName: hexColor }
 */
function renderHeatmap(containerId, themes, classes, colorMap) {
  const container = document.getElementById(containerId);
  if (!container || !themes || themes.length === 0) return;

  const maxVal = Math.max(1, ...themes.flatMap(t =>
    classes.map(c => (t.source_class_counts?.[c] ?? 0))
  ));

  const rows = themes.slice(0, 12).map(t => {
    const color = (colorMap && colorMap[t.name]) || '#e6e6e6';
    const cells = classes.map(c => {
      const v = t.source_class_counts?.[c] ?? 0;
      const heat = Math.round((v / maxVal) * 4);
      return `<td class="heat-${heat}" title="${c}: ${v}">${v || '—'}</td>`;
    }).join('');
    return `<tr><td style="color:${color};font-weight:500">${escHtml(t.name)}</td>${cells}</tr>`;
  }).join('');

  const CLASS_ABBR = {
    primary: 'Pri', operator: 'Ops', practitioner: 'Prac', media: 'Med', market: 'Mkt',
  };
  const headerCells = classes.map(c => {
    const abbr = CLASS_ABBR[c] || c;
    return `<th><abbr title="${escHtml(c)}">${escHtml(abbr)}</abbr></th>`;
  }).join('');

  container.innerHTML = `
    <div class="heatmap-scroll">
      <table class="heatmap-table">
        <thead><tr><th>Theme</th>${headerCells}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* ── Utilities ──────────────────────────────────────────────────────── */

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
