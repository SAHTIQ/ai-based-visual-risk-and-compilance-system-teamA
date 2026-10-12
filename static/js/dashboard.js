/**
 * Quanta Dashboard — dashboard.js
 * Optimized for speed with stale-while-revalidate caching via sessionStorage.
 * Renders: KPIs, charts, streak, achievements, ML forecasts, habit risk, simulation, recent activity.
 */
import { apiCall, formatCurrency, showToast } from './api.js';
import { onAuthChange } from './auth.js';

// ─── Chart instances (kept for lifecycle management) ─────────────────────────
let incomeChartInst = null;
let expenseChartInst = null;
let studyChartInst = null;
let fitnessChartInst = null;
let goalsChartInst = null;
let aiFinanceChartInst = null;
let aiStudyChartInst = null;
let simChartInst = null;

// ─── Fast Stale-While-Revalidate Cache ─────────────────────────────────────────
const CACHE_PREFIX = 'quanta_dash_';
const CACHE_TTL = 3 * 60 * 1000; // 3 minutes
let activeUserId = null;

function getCacheKey(key) {
  return CACHE_PREFIX + (activeUserId ? activeUserId + '_' : '') + key;
}

function getCached(key) {
  try {
    const raw = sessionStorage.getItem(getCacheKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.time < CACHE_TTL) return parsed.data;
  } catch (e) {}
  return null;
}

function setCache(key, data) {
  try {
    sessionStorage.setItem(getCacheKey(key), JSON.stringify({ time: Date.now(), data }));
  } catch (e) {}
}

export function clearDashboardCache() {
  try {
    Object.keys(sessionStorage).forEach(k => {
      if (k.startsWith(CACHE_PREFIX)) sessionStorage.removeItem(k);
    });
  } catch (e) {}
}

// ─── Simulation scenario definitions ────────────────────────────────────────
const SIM_SCENARIOS = {
  financial: [
    { value: 'save_10', label: 'Save 10% More',       fn: v => v * 0.9 },
    { value: 'save_20', label: 'Save 20% More',       fn: v => v * 0.8 },
    { value: 'increase_income', label: 'Income +15%', fn: v => v * 1.0 },
  ],
  habits: [
    { value: 'daily',    label: 'All Habits Daily',   fn: v => Math.min(v * 1.4, 100) },
    { value: 'drop_one', label: 'Drop 1 Habit',       fn: v => v * 0.85 },
  ],
  productivity: [
    { value: 'focus_2h', label: '+2 hrs / Day',       fn: v => v * 1.3 },
    { value: 'pomodoro', label: 'Pomodoro Mode',      fn: v => v * 1.2 },
  ],
  fitness: [
    { value: 'gym_3x',  label: 'Gym 3x / Week',       fn: v => v * 1.35 },
    { value: 'cardio',  label: 'Add Daily Cardio',    fn: v => v * 1.25 },
  ],
};

// ─── DOM helpers ─────────────────────────────────────────────────────────────
const el = id => document.getElementById(id);
function setText(id, text)  { const e = el(id); if (e) e.textContent = text; }
function setHtml(id, html)  { const e = el(id); if (e) e.innerHTML = html; }

const PALETTE = ['#7c3aed','#06b6d4','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6'];

// ─── Greeting ────────────────────────────────────────────────────────────────
function setGreeting() {
  const h = new Date().getHours();
  const msg = h < 12 ? 'Good morning ☀️' : h < 17 ? 'Good afternoon 🌤️' : 'Good evening 🌙';
  setText('greeting-text', `${msg} — here's your digital twin overview.`);
}

// ─── Streak & Achievements ───────────────────────────────────────────────────
function renderStreakData(d) {
  if (!d) return;

  const streak = d.streak_count ?? d.current_streak ?? 0;
  setText('streak-count', streak);

  const fireEl = el('streak-fire');
  if (fireEl) fireEl.textContent = streak > 0 ? '🔥' : '💤';

  const levelEl = el('level-badge');
  if (levelEl) levelEl.textContent = `Lvl ${d.level ?? 1}`;
  setText('level-title', d.level_title ?? 'Rookie');

  const xp = d.xp ?? 0;
  const xpNext = d.next_level_xp ?? d.xp_to_next_level ?? 100;
  const pct = Math.min((xp / xpNext) * 100, 100);
  setText('xp-text', `${xp} XP`);
  setText('checkin-total', `${d.total_checkins ?? 0} total days`);
  setText('xp-progress-label', `${xp} / ${xpNext} XP`);
  const bar = el('xp-bar');
  if (bar) bar.style.width = pct + '%';

  // Week dots
  const dotsEl = el('week-dots');
  if (dotsEl) {
    const history = d.checkin_history || d.week_days || [];
    const days = [0,1,2,3,4,5,6].map(offset => {
      const target = new Date();
      target.setDate(target.getDate() - (6 - offset));
      const iso = target.toISOString().split('T')[0];
      return history.includes(iso);
    });
    dotsEl.innerHTML = days.map(done =>
      `<div style="width:10px;height:10px;border-radius:3px;background:${done ? 'var(--q-accent)' : 'rgba(255,255,255,0.1)'}"></div>`
    ).join('');
  }

  // Achievements row (fixed: handle label, icon, avoid undefined)
  if (Array.isArray(d.achievements) && d.achievements.length) {
    const row = el('achievements-row');
    if (row) {
      row.innerHTML = d.achievements.map(a => {
        const label = a.label || a.title || a.name || 'Achievement';
        const icon = a.icon ? `<i class="bi ${a.icon} me-1"></i>` : (a.emoji ? `${a.emoji} ` : '🏅 ');
        return `<span class="q-forecast-badge me-2 mb-2" style="font-size:0.75rem;padding:4px 10px;display:inline-flex;align-items:center;">${icon}${label}</span>`;
      }).join('');
    }

    const latest = d.achievements[d.achievements.length - 1];
    if (latest && d.just_earned) {
      const toast = el('milestone-toast');
      if (toast) {
        setText('milestone-title-icon', latest.icon ? '🏆' : (latest.emoji || '🏆'));
        setText('milestone-title', latest.label || latest.title || 'Achievement Unlocked!');
        setText('milestone-subtitle', latest.desc || latest.description || '');
        toast.style.display = 'flex';
        setTimeout(() => { toast.style.display = 'none'; }, 5000);
      }
    }
  }
}

async function loadStreak() {
  const cached = getCached('streak');
  if (cached) renderStreakData(cached);

  try {
    const res = await apiCall('/api/streak');
    if (res?.data) {
      setCache('streak', res.data);
      renderStreakData(res.data);
      apiCall('/api/streak/checkin', 'POST').catch(() => {});
    }
  } catch (e) {
    console.warn('Streak load error:', e.message);
  }
}

// ─── Dashboard Summary KPIs ───────────────────────────────────────────────────
function renderSummaryData(d) {
  if (!d) return;

  const income   = d.total_income   ?? 0;
  const expenses = d.total_expenses ?? 0;
  const net      = d.net_savings    ?? 0;

  setText('total-income',   formatCurrency(income));
  setText('total-expenses', formatCurrency(expenses));
  setText('net-savings',    formatCurrency(net));

  // Study hours: show monthly if available, with total in subtitle
  const studyMonth = d.study_hours_month ?? d.study_hours ?? 0;
  const studyTotal = d.study_hours ?? 0;
  setText('study-hours', studyMonth.toFixed(1));
  const studySub = el('study-hours-sub');
  if (studySub) {
    studySub.textContent = studyTotal > studyMonth && studyMonth > 0
      ? `hrs this month (${studyTotal.toFixed(1)}h total)`
      : (studyMonth === 0 && studyTotal > 0 ? `${studyTotal.toFixed(1)} hrs all-time` : 'hrs this month');
  }

  // Fitness sessions: show monthly if available, with total in subtitle
  const fitMonth = d.fitness_sessions_month ?? d.fitness_sessions ?? 0;
  const fitTotal = d.fitness_sessions ?? 0;
  setText('fitness-sessions', fitMonth);
  const fitSub = el('fitness-sessions-sub');
  if (fitSub) {
    fitSub.textContent = fitTotal > fitMonth && fitMonth > 0
      ? `sessions this month (${fitTotal} total)`
      : (fitMonth === 0 && fitTotal > 0 ? `${fitTotal} sessions all-time` : 'sessions this month');
  }

  // Goals: handle completed goals gracefully
  const activeGoals = d.active_goals ?? 0;
  const totalGoals  = d.total_goals  ?? activeGoals;
  const compGoals   = d.completed_goals ?? (totalGoals - activeGoals);

  const goalSub = el('dash-goals-sub');
  if (activeGoals === 0 && totalGoals > 0) {
    setText('active-goals', totalGoals);
    if (goalSub) goalSub.textContent = `All ${totalGoals} goals completed! 🏆`;
  } else {
    setText('active-goals', activeGoals);
    if (goalSub) {
      goalSub.textContent = compGoals > 0
        ? `${activeGoals} in progress (${compGoals} done)`
        : 'Goals in progress';
    }
  }

  const rate = income > 0 ? Math.round((net / income) * 100) : 0;
  setText('savings-rate-display', rate + '%');
  setText('savings-rate-pct',     rate + '%');
  const status = rate >= 20 ? '✅ On track — great savings habit!' :
                rate >= 10 ? '⚠️ Moderate — aim for 20%+' :
                             '❌ Low savings rate — review spending';
  setText('savings-rate-status', status);

  // ── Digital Twin Health Score & Morning Briefing ──
  if (d.health_score) {
    const hs = d.health_score;
    setText('health-score-val', hs.score ?? '—');
    setText('health-score-label', hs.label ?? 'Digital Twin Active');

    // Animate SVG Radial Gauge
    const ring = el('health-ring-fill');
    if (ring) {
      const circumference = 314.15; // 2 * PI * r (r=50)
      const pct = Math.min(100, Math.max(0, hs.score ?? 0)) / 100;
      const offset = circumference - (pct * circumference);
      ring.style.strokeDashoffset = offset;

      if (hs.score >= 85) ring.style.stroke = '#10b981';
      else if (hs.score >= 70) ring.style.stroke = '#0071e3';
      else if (hs.score >= 50) ring.style.stroke = '#f59e0b';
      else ring.style.stroke = '#ef4444';
    }

    const badgeEl = el('health-score-badge');
    if (badgeEl) {
      badgeEl.className = `badge bg-${hs.badge || 'primary'} px-3 py-1 rounded-pill`;
      badgeEl.textContent = hs.label || 'Digital Twin AI';
    }

    // Breakdown Mini-bars
    if (hs.breakdown) {
      const fin = hs.breakdown.finance ?? 0;
      const hab = hs.breakdown.habits ?? 0;
      const std = hs.breakdown.study ?? 0;
      const life = hs.breakdown.goals_fitness ?? 0;

      setText('score-breakdown-fin', `${fin}/25`);
      setText('score-breakdown-hab', `${hab}/25`);
      setText('score-breakdown-std', `${std}/25`);
      setText('score-breakdown-life', `${life}/25`);

      const bFin = el('bar-breakdown-fin'); if (bFin) bFin.style.width = `${(fin / 25) * 100}%`;
      const bHab = el('bar-breakdown-hab'); if (bHab) bHab.style.width = `${(hab / 25) * 100}%`;
      const bStd = el('bar-breakdown-std'); if (bStd) bStd.style.width = `${(std / 25) * 100}%`;
      const bLife = el('bar-breakdown-life'); if (bLife) bLife.style.width = `${(life / 25) * 100}%`;
    }

    // Morning Briefing List
    const briefingList = el('morning-briefing-list');
    if (briefingList && hs.morning_briefing) {
      briefingList.innerHTML = hs.morning_briefing.map(bullet => `
        <li class="mb-2 d-flex align-items-start gap-2" style="font-size: 0.88rem; line-height: 1.4; color: var(--q-text);">
          <span class="mt-1" style="font-size:0.9rem;">🔹</span>
          <span style="color: var(--q-text); font-weight: 500;">${bullet}</span>
        </li>
      `).join('');
    }
  }
}

async function loadSummary() {
  const cached = getCached('summary');
  if (cached) renderSummaryData(cached);

  try {
    const res = await apiCall('/api/dashboard/summary');
    if (res?.data) {
      setCache('summary', res.data);
      renderSummaryData(res.data);
    }
  } catch (e) {
    console.warn('Summary load error:', e.message);
  }
}

// ─── Income Trajectory Chart ─────────────────────────────────────────────────
function renderIncomeChart(trend) {
  const labels = Object.keys(trend || {}).sort();
  const values = labels.map(k => trend[k]);

  const ctx = el('incomeChart');
  if (!ctx) return;
  if (incomeChartInst) incomeChartInst.destroy();

  incomeChartInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Income',
        data: values,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16,185,129,0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: '#10b981',
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', maxTicksLimit: 6 } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', callback: v => '₹' + (v/1000).toFixed(0) + 'k' } }
      }
    }
  });
}

async function loadIncomeChart() {
  const cached = getCached('income_trend');
  if (cached) renderIncomeChart(cached);

  try {
    const res = await apiCall('/api/dashboard/income-trend');
    if (res?.data) {
      setCache('income_trend', res.data);
      renderIncomeChart(res.data);
    }
  } catch (e) {
    console.warn('Income chart error:', e.message);
  }
}

// ─── Expense Composition Donut ────────────────────────────────────────────────
function renderExpenseChart(breakdown) {
  const labels = Object.keys(breakdown || {});
  const values = Object.values(breakdown || {});

  const ctx = el('expenseChart');
  if (!ctx) return;
  if (expenseChartInst) expenseChartInst.destroy();

  if (!labels.length) {
    const parent = ctx.parentElement;
    if (parent) parent.innerHTML = `<div class="q-empty py-4"><div class="q-empty-icon" style="font-size:2rem;">📊</div><div class="q-empty-title">No expense data yet</div></div>`;
    return;
  }

  expenseChartInst = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: PALETTE,
        borderColor: 'rgba(255,255,255,0.05)',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 }, boxWidth: 12, padding: 12 } }
      },
      cutout: '65%',
    }
  });
}

async function loadExpenseChart() {
  const cached = getCached('expense_breakdown');
  if (cached) renderExpenseChart(cached);

  try {
    const res = await apiCall('/api/dashboard/expense-breakdown');
    if (res?.data) {
      setCache('expense_breakdown', res.data);
      renderExpenseChart(res.data);
    }
  } catch (e) {
    console.warn('Expense chart error:', e.message);
  }
}

// ─── Study Chart ──────────────────────────────────────────────────────────────
function renderStudyChart(trend) {
  const labels = Object.keys(trend || {}).sort();
  const values = labels.map(k => parseFloat((trend[k] || 0).toFixed(1)));

  const ctx = el('studyChart');
  if (!ctx) return;
  if (studyChartInst) studyChartInst.destroy();

  studyChartInst = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Study Hours',
        data: values,
        backgroundColor: 'rgba(6,182,212,0.7)',
        borderColor: '#06b6d4',
        borderWidth: 1,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#64748b', maxTicksLimit: 5 } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } }
      }
    }
  });
}

async function loadStudyChart() {
  const cached = getCached('study_trend');
  if (cached) renderStudyChart(cached);

  try {
    const res = await apiCall('/api/dashboard/study-trend');
    if (res?.data) {
      setCache('study_trend', res.data);
      renderStudyChart(res.data);
    }
  } catch (e) {
    console.warn('Study chart error:', e.message);
  }
}

// ─── Fitness Radar Chart ─────────────────────────────────────────────────────
function renderFitnessChart(records) {
  const byType = {};
  (records || []).forEach(r => {
    const t = (r.activity_type || 'Other');
    byType[t] = (byType[t] || 0) + 1;
  });
  const labels = Object.keys(byType);
  const values = Object.values(byType);

  const ctx = el('fitnessRadarChart');
  if (!ctx) return;
  if (fitnessChartInst) fitnessChartInst.destroy();

  if (!labels.length) {
    const parent = ctx.parentElement;
    if (parent) parent.innerHTML = `<div class="q-empty py-4"><div class="q-empty-icon" style="font-size:2rem;">🏃</div><div class="q-empty-title">No fitness data yet</div></div>`;
    return;
  }

  fitnessChartInst = new Chart(ctx, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Sessions',
        data: values,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245,158,11,0.15)',
        pointBackgroundColor: '#f59e0b',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        r: {
          grid: { color: 'rgba(255,255,255,0.06)' },
          ticks: { color: '#64748b', backdropColor: 'transparent' },
          pointLabels: { color: '#94a3b8', font: { size: 11 } }
        }
      }
    }
  });
}

async function loadFitnessChart() {
  const cached = getCached('fitness');
  if (cached) renderFitnessChart(cached);

  try {
    const res = await apiCall('/api/fitness');
    if (res?.data) {
      setCache('fitness', res.data);
      renderFitnessChart(res.data);
    }
  } catch (e) {
    console.warn('Fitness chart error:', e.message);
  }
}

// ─── Goals Chart & Progress List ──────────────────────────────────────────────
function renderGoalsData(goals) {
  const list = goals || [];

  // Count by status
  const counts = { 'not-started': 0, 'in-progress': 0, 'completed': 0, 'abandoned': 0 };
  list.forEach(g => {
    const s = (g.status || 'not-started').toLowerCase().replace(/_/g, '-');
    if (s in counts) counts[s]++;
    else counts['in-progress']++;
  });

  const ctx = el('goalsChart');
  if (ctx) {
    if (goalsChartInst) goalsChartInst.destroy();
    goalsChartInst = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Not Started', 'In Progress', 'Completed', 'Abandoned'],
        datasets: [{
          data: Object.values(counts),
          backgroundColor: ['#64748b', '#7c3aed', '#10b981', '#ef4444'],
          borderColor: 'rgba(255,255,255,0.05)',
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 }, boxWidth: 12, padding: 8 } }
        },
        cutout: '60%'
      }
    });
  }

  // Goal progress list (fixed: handles progress_percent, progress, displays active first)
  const container = el('dash-goal-progress');
  if (container) {
    const active = list.filter(g => {
      const s = (g.status || '').toLowerCase().replace(/_/g, '-');
      return s !== 'completed' && s !== 'abandoned';
    });
    const displayGoals = (active.length > 0 ? active : list).slice(0, 5);

    if (!displayGoals.length) {
      container.innerHTML = `
        <div class="q-empty py-4 text-center">
          <div class="q-empty-icon" style="font-size:2.2rem;margin-bottom:8px;">🎯</div>
          <div class="q-empty-title" style="font-weight:600;">No active goals</div>
          <div class="q-empty-sub"><a href="/goals" style="color:var(--q-accent-light);text-decoration:underline;">Create a goal to start tracking</a></div>
        </div>`;
    } else {
      container.innerHTML = displayGoals.map(g => {
        const rawPct = g.progress_percent ?? g.progress ?? (g.status === 'completed' ? 100 : (g.status === 'not-started' ? 0 : 35));
        const pct = Math.min(Math.max(Math.round(Number(rawPct) || 0), 0), 100);
        const isDone = g.status === 'completed' || pct >= 100;
        const statusBadge = isDone ? `<span class="badge bg-success-subtle text-success ms-2" style="font-size:0.68rem;">Done</span>` : '';
        return `
          <div class="mb-3">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <span style="color:var(--q-text);font-size:0.88rem;font-weight:500;">${g.title || 'Goal'}${statusBadge}</span>
              <span style="color:var(--q-muted);font-size:0.8rem;font-weight:600;">${pct}%</span>
            </div>
            <div class="q-progress">
              <div class="q-progress-fill" style="width:${pct}%;background:${isDone ? '#10b981' : 'var(--q-accent)'};"></div>
            </div>
          </div>`;
      }).join('');
    }
  }
}

async function loadGoalsChart() {
  const cached = getCached('goals');
  if (cached) renderGoalsData(cached);

  try {
    const res = await apiCall('/api/goals');
    if (res?.data) {
      setCache('goals', res.data);
      renderGoalsData(res.data);
    }
  } catch (e) {
    console.warn('Goals chart error:', e.message);
  }
}

// ─── Recent Activity (Fixed: handles summary, action, entity_type) ───────────
function renderRecentActivity(items) {
  const container = el('recent-activity');
  if (!container) return;

  const list = items || [];
  if (!list.length) {
    container.innerHTML = `<div class="q-empty py-4 text-center"><div class="q-empty-icon" style="font-size:2rem;margin-bottom:8px;">📋</div><div class="q-empty-title">No recent activity</div></div>`;
    return;
  }

  const icons = {
    income: '💰',
    expenses: '💸',
    expense: '💸',
    study: '📚',
    study_records: '📚',
    habits: '✅',
    habit: '✅',
    fitness: '🏃',
    fitness_records: '🏃',
    goals: '🎯',
    goal: '🎯',
    savings: '🏦',
    system: '⚡',
  };

  container.innerHTML = `<div class="list-group list-group-flush">`
    + list.map(item => {
        const type = (item.entity_type || item.type || '').toLowerCase();
        const icon = icons[type] || '📌';
        const text = item.summary || (item.action ? `${item.action.toUpperCase()} ${type}` : (item.description || 'Activity recorded'));
        const dateVal = item.timestamp || item.created_at || item.date;
        let date = '';
        if (dateVal) {
          try {
            const d = new Date(dateVal);
            date = isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
          } catch(e) {}
        }

        return `
          <div class="list-group-item list-group-item-action" style="background:transparent;border-color:rgba(255,255,255,0.06);padding:12px 4px;">
            <div class="d-flex justify-content-between align-items-center">
              <div class="d-flex align-items-center gap-2">
                <span style="font-size:1.1rem;">${icon}</span>
                <span style="color:var(--q-text);font-size:0.88rem;font-weight:500;">${text}</span>
              </div>
              <small style="color:var(--q-muted);font-size:0.78rem;">${date}</small>
            </div>
          </div>`;
      }).join('')
    + `</div>`;
}

async function loadRecentActivity() {
  const cached = getCached('recent_activity');
  if (cached) renderRecentActivity(cached);

  try {
    const res = await apiCall('/api/dashboard/recent-activity');
    if (res?.data) {
      setCache('recent_activity', res.data);
      renderRecentActivity(res.data);
    }
  } catch (e) {
    console.warn('Recent activity error:', e.message);
  }
}

// ─── ML Finance Forecast ──────────────────────────────────────────────────────
function renderFinanceForecast(d) {
  if (!d) return;

  const total = d.projected_30d_expenses ?? d.predicted_total ?? 0;
  setText('ai-finance-forecast', formatCurrency(total));
  const trend = d.expense_trend ?? d.trend ?? 'stable';
  const trendIcon = trend === 'upward' || trend === 'increasing' ? '📈' : trend === 'downward' || trend === 'decreasing' ? '📉' : '➡️';
  setText('ai-finance-trend', `${trendIcon} Trend: ${trend.charAt(0).toUpperCase() + trend.slice(1)}`);
  setText('ai-finance-insight', d.insight ?? 'Model analyzed your spending patterns.');

  const history = (d.history || []).map(h => typeof h === 'object' ? h.amount : h);
  const predicted = (d.forecast || d.predictions || []).map(f => typeof f === 'object' ? f.amount : f);
  const ctx = el('ai-finance-chart');
  if (ctx && (history.length || predicted.length)) {
    if (aiFinanceChartInst) aiFinanceChartInst.destroy();
    aiFinanceChartInst = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [...history.map((_, i) => `W-${history.length - i}`), ...predicted.map((_, i) => `W+${i + 1}`)],
        datasets: [
          { label: 'Historical', data: history, borderColor: '#94a3b8', borderWidth: 1.5, pointRadius: 2, tension: 0.3, fill: false },
          { label: 'Predicted',  data: [...Array(history.length).fill(null), ...predicted], borderColor: '#7c3aed', borderDash: [4, 3], borderWidth: 2, pointRadius: 3, tension: 0.3, fill: false },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#94a3b8', font: { size: 10 } } } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', font: { size: 9 } } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', font: { size: 9 }, callback: v => '₹' + (v/1000).toFixed(0) + 'k' } }
        }
      }
    });
  }

  const breakdown = d.category_breakdown || d.breakdown;
  if (breakdown) {
    const bdEl = el('ai-finance-breakdown');
    if (bdEl) {
      if (Array.isArray(breakdown)) {
        bdEl.innerHTML = breakdown.slice(0, 4).map(item =>
          `<div class="d-flex justify-content-between mb-1"><span style="color:var(--q-muted);font-size:0.8rem;">${item.category}</span><span style="color:var(--q-text);font-size:0.8rem;font-weight:600;">${formatCurrency(item.total)} (${item.pct}%)</span></div>`
        ).join('');
      } else {
        bdEl.innerHTML = Object.entries(breakdown).map(([cat, val]) =>
          `<div class="d-flex justify-content-between mb-1"><span style="color:var(--q-muted);font-size:0.8rem;">${cat}</span><span style="color:var(--q-text);font-size:0.8rem;font-weight:600;">${formatCurrency(val)}</span></div>`
        ).join('');
      }
    }
  }
}

async function loadFinanceForecast() {
  const cached = getCached('ml_finance');
  if (cached) renderFinanceForecast(cached);

  try {
    const res = await apiCall('/api/ml/finance/forecast');
    if (res?.data) {
      setCache('ml_finance', res.data);
      renderFinanceForecast(res.data);
    }
  } catch (e) {
    setText('ai-finance-forecast', 'Not enough data');
    setText('ai-finance-trend', 'Add more expense records to unlock ML insights.');
    setText('ai-finance-insight', '');
  }
}

// ─── ML Study Forecast ────────────────────────────────────────────────────────
function renderStudyForecast(d) {
  if (!d) return;

  const hrs = d.projected_7d_study_hrs != null ? d.projected_7d_study_hrs.toFixed(1) : ((d.predicted_minutes ?? d.projected_7d_study_mins ?? 0) / 60).toFixed(1);
  setText('ai-study-forecast', hrs + ' hrs');
  const trend = d.study_trend ?? d.trend ?? 'stable';
  const icon = trend === 'upward' || trend === 'increasing' ? '📈' : trend === 'downward' || trend === 'decreasing' ? '📉' : '➡️';
  setText('ai-study-trend', `${icon} Momentum: ${trend}`);
  setText('ai-study-insight', d.insight ?? 'Based on your recent study sessions.');

  const history  = (d.history || []).map(h => typeof h === 'object' ? (h.stu || h.amount || 0) : h);
  const predicted = (d.forecast || d.predictions || []).map(f => typeof f === 'object' ? (f.stu || f.amount || 0) : f);
  const ctx = el('ai-study-chart');
  if (ctx && (history.length || predicted.length)) {
    if (aiStudyChartInst) aiStudyChartInst.destroy();
    aiStudyChartInst = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [...history.map((_, i) => `D-${history.length - i}`), ...predicted.map((_, i) => `D+${i + 1}`)],
        datasets: [
          { label: 'Historical', data: history.map(v => parseFloat((v / 60).toFixed(1))), borderColor: '#94a3b8', borderWidth: 1.5, pointRadius: 2, tension: 0.3, fill: false },
          { label: 'Predicted',  data: [...Array(history.length).fill(null), ...predicted.map(v => parseFloat((v / 60).toFixed(1)))], borderColor: '#06b6d4', borderDash: [4, 3], borderWidth: 2, pointRadius: 3, tension: 0.3, fill: false },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#94a3b8', font: { size: 10 } } } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', font: { size: 9 } } },
          y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', font: { size: 9 }, callback: v => v + 'h' } }
        }
      }
    });
  }
}

async function loadStudyForecast() {
  const cached = getCached('ml_study');
  if (cached) renderStudyForecast(cached);

  try {
    const res = await apiCall('/api/ml/study/forecast');
    if (res?.data) {
      setCache('ml_study', res.data);
      renderStudyForecast(res.data);
    }
  } catch (e) {
    setText('ai-study-forecast', 'Not enough data');
    setText('ai-study-trend', 'Log more study sessions to enable ML predictions.');
    setText('ai-study-insight', '');
  }
}

// ─── Habit Churn Risk ─────────────────────────────────────────────────────────
let currentShieldHabit = null;

function renderHabitRisk(habits) {
  const container = el('ai-habit-risk-row');
  if (!container) return;

  const list = habits || [];
  if (!list.length) {
    container.innerHTML = `<div class="col-12 q-empty py-4"><div class="q-empty-icon">✅</div><div class="q-empty-title">No habits found</div><div class="q-empty-sub">Add habits to see churn risk predictions.</div></div>`;
    return;
  }

  const sorted = [...list].sort((a, b) => (b.churn_probability ?? 0) - (a.churn_probability ?? 0));
  container.innerHTML = sorted.slice(0, 6).map(h => {
    const prob = Math.round((h.churn_probability ?? 0) * 100);
    const riskLevel = prob >= 70 ? 'high' : prob >= 40 ? 'medium' : 'low';
    const riskColor = { high: '#ef4444', medium: '#f59e0b', low: '#10b981' }[riskLevel];
    const riskLabel = { high: 'High Risk', medium: 'Moderate', low: 'Stable' }[riskLevel];
    const isShielded = h.streak_protected;

    return `
      <div class="col-md-4 col-sm-6">
        <div class="q-card p-3 h-100 d-flex flex-column justify-content-between">
          <div>
            <div class="d-flex justify-content-between align-items-start mb-2">
              <span style="font-weight:600;color:var(--q-text);font-size:0.9rem;">${h.name ?? 'Habit'}</span>
              <span class="q-confidence ${riskLevel}" style="font-size:0.72rem;">${riskLabel}</span>
            </div>
            <div class="q-progress mb-1">
              <div class="q-progress-fill" style="width:${prob}%;background:linear-gradient(90deg,${riskColor},${riskColor}88);"></div>
            </div>
            <div class="d-flex justify-content-between mb-2">
              <small style="color:var(--q-muted);">Churn risk</small>
              <small style="color:${riskColor};font-weight:600;">${prob}%</small>
            </div>
          </div>
          <div>
            <div class="d-flex justify-content-between align-items-center mb-2">
              <small style="color:var(--q-muted);font-size:0.75rem;">Streak: ${h.current_streak ?? h.streak ?? 0} days</small>
              ${isShielded ? `<span class="badge bg-success" style="font-size:0.65rem;">🛡️ Shielded</span>` : ''}
            </div>
            <button class="btn btn-outline-primary btn-sm w-100 btn-shield-habit" 
                    data-habit-id="${h.id || h.doc_id || ''}" 
                    data-habit-name="${h.name || 'Habit'}" 
                    data-risk="${prob}"
                    style="font-size: 0.78rem; font-weight: 600;">
              🛡️ Shield Streak
            </button>
          </div>
        </div>
      </div>`;
  }).join('');

  container.querySelectorAll('.btn-shield-habit').forEach(btn => {
    btn.addEventListener('click', () => {
      const habitId = btn.getAttribute('data-habit-id');
      const habitName = btn.getAttribute('data-habit-name');
      const risk = btn.getAttribute('data-risk');
      openShieldModal(habitId, habitName, risk);
    });
  });
}

function openShieldModal(id, name, risk) {
  currentShieldHabit = { id, name, risk };
  setText('shield-habit-name', name);
  setText('shield-risk-label', `${risk}% Churn Risk predicted by ML model.`);
  setText('shield-risk-badge', risk >= 70 ? 'HIGH RISK' : risk >= 40 ? 'MEDIUM RISK' : 'STABLE');

  const check = el('micro-task-check');
  const btnTask = el('btn-submit-micro-task');
  if (check) check.checked = false;
  if (btnTask) btnTask.disabled = true;

  const modalEl = el('habit-shield-modal');
  if (modalEl && window.bootstrap) {
    const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  }
}

function initHabitShield() {
  const check = el('micro-task-check');
  const btnTask = el('btn-submit-micro-task');
  const btnFreeze = el('btn-submit-xp-freeze');

  if (check && btnTask) {
    check.addEventListener('change', () => {
      btnTask.disabled = !check.checked;
    });
  }

  if (btnTask) {
    btnTask.addEventListener('click', async () => {
      if (!currentShieldHabit?.id) return;
      btnTask.disabled = true;
      btnTask.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Shielding...';
      try {
        const res = await apiCall(`/api/habits/${currentShieldHabit.id}/shield`, 'POST', { action: 'micro_task' });
        showToast(res.message || 'Streak shielded successfully!', 'success');
        const modalEl = el('habit-shield-modal');
        if (modalEl && window.bootstrap) {
          const modal = window.bootstrap.Modal.getInstance(modalEl);
          if (modal) modal.hide();
        }
        clearDashboardCache();
        loadSummary();
        loadStreak();
        loadHabitRisk();
      } catch (e) {
        showToast('Shield failed: ' + e.message, 'danger');
      } finally {
        btnTask.disabled = false;
        btnTask.innerHTML = '<i class="bi bi-shield-check me-1"></i> Shield Streak (+10 XP)';
      }
    });
  }

  if (btnFreeze) {
    btnFreeze.addEventListener('click', async () => {
      if (!currentShieldHabit?.id) return;
      btnFreeze.disabled = true;
      btnFreeze.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Freezing...';
      try {
        const res = await apiCall(`/api/habits/${currentShieldHabit.id}/shield`, 'POST', { action: 'xp_freeze' });
        showToast(res.message || 'Streak Freeze activated!', 'success');
        const modalEl = el('habit-shield-modal');
        if (modalEl && window.bootstrap) {
          const modal = window.bootstrap.Modal.getInstance(modalEl);
          if (modal) modal.hide();
        }
        clearDashboardCache();
        loadSummary();
        loadStreak();
        loadHabitRisk();
      } catch (e) {
        showToast('Streak Freeze failed: ' + e.message, 'danger');
      } finally {
        btnFreeze.disabled = false;
        btnFreeze.innerHTML = '<i class="bi bi-snow2 me-1"></i> Use 30 XP Freeze';
      }
    });
  }
}

async function loadHabitRisk() {
  const cached = getCached('ml_habit_risk');
  if (cached) renderHabitRisk(cached);

  try {
    const res = await apiCall('/api/ml/habit/all/risk');
    if (res?.data) {
      setCache('ml_habit_risk', res.data);
      renderHabitRisk(res.data);
    }
  } catch (e) {
    const container = el('ai-habit-risk-row');
    if (container) container.innerHTML = `<div class="col-12 q-muted-text text-center py-3">Add habits to see ML risk predictions.</div>`;
  }
}

// ─── Simulation Chart ────────────────────────────────────────────────────────
function populateScenarioSelect(category) {
  const select = el('sim-scenario-select');
  if (!select) return;
  const scenarios = SIM_SCENARIOS[category] || [];
  select.innerHTML = scenarios.map(s => `<option value="${s.value}">${s.label}</option>`).join('');
}

async function renderSimChart() {
  const category = (el('sim-category-select')?.value) || 'financial';
  const scenarioVal = el('sim-scenario-select')?.value;
  const scenarios = SIM_SCENARIOS[category] || [];
  const scenario = scenarios.find(s => s.value === scenarioVal) || scenarios[0];
  if (!scenario) return;

  setText('sim-scenario-label', scenario.label);

  let baseValues = [0, 0, 0, 0, 0, 0];
  let labels = ['Month 1','Month 2','Month 3','Month 4','Month 5','Month 6'];

  const incomeCached = getCached('income_trend');
  const studyCached  = getCached('study_trend');

  if (category === 'financial' && incomeCached && Object.keys(incomeCached).length > 0) {
    const sorted = Object.keys(incomeCached).sort();
    labels = sorted;
    baseValues = sorted.map(k => incomeCached[k]);
  } else if (category === 'productivity' && studyCached && Object.keys(studyCached).length > 0) {
    const sorted = Object.keys(studyCached).sort();
    labels = sorted;
    baseValues = sorted.map(k => studyCached[k]);
  }

  const simValues = baseValues.map(v => scenario.fn(v));

  const ctx = el('simChart');
  if (!ctx) return;
  if (simChartInst) simChartInst.destroy();

  simChartInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Current',       data: baseValues, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3 },
        { label: scenario.label, data: simValues,  borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.08)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3, borderDash: [5, 4] },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b', maxTicksLimit: 6 } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#64748b' } }
      }
    }
  });
}

function initSimulation() {
  const catSelect = el('sim-category-select');
  const scSelect  = el('sim-scenario-select');
  if (!catSelect || !scSelect) return;

  populateScenarioSelect(catSelect.value);
  renderSimChart();

  catSelect.addEventListener('change', () => {
    populateScenarioSelect(catSelect.value);
    renderSimChart();
  });
  scSelect.addEventListener('change', renderSimChart);
}

// ─── High-Speed Bootstrap Loader ─────────────────────────────────────────────
function applyBootstrapData(d) {
  if (!d) return;
  if (d.streak) {
    setCache('streak', d.streak);
    renderStreakData(d.streak);
  }
  if (d.summary) {
    setCache('summary', d.summary);
    renderSummaryData(d.summary);
  }
  if (d.income_trend) {
    setCache('income_trend', d.income_trend);
    renderIncomeChart(d.income_trend);
  }
  if (d.expense_breakdown) {
    setCache('expense_breakdown', d.expense_breakdown);
    renderExpenseChart(d.expense_breakdown);
  }
  if (d.study_trend) {
    setCache('study_trend', d.study_trend);
    renderStudyChart(d.study_trend);
  }
  if (d.fitness) {
    setCache('fitness', d.fitness);
    renderFitnessChart(d.fitness);
  }
  if (d.goals) {
    setCache('goals', d.goals);
    renderGoalsData(d.goals);
  }
  if (d.recent_activity) {
    setCache('recent_activity', d.recent_activity);
    renderRecentActivity(d.recent_activity);
  }
}

async function loadDashboardBootstrap() {
  const cachedBoot = getCached('bootstrap');
  if (cachedBoot) {
    applyBootstrapData(cachedBoot);
  } else {
    // If no full bootstrap in cache, check individual caches for instant 0ms painting
    const cStreak = getCached('streak'); if (cStreak) renderStreakData(cStreak);
    const cSum = getCached('summary'); if (cSum) renderSummaryData(cSum);
    const cInc = getCached('income_trend'); if (cInc) renderIncomeChart(cInc);
    const cExp = getCached('expense_breakdown'); if (cExp) renderExpenseChart(cExp);
    const cStd = getCached('study_trend'); if (cStd) renderStudyChart(cStd);
    const cFit = getCached('fitness'); if (cFit) renderFitnessChart(cFit);
    const cGoal = getCached('goals'); if (cGoal) renderGoalsData(cGoal);
    const cAct = getCached('recent_activity'); if (cAct) renderRecentActivity(cAct);
  }

  try {
    const res = await apiCall('/api/dashboard/bootstrap');
    if (res?.data) {
      setCache('bootstrap', res.data);
      applyBootstrapData(res.data);
      apiCall('/api/streak/checkin', 'POST').catch(() => {});
    }
  } catch (e) {
    console.warn('Bootstrap API failed, falling back to separate endpoints:', e.message);
    await Promise.allSettled([
      loadStreak(),
      loadSummary(),
      loadIncomeChart(),
      loadExpenseChart(),
      loadStudyChart(),
      loadFitnessChart(),
      loadGoalsChart(),
      loadRecentActivity(),
    ]);
  }
}

async function loadMLForecasts() {
  const cachedFinance = getCached('ml_finance');
  if (cachedFinance) renderFinanceForecast(cachedFinance);
  const cachedStudy = getCached('ml_study');
  if (cachedStudy) renderStudyForecast(cachedStudy);
  const cachedHabit = getCached('ml_habit_risk');
  if (cachedHabit) renderHabitRisk(cachedHabit);

  try {
    const res = await apiCall('/api/ml/summary');
    if (res?.data) {
      if (res.data.finance) {
        setCache('ml_finance', res.data.finance);
        renderFinanceForecast(res.data.finance);
      }
      if (res.data.study) {
        setCache('ml_study', res.data.study);
        renderStudyForecast(res.data.study);
      }
      if (res.data.habits) {
        setCache('ml_habit_risk', res.data.habits);
        renderHabitRisk(res.data.habits);
      }
      return;
    }
  } catch (e) {
    // Non-blocking fallback to individual calls
    loadFinanceForecast().catch(() => {});
    loadStudyForecast().catch(() => {});
    loadHabitRisk().catch(() => {});
  }
}

// ─── Main Init (Protected against duplicate triggering) ──────────────────────
let isDashInitialized = false;

onAuthChange(async user => {
  if (!user) {
    activeUserId = null;
    return;
  }

  if (activeUserId !== user.uid) {
    activeUserId = user.uid;
    clearDashboardCache();
    isDashInitialized = false;
  } else if (isDashInitialized) {
    return;
  }
  isDashInitialized = true;

  setGreeting();

  // Instant Bootstrap: Loads ALL core dashboard data in 1 single round-trip
  await loadDashboardBootstrap();

  // Load ML forecasts asynchronously in background without blocking UI
  loadMLForecasts();

  initSimulation();
  initHabitShield();
});