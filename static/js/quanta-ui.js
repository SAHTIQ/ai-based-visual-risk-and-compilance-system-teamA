// ╔══════════════════════════════════════════════════════════════╗
// ║         QUANTA UI — Shared Utility Module v2                 ║
// ╚══════════════════════════════════════════════════════════════╝

// ─── Chart.js Theme-Aware Defaults ────────────────────────────────────────────
export function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const gridColor   = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
  const tickColor   = isDark ? '#64748b' : '#9ca3af';
  const tooltipBg   = isDark ? 'rgba(13,14,26,0.96)' : 'rgba(255,255,255,0.98)';
  const tooltipTitle = isDark ? '#f1f5f9' : '#111827';
  const tooltipBody  = isDark ? '#94a3b8' : '#6b7280';
  const tooltipBorder = isDark ? 'rgba(124,58,237,0.3)' : 'rgba(0,0,0,0.08)';
  const legendColor  = isDark ? '#94a3b8' : '#6b7280';

  Chart.defaults.color = tickColor;
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.tooltip.backgroundColor = tooltipBg;
  Chart.defaults.plugins.tooltip.titleColor = tooltipTitle;
  Chart.defaults.plugins.tooltip.bodyColor   = tooltipBody;
  Chart.defaults.plugins.tooltip.borderColor = tooltipBorder;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.cornerRadius = 10;
  Chart.defaults.plugins.legend.labels.color = legendColor;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 10;
  try {
    Chart.defaults.scale.grid.color  = gridColor;
    Chart.defaults.scale.ticks.color = tickColor;
  } catch(e) {}
}

// ─── Overview / Forecast Toggle ────────────────────────────────────────────────
export function initToggle(containerId = 'mode-toggle') {
  const container = document.getElementById(containerId);
  if (!container) return;

  const buttons = container.querySelectorAll('.q-toggle-btn[data-mode]');

  function switchMode(mode) {
    // Update button states
    buttons.forEach(b => {
      const isActive = b.getAttribute('data-mode') === mode;
      b.classList.toggle('active', isActive);
      b.setAttribute('aria-pressed', String(isActive));
    });

    // Switch body class — CSS rules handle visibility
    if (mode === 'forecast') {
      document.body.classList.add('forecast-mode');
    } else {
      document.body.classList.remove('forecast-mode');
    }

    // Dispatch custom event so pages can react (e.g. resize charts)
    document.dispatchEvent(new CustomEvent('quanta-mode-change', { detail: { mode } }));
  }

  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      switchMode(btn.getAttribute('data-mode'));
    });
  });

  // Initialize to overview mode
  switchMode('overview');
}

// ─── Insight Cards ─────────────────────────────────────────────────────────────
const INSIGHT_ICONS = {
  info:    'bi-lightbulb-fill',
  warning: 'bi-exclamation-triangle-fill',
  success: 'bi-graph-up-arrow',
  danger:  'bi-exclamation-circle-fill',
};

export function renderInsights(containerId, insights) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!insights || insights.length === 0) {
    container.innerHTML = emptyState('No insights yet', 'Add more data to unlock personalised insights.');
    return;
  }

  container.innerHTML = insights.map(({ text, type = 'info' }) => `
    <div class="q-insight-card ${type}">
      <i class="bi ${INSIGHT_ICONS[type] || INSIGHT_ICONS.info} q-insight-icon"></i>
      <p class="q-insight-text">${text}</p>
    </div>
  `).join('');
}

// ─── Info Tooltips ─────────────────────────────────────────────────────────────
export function initTooltips() {
  if (typeof bootstrap === 'undefined') return;
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover focus', html: true });
  });
}

// ─── Confidence Badge ──────────────────────────────────────────────────────────
export function confidenceBadge(r2Score) {
  if (r2Score >= 0.8) return `<span class="q-confidence high"><i class="bi bi-patch-check-fill"></i> High Confidence</span>`;
  if (r2Score >= 0.6) return `<span class="q-confidence medium"><i class="bi bi-patch-exclamation-fill"></i> Medium Confidence</span>`;
  return `<span class="q-confidence low"><i class="bi bi-patch-question-fill"></i> Low Confidence</span>`;
}

// ─── KPI Change Indicator ──────────────────────────────────────────────────────
export function changeIndicator(pct) {
  if (pct === null || pct === undefined || isNaN(pct)) return '';
  const abs = Math.abs(pct).toFixed(1);
  if (pct > 0)  return `<span class="q-kpi-change positive"><i class="bi bi-arrow-up-right"></i> ${abs}%</span>`;
  if (pct < 0)  return `<span class="q-kpi-change negative"><i class="bi bi-arrow-down-right"></i> ${abs}%</span>`;
  return `<span class="q-kpi-change neutral"><i class="bi bi-dash"></i> Stable</span>`;
}

// ─── Trend badge ────────────────────────────────────────────────────────────────
export function trendBadge(trend) {
  const map = {
    upward:   { icon: 'bi-arrow-up-right',  cls: 'text-danger',  label: 'Upward'   },
    downward: { icon: 'bi-arrow-down-right', cls: 'text-success', label: 'Downward' },
    stable:   { icon: 'bi-dash',            cls: 'text-warning', label: 'Stable'   },
  };
  const t = map[trend] || map.stable;
  return `<span class="${t.cls}" style="font-size:0.85rem;font-weight:600;">
    <i class="bi ${t.icon} me-1"></i>${t.label}
  </span>`;
}

// ─── Risk Badge ────────────────────────────────────────────────────────────────
export function riskBadge(level) {
  const map = {
    High:   'q-confidence low',
    Medium: 'q-confidence medium',
    Low:    'q-confidence high',
  };
  return `<span class="${map[level] || map.Low}">${level} Risk</span>`;
}

// ─── Empty State ───────────────────────────────────────────────────────────────
export function emptyState(title = 'Not enough data yet', sub = 'Add more records to unlock this insight.') {
  return `<div class="q-empty">
    <div class="q-empty-icon"><i class="bi bi-database-slash"></i></div>
    <div class="q-empty-title">${title}</div>
    <div class="q-empty-sub">${sub}</div>
  </div>`;
}

// ─── Loading Skeleton ──────────────────────────────────────────────────────────
export function skeleton(lines = 3) {
  return Array.from({ length: lines }, (_, i) =>
    `<div class="q-skeleton mb-2" style="height:16px;border-radius:8px;opacity:${1 - i * 0.2}"></div>`
  ).join('');
}

// ─── Score Ring SVG ────────────────────────────────────────────────────────────
export function scoreRing(score, max = 100, color = null, size = 120) {
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const accentColor = color || (isDark ? '#7c3aed' : '#0f766e');
  const ringBg      = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)';
  const textColor   = isDark ? '#f1f5f9' : '#111827';
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(Math.max(score / max, 0), 1);
  const offset = circumference * (1 - pct);
  return `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
      <circle cx="${size/2}" cy="${size/2}" r="${radius}"
        fill="none" stroke="${ringBg}" stroke-width="8"/>
      <circle cx="${size/2}" cy="${size/2}" r="${radius}"
        fill="none" stroke="${accentColor}" stroke-width="8"
        stroke-linecap="round"
        stroke-dasharray="${circumference}"
        stroke-dashoffset="${offset}"
        style="transition: stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1);"/>
      <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central"
        fill="${textColor}" font-size="${size * 0.22}px" font-weight="700"
        font-family="Inter,sans-serif" style="transform:rotate(90deg);transform-origin:center">
        ${Math.round(score)}
      </text>
    </svg>`;
}

// ─── Category color palette (works across both themes) ────────────────────────
export const CAT_COLORS = [
  '#7c3aed','#06b6d4','#10b981','#f59e0b','#ef4444','#ec4899','#8b5cf6','#3b82f6','#14b8a6','#f97316'
];

// ─── Format helpers ────────────────────────────────────────────────────────────
export function formatPct(v) { return `${Math.round(v)}%`; }
export function fmtHrs(mins) {
  const h = Math.floor(mins / 60), m = Math.round(mins % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ─── Mobile Sidebar ────────────────────────────────────────────────────────────
export function initMobileSidebar() {
  const hamburger = document.getElementById('q-hamburger');
  const sidebar   = document.getElementById('q-sidebar');
  const overlay   = document.getElementById('q-sidebar-overlay');
  if (!hamburger || !sidebar) return;

  hamburger.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('show');
  });
  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('show');
    });
  }
}

// ─── Auto-init on DOMContentLoaded ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applyChartDefaults();
  initMobileSidebar();
  initTooltips();
});
