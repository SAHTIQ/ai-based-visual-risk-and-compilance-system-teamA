/**
 * QUANTA — Theme Manager
 * Centralized light/dark mode with:
 *  - localStorage persistence
 *  - System preference fallback (prefers-color-scheme)
 *  - Instant switching (no page reload)
 *  - Chart.js re-theming on switch
 */

const THEME_KEY = 'quanta_theme';

// ─── Resolve which theme to use ───────────────────────────────────────────────
function resolveTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  // No saved preference — use system preference
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

// ─── Apply theme to <html> ────────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('data-bs-theme', theme === 'dark' ? 'dark' : 'light');
  updateToggleUI(theme);
  rechartIfNeeded(theme);
}

// ─── Sync all toggle controls ─────────────────────────────────────────────────
function updateToggleUI(theme) {
  const isDark = theme === 'dark';
  document.querySelectorAll('.q-theme-checkbox').forEach(cb => {
    cb.checked = isDark;
  });
  document.querySelectorAll('.q-theme-icon').forEach(el => {
    el.className = `bi ${isDark ? 'bi-moon-stars-fill' : 'bi-sun-fill'} q-theme-icon`;
  });
  document.querySelectorAll('.q-theme-label-text').forEach(el => {
    el.textContent = isDark ? 'Dark' : 'Light';
  });
}

// ─── Re-apply Chart.js defaults on theme switch ───────────────────────────────
function rechartIfNeeded(theme) {
  if (typeof Chart === 'undefined') return;
  const isDark = theme === 'dark';
  const gridColor  = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(124,58,237,0.06)';
  const tickColor  = isDark ? '#64748b' : '#4c3770';
  const tooltipBg  = isDark ? 'rgba(13,14,26,0.96)' : 'rgba(255,255,255,0.98)';
  const tooltipTitle = isDark ? '#f1f5f9' : '#1e144a';
  const tooltipBody  = isDark ? '#94a3b8' : '#4c3770';
  const tooltipBorder = isDark ? 'rgba(124,58,237,0.3)' : 'rgba(124,58,237,0.15)';
  const legendColor  = isDark ? '#94a3b8' : '#1e144a';

  Chart.defaults.color = tickColor;
  Chart.defaults.plugins.tooltip.backgroundColor = tooltipBg;
  Chart.defaults.plugins.tooltip.titleColor = tooltipTitle;
  Chart.defaults.plugins.tooltip.bodyColor   = tooltipBody;
  Chart.defaults.plugins.tooltip.borderColor = tooltipBorder;
  Chart.defaults.plugins.legend.labels.color = legendColor;
  try {
    Chart.defaults.scale.grid.color  = gridColor;
    Chart.defaults.scale.ticks.color = tickColor;
  } catch(e) {}

  // Re-render all existing charts
  Object.values(Chart.instances).forEach(chart => {
    try {
      if (chart.options.scales) {
        Object.values(chart.options.scales).forEach(scale => {
          if (scale.grid)  scale.grid.color  = gridColor;
          if (scale.ticks) scale.ticks.color = tickColor;
        });
      }
      if (chart.options.plugins?.legend?.labels) {
        chart.options.plugins.legend.labels.color = legendColor;
      }
      chart.update('none');
    } catch(e) {}
  });
}

// ─── Toggle action ────────────────────────────────────────────────────────────
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}

// ─── Init ─────────────────────────────────────────────────────────────────────
export function initTheme() {
  const theme = resolveTheme();
  applyTheme(theme);

  // Wire up all toggle checkboxes
  document.querySelectorAll('.q-theme-checkbox').forEach(cb => {
    cb.checked = (theme === 'dark');
    cb.removeEventListener('change', toggleTheme);
    cb.addEventListener('change', toggleTheme);
  });

  // Wire up click-based toggle elements and settings rows
  document.querySelectorAll('[data-theme-toggle], #topbar-theme-toggle-row, .q-theme-toggle-row').forEach(el => {
    el.addEventListener('click', (e) => {
      // Prevent dropdown auto-close when clicking theme row inside bootstrap dropdown
      e.stopPropagation();
      // Avoid double firing if event originated directly from checkbox/label change
      if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'LABEL' && !e.target.classList.contains('q-slider')) {
        toggleTheme();
      }
    });
  });

  // React to OS-level preference changes (only if user has no saved preference)
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {
    if (!localStorage.getItem(THEME_KEY)) {
      applyTheme(e.matches ? 'light' : 'dark');
    }
  });
}

// ─── Legacy compat (used by old code) ─────────────────────────────────────────
export { applyTheme, resolveTheme, toggleTheme };
