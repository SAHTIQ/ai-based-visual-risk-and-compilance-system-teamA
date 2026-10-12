/**
 * QUANTA — AI Assistant Chatbot Frontend (chat.js)
 * Implements: Time-bucketed thread management, smart routing, markdown + Generative UI widgets,
 * saved insights, right drawer context telemetry, child thread branching, and full-page layout.
 */

import { onAuthChange, getIdToken } from './auth.js';
import { formatCurrency, showToast } from './api.js';

// ── State Variables ──────────────────────────────────────────────────────────
let activeThreadId = null;
let activeThreadTitle = "Digital Twin Intelligence";
let threadsList = [];
let _chatInitialized = false;

// ── Auth ─────────────────────────────────────────────────────────────────────
onAuthChange(user => {
  if (!user && window.location.pathname !== '/login') {
    window.location.href = '/login';
    return;
  }
  if (user && !_chatInitialized) {
    _chatInitialized = true;
    initChatPage();
  }
});

async function getToken(forceRefresh = false) {
  return await getIdToken(forceRefresh);
}

// ── DOM References ───────────────────────────────────────────────────────────
const threadListEl = document.getElementById('q-thread-list');
const messagesFeedEl = document.getElementById('q-messages-feed');
const feedContainerEl = document.getElementById('q-feed-container');
const inputEl = document.getElementById('q-chat-input');
const sendBtn = document.getElementById('q-btn-send');
const newChatBtn = document.getElementById('btn-new-chat');
const btnNewThreadHeader = document.getElementById('btn-new-thread');
const searchThreadsEl = document.getElementById('q-search-threads');
const chatsCountEl = document.getElementById('q-chats-count');
const activeTitleEl = document.getElementById('q-active-thread-title');
const activeTagsEl = document.getElementById('q-active-thread-tags');
const renameThreadBtn = document.getElementById('btn-rename-thread');
const routingModeSelect = document.getElementById('q-routing-mode');
const toggleHistoryBtn = document.getElementById('toggle-history-btn');
const toggleContextBtn = document.getElementById('toggle-context-btn');
const btnCloseContext = document.getElementById('btn-close-context');
const toggleFullWorkspaceBtn = document.getElementById('toggle-full-workspace-btn');
const chatSidebarEl = document.getElementById('q-chat-sidebar');
const chatContextPanelEl = document.getElementById('q-chat-context-panel');

// Context Panel DOM References
const ctxProdScoreEl = document.getElementById('ctx-prod-score');
const ctxProdConsistencyEl = document.getElementById('ctx-prod-consistency');
const ctxHabitsValEl = document.getElementById('ctx-habits-val');
const ctxStudyValEl = document.getElementById('ctx-study-val');
const ctxSourcesCountEl = document.getElementById('ctx-sources-count');
const ctxInsightsCountEl = document.getElementById('ctx-insights-count');
const qContextSourcesEl = document.getElementById('q-context-sources');
const savedInsightsContainer = document.getElementById('q-saved-insights-container');

function getTargetContainer() {
  return feedContainerEl || messagesFeedEl;
}

// ── API Helpers ──────────────────────────────────────────────────────────────
async function fetchApi(url, options = {}, isRetry = false) {
  const token = await getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };
  
  let res = await fetch(url, { ...options, headers });
  
  // If unauthorized / token expired, transparently refresh token once and replay request
  if (res.status === 401 && !isRetry) {
    console.warn(`[Chat] 401 received for ${url}. Attempting silent token refresh...`);
    try {
      const newToken = await getToken(true);
      if (newToken) {
        const retryHeaders = {
          ...headers,
          'Authorization': `Bearer ${newToken}`
        };
        res = await fetch(url, { ...options, headers: retryHeaders });
      }
    } catch (refreshErr) {
      console.error('[Chat] Silent token refresh failed:', refreshErr);
    }
  }

  let data;
  try {
    data = await res.json();
  } catch (err) {
    throw new Error('Server returned an unparseable response.');
  }

  if (!res.ok || !data.success) {
    throw new Error(data.error || 'Request failed');
  }
  return data.data;
}

// ── Page Initialization ──────────────────────────────────────────────────────
async function initChatPage() {
  initWorkspaceMode();
  setupEventListeners();
  await loadThreads();
  await loadContextSummary();
}

function initWorkspaceMode() {
  const saved = localStorage.getItem('quanta_chat_extended_mode');
  // Default to true (Extended Full Window Workspace Mode)
  const isExtended = saved === null ? true : saved === 'true';
  setExtendedWorkspace(isExtended);

  if (toggleFullWorkspaceBtn) {
    toggleFullWorkspaceBtn.addEventListener('click', () => {
      const active = document.body.classList.contains('q-chat-full-workspace');
      setExtendedWorkspace(!active);
    });
  }
}

function setExtendedWorkspace(enabled) {
  if (enabled) {
    document.body.classList.add('q-chat-full-workspace');
    if (toggleFullWorkspaceBtn) {
      toggleFullWorkspaceBtn.innerHTML = `<i class="bi bi-arrows-angle-contract"></i>`;
      toggleFullWorkspaceBtn.title = "Standard View Mode";
    }
  } else {
    document.body.classList.remove('q-chat-full-workspace');
    if (toggleFullWorkspaceBtn) {
      toggleFullWorkspaceBtn.innerHTML = `<i class="bi bi-arrows-angle-expand"></i>`;
      toggleFullWorkspaceBtn.title = "Extended Full Window Workspace Mode";
    }
  }
  localStorage.setItem('quanta_chat_extended_mode', enabled ? 'true' : 'false');
}

function setupEventListeners() {
  if (newChatBtn) newChatBtn.addEventListener('click', () => handleCreateNewThread());
  if (btnNewThreadHeader) btnNewThreadHeader.addEventListener('click', () => handleCreateNewThread(activeThreadId));
  if (sendBtn) sendBtn.addEventListener('click', handleSendMessage);
  
  if (inputEl) {
    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    });
    inputEl.addEventListener('input', () => {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + 'px';
    });
  }

  if (searchThreadsEl) {
    searchThreadsEl.addEventListener('input', () => renderThreadsList());
  }

  if (renameThreadBtn) {
    renameThreadBtn.addEventListener('click', handleRenameActiveThread);
  }

  // Sidebar & Context toggles
  if (toggleHistoryBtn) {
    toggleHistoryBtn.addEventListener('click', () => {
      if (window.innerWidth <= 992) {
        chatSidebarEl.classList.toggle('open');
        chatContextPanelEl.classList.remove('open');
      } else {
        chatSidebarEl.classList.toggle('collapsed');
      }
    });
  }
  if (toggleContextBtn) {
    toggleContextBtn.addEventListener('click', () => {
      if (window.innerWidth <= 992) {
        chatContextPanelEl.classList.toggle('open');
        chatSidebarEl.classList.remove('open');
      } else {
        chatContextPanelEl.classList.toggle('collapsed');
      }
    });
  }
  if (btnCloseContext) {
    btnCloseContext.addEventListener('click', () => {
      if (window.innerWidth <= 992) {
        chatContextPanelEl.classList.remove('open');
      } else {
        chatContextPanelEl.classList.add('collapsed');
      }
    });
  }
}

// ── Threads Management & Time Bucketing ──────────────────────────────────────
async function loadThreads() {
  try {
    const data = await fetchApi('/api/chat/threads');
    threadsList = data || [];
    if (threadsList.length > 0 && !activeThreadId) {
      activeThreadId = threadsList[0].id;
      activeThreadTitle = threadsList[0].title;
    }
    renderThreadsList();
    if (activeThreadId) {
      const activeObj = threadsList.find(t => t.id === activeThreadId);
      if (activeObj && activeTitleEl) {
        activeTitleEl.textContent = activeObj.title;
        activeThreadTitle = activeObj.title;
      }
      await loadThreadMessages(activeThreadId);
    } else {
      renderWelcomeBanner();
    }
  } catch (err) {
    console.error('Failed to load threads:', err);
    if (threadListEl) threadListEl.innerHTML = `<div class="p-3 text-center text-muted small">Could not load conversations.</div>`;
  }
}

function renderThreadsList() {
  if (!threadListEl) return;

  const searchQuery = (searchThreadsEl?.value || '').toLowerCase().trim();
  const filtered = threadsList.filter(t => {
    return !searchQuery || t.title.toLowerCase().includes(searchQuery) || (t.last_message || '').toLowerCase().includes(searchQuery);
  });

  if (chatsCountEl) {
    chatsCountEl.textContent = `CHATS (${filtered.length})`;
  }

  if (filtered.length === 0) {
    threadListEl.innerHTML = `<div class="p-3 text-center text-muted small">${searchQuery ? 'No matching threads.' : 'No conversations yet.'}</div>`;
    return;
  }

  // Bucket threads into time categories: YESTERDAY, PREVIOUS 7 DAYS, OLDER, ARCHIVED
  const buckets = {
    'YESTERDAY': [],
    'PREVIOUS 7 DAYS': [],
    'OLDER': [],
    'ARCHIVED': []
  };

  filtered.forEach(t => {
    const b = t.time_bucket || (t.archived ? 'ARCHIVED' : 'PREVIOUS 7 DAYS');
    if (buckets[b]) {
      buckets[b].push(t);
    } else {
      buckets['OLDER'].push(t);
    }
  });

  let html = '';
  const bucketOrder = ['YESTERDAY', 'PREVIOUS 7 DAYS', 'OLDER', 'ARCHIVED'];

  bucketOrder.forEach(bucketKey => {
    const items = buckets[bucketKey];
    if (items.length === 0) return;

    html += `<div class="q-thread-bucket-label mt-2">${bucketKey}</div>`;

    items.forEach(t => {
      const isActive = t.id === activeThreadId;
      const tagsStr = (t.tags || ["Productivity", "Behaviour"]).join(" • ");
      html += `
        <div class="q-thread-item ${isActive ? 'active' : ''}" data-thread-id="${t.id}" data-thread-title="${escapeHtml(t.title)}">
          <div class="q-thread-item-header">
            <span class="q-thread-title">${escapeHtml(t.title)}</span>
            <div class="dropdown" onclick="event.stopPropagation();">
              <button class="btn btn-link btn-sm text-muted p-0 border-0" data-bs-toggle="dropdown" aria-expanded="false">
                <i class="bi bi-three-dots-vertical"></i>
              </button>
              <ul class="dropdown-menu dropdown-menu-end shadow-sm" style="font-size:0.8rem;">
                <li><a class="dropdown-item btn-action-rename" href="#" data-id="${t.id}" data-title="${escapeHtml(t.title)}"><i class="bi bi-pencil me-2"></i>Rename</a></li>
                <li><a class="dropdown-item btn-action-archive" href="#" data-id="${t.id}" data-archived="${t.archived}"><i class="bi bi-archive me-2"></i>${t.archived ? 'Unarchive' : 'Archive'}</a></li>
                <li><hr class="dropdown-divider"></li>
                <li><a class="dropdown-item text-danger btn-action-delete" href="#" data-id="${t.id}"><i class="bi bi-trash me-2"></i>Delete</a></li>
              </ul>
            </div>
          </div>
          <div class="q-thread-meta">${escapeHtml(tagsStr)}</div>
        </div>
      `;
    });
  });

  threadListEl.innerHTML = html;

  // Event Listeners for thread items
  threadListEl.querySelectorAll('.q-thread-item').forEach(item => {
    item.addEventListener('click', () => {
      const id = item.getAttribute('data-thread-id');
      const title = item.getAttribute('data-thread-title');
      if (id !== activeThreadId) {
        activeThreadId = id;
        activeThreadTitle = title;
        if (activeTitleEl) activeTitleEl.textContent = title;
        renderThreadsList();
        loadThreadMessages(id);
        if (chatSidebarEl && window.innerWidth <= 992) chatSidebarEl.classList.remove('open');
      }
    });
  });

  // Action listeners inside dropdowns
  threadListEl.querySelectorAll('.btn-action-rename').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const id = btn.getAttribute('data-id');
      const title = btn.getAttribute('data-title');
      promptRenameThread(id, title);
    });
  });

  threadListEl.querySelectorAll('.btn-action-archive').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = btn.getAttribute('data-id');
      const isArchived = btn.getAttribute('data-archived') === 'true';
      await toggleArchiveThread(id, !isArchived);
    });
  });

  threadListEl.querySelectorAll('.btn-action-delete').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = btn.getAttribute('data-id');
      await deleteThread(id);
    });
  });
}

async function handleCreateNewThread(parentId = null) {
  try {
    const title = parentId ? "Branch Discussion" : "New Conversation";
    const data = await fetchApi('/api/chat/threads', {
      method: 'POST',
      body: JSON.stringify({ title: title, parent_id: parentId })
    });
    activeThreadId = data.id;
    activeThreadTitle = data.title;
    if (activeTitleEl) activeTitleEl.textContent = activeThreadTitle;
    await loadThreads();
    renderWelcomeBanner();
    showToast(parentId ? 'Branched new conversation thread.' : 'Created new conversation.', 'info');
  } catch (err) {
    showToast('Could not create new thread: ' + err.message, 'danger');
  }
}

async function promptRenameThread(id, oldTitle) {
  const newTitle = prompt('Enter new conversation title:', oldTitle);
  if (newTitle && newTitle.trim() && newTitle.trim() !== oldTitle) {
    try {
      await fetchApi(`/api/chat/threads/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: newTitle.trim() })
      });
      if (id === activeThreadId) {
        activeThreadTitle = newTitle.trim();
        if (activeTitleEl) activeTitleEl.textContent = activeThreadTitle;
      }
      await loadThreads();
      showToast('Conversation renamed.', 'success');
    } catch (err) {
      showToast('Rename failed: ' + err.message, 'danger');
    }
  }
}

async function handleRenameActiveThread() {
  if (activeThreadId) {
    await promptRenameThread(activeThreadId, activeThreadTitle);
  }
}

async function toggleArchiveThread(id, archiveBool) {
  try {
    await fetchApi(`/api/chat/threads/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ archived: archiveBool })
    });
    await loadThreads();
    showToast(archiveBool ? 'Conversation archived.' : 'Conversation unarchived.', 'info');
  } catch (err) {
    showToast('Failed to update thread: ' + err.message, 'danger');
  }
}

async function deleteThread(id) {
  if (!confirm('Are you sure you want to delete this conversation?')) return;
  try {
    await fetchApi(`/api/chat/threads/${id}`, { method: 'DELETE' });
    if (id === activeThreadId) {
      activeThreadId = null;
      activeThreadTitle = 'Digital Twin Intelligence';
    }
    await loadThreads();
    showToast('Conversation deleted.', 'info');
  } catch (err) {
    showToast('Delete failed: ' + err.message, 'danger');
  }
}

// ── Messages Feed & Loading ──────────────────────────────────────────────────
async function loadThreadMessages(threadId) {
  const container = getTargetContainer();
  if (!container) return;

  container.innerHTML = `<div class="m-auto text-center text-muted py-5"><div class="spinner-border text-primary spinner-border-sm me-2"></div>Syncing conversation messages...</div>`;

  try {
    const history = await fetchApi(`/api/chat/history?thread_id=${threadId}`);
    container.innerHTML = '';

    if (!history || history.length === 0) {
      renderWelcomeBanner();
      return;
    }

    history.forEach(msg => {
      appendMessage(msg.role, msg.content, msg.tool_calls || [], msg.widgets || []);
    });
    scrollToBottom();
  } catch (err) {
    container.innerHTML = `<div class="m-auto text-center text-danger py-4"><i class="bi bi-exclamation-triangle-fill me-2"></i>Failed to load messages. <button class="btn btn-link text-primary btn-sm" id="btn-retry-load">Retry</button></div>`;
    const retryBtn = document.getElementById('btn-retry-load');
    if (retryBtn) retryBtn.addEventListener('click', () => loadThreadMessages(threadId));
  }
}

function renderWelcomeBanner() {
  const container = getTargetContainer();
  if (!container) return;

  container.innerHTML = `
    <div class="q-welcome-banner text-center py-5">
      <div class="q-welcome-icon mb-3" style="font-size:2.5rem; color:#3b82f6;">
        <i class="bi bi-stars"></i>
      </div>
      <h2 class="q-welcome-title fw-bold text-light mb-2">How can I assist your Digital Twin today?</h2>
      <p class="q-welcome-sub text-muted mb-4" style="max-width:560px; margin:0 auto;">I am connected to your live financial records, study sessions, habit risk predictions, and Monte Carlo simulation lab.</p>

      <div class="row g-3 justify-content-center" style="max-width:800px; margin:0 auto;">
        <div class="col-md-6">
          <div class="p-3 rounded-3 bg-dark border border-secondary text-start q-suggest-chip cursor-pointer" data-prompt="Analyze my 30-day spending breakdown and net savings rate.">
            <strong class="text-primary d-block mb-1">📊 Financial Overview</strong>
            <div class="text-muted small">Check income, expenses &amp; savings rate</div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="p-3 rounded-3 bg-dark border border-secondary text-start q-suggest-chip cursor-pointer" data-prompt="What is my 7-day study prediction based on my historical momentum?">
            <strong class="text-info d-block mb-1">📚 Study Forecast</strong>
            <div class="text-muted small">Analyze focus hours &amp; cognitive output</div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="p-3 rounded-3 bg-dark border border-secondary text-start q-suggest-chip cursor-pointer" data-prompt="Which of my active habits are at high risk of churn?">
            <strong class="text-warning d-block mb-1">✅ Habit Churn Risk</strong>
            <div class="text-muted small">Identify at-risk streaks &amp; streak shield</div>
          </div>
        </div>
        <div class="col-md-6">
          <div class="p-3 rounded-3 bg-dark border border-secondary text-start q-suggest-chip cursor-pointer" data-prompt="Simulate saving 15% more income over the next 6 months.">
            <strong class="text-success d-block mb-1">🔮 Scenario Simulation</strong>
            <div class="text-muted small">Run financial &amp; productivity simulations</div>
          </div>
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll('[data-prompt]').forEach(btn => {
    btn.addEventListener('click', () => {
      const prompt = btn.getAttribute('data-prompt');
      if (prompt && inputEl) {
        inputEl.value = prompt;
        handleSendMessage();
      }
    });
  });
}

// ── Sending & Handling Messages ──────────────────────────────────────────────
async function handleSendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  if (!activeThreadId) {
    await handleCreateNewThread();
  }

  const container = getTargetContainer();
  const banner = container.querySelector('.q-welcome-banner');
  if (banner) banner.remove();

  inputEl.value = '';
  inputEl.style.height = 'auto';
  setLoading(true);

  appendMessage('user', text);
  const typingIndicator = appendTypingIndicator();

  const routingMode = routingModeSelect?.value || 'auto';

  try {
    const res = await fetchApi('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: text,
        thread_id: activeThreadId,
        routing_mode: routingMode
      })
    });

    removeTypingIndicator();
    appendMessage('assistant', res.reply, res.tool_calls || [], res.widgets || []);
    
    // Refresh threads list & right panel summary
    loadThreads();
    loadContextSummary();

  } catch (err) {
    removeTypingIndicator();
    appendMessage('assistant', `⚠️ **Service Notice**: ${err.message || 'I encountered an issue connecting to the AI model. Please try again.'}`);
  } finally {
    setLoading(false);
    if (inputEl) inputEl.focus();
  }
}

function setLoading(isLoading) {
  if (sendBtn) {
    sendBtn.disabled = isLoading;
    sendBtn.innerHTML = isLoading
      ? `<span class="spinner-border spinner-border-sm" role="status"></span>`
      : `<i class="bi bi-send-fill"></i>`;
  }
  if (inputEl) inputEl.disabled = isLoading;
}

// ── Markdown & Rich Cards Renderer ───────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '';

  let html = escapeHtml(text)
    // Fenced code blocks
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="bg-dark p-2 rounded border border-secondary text-light"><code>$1</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-dark text-info px-1 rounded">$1</code>')
    // Headers
    .replace(/^### (.*$)/gim, '<h6 class="fw-bold mt-2 mb-1 text-light">$1</h6>')
    .replace(/^## (.*$)/gim, '<h5 class="fw-bold mt-2 mb-1 text-light">$1</h5>')
    // Bold & Italic
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Bullet lists
    .replace(/^[-•]\s(.+)$/gm, '<li class="mb-1">$1</li>')
    .replace(/(<li class="mb-1">[\s\S]*?<\/li>)+/g, '<ul class="ps-3 mb-2">$&</ul>')
    // Line breaks
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');

  // Detect and inject smart navigation links
  html = injectSmartActionLinks(html);

  return `<p>${html}</p>`;
}

function injectSmartActionLinks(html) {
  if (html.includes('/expenses') || html.includes('expenses') || html.includes('spending')) {
    if (!html.includes('href="/expenses"')) {
      html += `<div class="mt-2"><a href="/expenses" class="btn btn-sm btn-outline-primary rounded-pill text-decoration-none" style="font-size:0.75rem;"><i class="bi bi-credit-card-fill me-1"></i> Open Finance Analytics</a></div>`;
    }
  }
  if (html.includes('/study') || html.includes('study') || html.includes('cognitive')) {
    if (!html.includes('href="/study"')) {
      html += `<div class="mt-2"><a href="/study" class="btn btn-sm btn-outline-info rounded-pill text-decoration-none" style="font-size:0.75rem;"><i class="bi bi-book-fill me-1"></i> Open Study Analytics</a></div>`;
    }
  }
  if (html.includes('/habits') || html.includes('habit')) {
    if (!html.includes('href="/habits"')) {
      html += `<div class="mt-2"><a href="/habits" class="btn btn-sm btn-outline-warning rounded-pill text-decoration-none" style="font-size:0.75rem;"><i class="bi bi-check2-circle me-1"></i> Open Habit Tracker</a></div>`;
    }
  }
  if (html.includes('/simulation') || html.includes('simulate') || html.includes('scenario')) {
    if (!html.includes('href="/simulation"')) {
      html += `<div class="mt-2"><a href="/simulation" class="btn btn-sm btn-outline-success rounded-pill text-decoration-none" style="font-size:0.75rem;"><i class="bi bi-diagram-3-fill me-1"></i> Open Simulation Lab</a></div>`;
    }
  }
  return html;
}

function appendMessage(role, content, toolCalls = [], widgets = []) {
  const container = getTargetContainer();
  if (!container) return;
  const isUser = role === 'user';

  const row = document.createElement('div');
  row.className = `q-msg-row ${isUser ? 'user' : 'assistant'}`;

  const avatar = document.createElement('div');
  avatar.className = `q-avatar ${isUser ? 'user' : 'assistant'}`;
  avatar.innerHTML = isUser ? `<i class="bi bi-person-fill"></i>` : `<i class="bi bi-stars"></i>`;

  const contentWrap = document.createElement('div');
  contentWrap.className = 'q-msg-content';

  const bubble = document.createElement('div');
  bubble.className = `q-bubble ${isUser ? 'user' : 'assistant'}`;

  if (isUser) {
    bubble.textContent = content;
    contentWrap.appendChild(bubble);
  } else {
    bubble.innerHTML = renderMarkdown(content);
    contentWrap.appendChild(bubble);

    // Render Generative UI Widgets inline inside assistant content block
    if (widgets && widgets.length > 0) {
      widgets.forEach(w => {
        const widgetNode = buildGenerativeWidget(w);
        if (widgetNode) contentWrap.appendChild(widgetNode);
      });
    }

    // Tool call execution badge
    if (toolCalls && toolCalls.length > 0) {
      const badge = buildToolBadge(toolCalls);
      contentWrap.appendChild(badge);
    }
  }

  // Assistant response action bar
  if (!isUser) {
    const actionBar = document.createElement('div');
    actionBar.className = 'q-msg-action-bar d-flex gap-2 mt-2';
    actionBar.innerHTML = `
      <button class="btn btn-sm btn-outline-secondary py-0 px-2 btn-save-insight" style="font-size:0.72rem;" title="Save to Right Panel">
        <i class="bi bi-bookmark-plus me-1"></i> Save Insight
      </button>
      <button class="btn btn-sm btn-outline-secondary py-0 px-2 btn-copy-msg" style="font-size:0.72rem;" title="Copy Text">
        <i class="bi bi-clipboard me-1"></i> Copy
      </button>
    `;

    actionBar.querySelector('.btn-save-insight').addEventListener('click', () => {
      saveInsightFromMessage(content);
    });
    actionBar.querySelector('.btn-copy-msg').addEventListener('click', () => {
      navigator.clipboard.writeText(content);
      showToast('Copied to clipboard!', 'success');
    });

    contentWrap.appendChild(actionBar);
  }

  row.appendChild(avatar);
  row.appendChild(contentWrap);

  container.appendChild(row);
  scrollToBottom();
}

function buildGenerativeWidget(widget) {
  if (!widget || !widget.payload) return null;
  const p = widget.payload;
  const wrapper = document.createElement('div');

  // 1. Line Chart Widget (History + Forecast)
  if (widget.type === 'line_chart') {
    wrapper.className = 'q-widget-chart-card mt-2';
    const chartId = 'chat-chart-' + Math.random().toString(36).substr(2, 9);
    
    wrapper.innerHTML = `
      <div class="q-widget-header">
        <div class="q-widget-title">
          <i class="bi bi-graph-up text-primary"></i> ${escapeHtml(p.title || 'Forecast Trajectory')}
        </div>
        <div class="d-flex align-items-center gap-2">
          <span class="q-widget-badge"><i class="bi bi-cpu me-1"></i> ML Forecast</span>
          ${p.view_url ? `<a href="${p.view_url}" class="text-primary text-decoration-none small">View ↗</a>` : ''}
        </div>
      </div>
      <div style="position:relative; height:190px; width:100%;">
        <canvas id="${chartId}"></canvas>
      </div>
      ${p.insight ? `<div class="mt-2 text-muted small"><i class="bi bi-lightbulb text-warning me-1"></i> ${escapeHtml(p.insight)}</div>` : ''}
    `;

    setTimeout(() => {
      const canvas = document.getElementById(chartId);
      if (!canvas || !window.Chart) return;
      
      const isLight = document.body.classList.contains('light-theme');
      const textColor = isLight ? '#475569' : '#94a3b8';
      const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.06)';
      const primaryColor = isLight ? '#0d9488' : '#7c3aed';
      const forecastColor = isLight ? '#0284c7' : '#38bdf8';
      
      const history = p.history || [];
      const forecast = p.forecast || [];
      
      const labels = [];
      const histData = [];
      const foreData = [];
      
      history.forEach(h => {
        labels.push(h.date ? h.date.slice(5) : '');
        histData.push(h.amount !== undefined ? h.amount : h.value);
        foreData.push(null);
      });
      
      if (history.length > 0 && forecast.length > 0) {
        foreData[foreData.length - 1] = histData[histData.length - 1];
      }
      
      forecast.forEach(f => {
        labels.push(f.date ? f.date.slice(5) : '');
        foreData.push(f.amount !== undefined ? f.amount : f.value);
      });
      
      new window.Chart(canvas, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Historical',
              data: histData,
              borderColor: primaryColor,
              backgroundColor: isLight ? 'rgba(13,148,136,0.1)' : 'rgba(124,58,237,0.15)',
              borderWidth: 2,
              tension: 0.3,
              fill: false,
              pointRadius: labels.length > 20 ? 0 : 3
            },
            {
              label: 'Forecast',
              data: foreData,
              borderColor: forecastColor,
              borderDash: [5, 5],
              borderWidth: 2,
              tension: 0.3,
              fill: false,
              pointRadius: labels.length > 20 ? 0 : 3
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              display: true,
              labels: { color: textColor, boxWidth: 10, font: { size: 11 } }
            },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  if (ctx.parsed.y === null) return '';
                  const val = ctx.parsed.y;
                  if (p.kind === 'currency') return ` ₹${Number(val).toLocaleString()}`;
                  if (p.kind === 'minutes') return ` ${val} mins`;
                  if (p.kind === 'hours') return ` ${Number(val).toFixed(1)} hrs`;
                  return ` ${val}`;
                }
              }
            }
          },
          scales: {
            x: { grid: { color: gridColor }, ticks: { color: textColor, maxTicksLimit: 7, font: { size: 10 } } },
            y: {
              grid: { color: gridColor },
              ticks: {
                color: textColor,
                font: { size: 10 },
                callback: (val) => p.kind === 'currency' ? `₹${val}` : val
              }
            }
          }
        }
      });
    }, 60);

    return wrapper;
  }

  // 2. Bar Chart Widget (Category Breakdown / Daily Productivity)
  if (widget.type === 'bar_chart') {
    wrapper.className = 'q-widget-chart-card mt-2';
    const chartId = 'chat-chart-' + Math.random().toString(36).substr(2, 9);
    
    wrapper.innerHTML = `
      <div class="q-widget-header">
        <div class="q-widget-title">
          <i class="bi bi-bar-chart-fill text-primary"></i> ${escapeHtml(p.title || 'Breakdown')}
        </div>
        ${p.view_url ? `<a href="${p.view_url}" class="text-primary text-decoration-none small">View ↗</a>` : ''}
      </div>
      <div style="position:relative; height:180px; width:100%;">
        <canvas id="${chartId}"></canvas>
      </div>
    `;

    setTimeout(() => {
      const canvas = document.getElementById(chartId);
      if (!canvas || !window.Chart) return;
      
      const isLight = document.body.classList.contains('light-theme');
      const textColor = isLight ? '#475569' : '#94a3b8';
      const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.06)';
      const barColor = isLight ? '#0d9488' : '#7c3aed';
      
      new window.Chart(canvas, {
        type: 'bar',
        data: {
          labels: p.labels || [],
          datasets: [{
            data: p.values || [],
            backgroundColor: barColor,
            borderRadius: 6
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const val = ctx.parsed.x;
                  if (p.kind === 'currency') return ` ₹${Number(val).toLocaleString()}`;
                  if (p.kind === 'minutes') return ` ${val} mins`;
                  return ` ${val}`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { color: gridColor },
              ticks: {
                color: textColor,
                font: { size: 10 },
                callback: (val) => p.kind === 'currency' ? `₹${val}` : val
              }
            },
            y: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } }
          }
        }
      });
    }, 60);

    return wrapper;
  }

  // 3. Habit Risk Widget
  if (widget.type === 'habit_risk') {
    wrapper.className = 'q-widget-chart-card mt-2';
    const habits = p.habits || [];
    
    wrapper.innerHTML = `
      <div class="q-widget-header">
        <div class="q-widget-title">
          <i class="bi bi-shield-exclamation text-warning"></i> ${escapeHtml(p.title || 'Habit Churn Risk')}
        </div>
        ${p.view_url ? `<a href="${p.view_url}" class="text-primary text-decoration-none small">Tracker ↗</a>` : ''}
      </div>
      <div class="d-flex flex-column gap-2 mt-2">
        ${habits.length === 0 ? '<div class="text-muted small">No active habits recorded.</div>' : habits.map(h => {
          const prob = h.churn_probability || 0;
          const color = prob >= 60 ? '#ef4444' : prob >= 35 ? '#f59e0b' : '#10b981';
          const badgeClass = prob >= 60 ? 'bg-danger' : prob >= 35 ? 'bg-warning text-dark' : 'bg-success';
          return `
            <div class="p-2 rounded" style="background:var(--q-bg-elevated); border:1px solid var(--q-border);">
              <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="fw-bold" style="font-size:0.84rem;">${escapeHtml(h.name)}</span>
                <div class="d-flex align-items-center gap-2">
                  <span class="badge bg-secondary" style="font-size:0.7rem;">🔥 ${h.current_streak || 0}d streak</span>
                  <span class="badge ${badgeClass}" style="font-size:0.7rem;">${escapeHtml(h.risk_level || 'Risk')} (${prob}%)</span>
                </div>
              </div>
              <div class="progress" style="height:5px; background:var(--q-border);">
                <div class="progress-bar" style="width:${prob}%; background-color:${color};"></div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
    return wrapper;
  }

  // Habit Check-in Card Widget
  if (widget.type === 'habit_checkin_card') {
    wrapper.className = 'q-widget-chart-card mt-2 p-3';
    wrapper.style.border = '1px solid rgba(16, 185, 129, 0.4)';
    wrapper.style.background = 'linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(13, 14, 26, 0.95) 100%)';
    wrapper.style.borderRadius = '16px';
    
    const hName = escapeHtml(p.habit_name || 'Habit');
    const hStreak = p.habit_streak || 1;
    const dStreak = p.daily_streak || 1;
    const xpGained = p.xp_gained || 10;
    const totalXp = p.total_xp || 0;
    const level = escapeHtml(p.level || 'Rookie');
    const milestone = p.milestone ? escapeHtml(p.milestone) : null;
    const isAlready = !!p.already_completed;

    wrapper.innerHTML = `
      <div class="d-flex align-items-center justify-content-between mb-3 pb-2 border-bottom border-secondary border-opacity-25">
        <div class="d-flex align-items-center gap-2">
          <div class="rounded-circle d-flex align-items-center justify-content-center" style="width:34px;height:34px;background:rgba(16,185,129,0.2);color:#10b981;">
            <i class="bi bi-check2-circle fs-5"></i>
          </div>
          <div>
            <div class="fw-bold text-light" style="font-size:0.95rem;">${isAlready ? 'Habit Already Completed' : 'Habit Marked Complete!'}</div>
            <div class="text-muted small">${escapeHtml(p.completed_date || 'Today')}</div>
          </div>
        </div>
        <span class="badge ${isAlready ? 'bg-secondary' : 'bg-success'} text-white px-2 py-1" style="font-size:0.75rem;">
          <i class="bi bi-check-lg me-1"></i>${isAlready ? 'Checked' : 'Checked In'}
        </span>
      </div>

      <div class="mb-3">
        <div class="d-flex align-items-baseline gap-2">
          <span style="font-size:1.15rem; font-weight:700; color:var(--q-text);">${hName}</span>
          <span class="badge" style="background:var(--q-accent-dim);color:var(--q-accent-light);font-size:0.7rem;">${escapeHtml(p.category || 'habit')}</span>
        </div>
      </div>

      <div class="row g-2 mb-3">
        <div class="col-6">
          <div class="p-2 rounded" style="background:var(--q-bg-elevated); border:1px solid var(--q-border);">
            <div class="text-muted small text-uppercase" style="font-size:0.68rem; letter-spacing:0.05em;">Habit Streak</div>
            <div class="d-flex align-items-center gap-1 mt-1">
              <span style="font-size:1.25rem; font-weight:800; color:#f59e0b;">🔥 ${hStreak}</span>
              <span class="small text-muted">days</span>
            </div>
          </div>
        </div>
        <div class="col-6">
          <div class="p-2 rounded" style="background:var(--q-bg-elevated); border:1px solid var(--q-border);">
            <div class="text-muted small text-uppercase" style="font-size:0.68rem; letter-spacing:0.05em;">Daily Platform Streak</div>
            <div class="d-flex align-items-center gap-1 mt-1">
              <span style="font-size:1.25rem; font-weight:800; color:#3b82f6;">⚡ ${dStreak}</span>
              <span class="small text-muted">days</span>
            </div>
          </div>
        </div>
      </div>

      <div class="p-2 rounded d-flex align-items-center justify-content-between mb-2" style="background:rgba(124,58,237,0.12); border:1px solid rgba(124,58,237,0.3);">
        <div class="d-flex align-items-center gap-2">
          <span class="badge" style="background:#7c3aed;color:#fff;">+${xpGained} XP</span>
          <span class="small" style="color:var(--q-text);">Level: <strong>${level}</strong> (${totalXp} XP)</span>
        </div>
        ${milestone ? `<span class="badge bg-warning text-dark"><i class="bi bi-trophy-fill me-1"></i>${milestone}</span>` : ''}
      </div>

      <div class="text-end pt-1">
        <a href="${p.view_url || '/habits'}" class="btn btn-sm btn-outline-success rounded-pill px-3 py-1" style="font-size:0.75rem;">
          View Habits Tracker ↗
        </a>
      </div>
    `;
    return wrapper;
  }

  // 4. Goal Progress Widget
  if (widget.type === 'goal_progress') {
    wrapper.className = 'q-widget-chart-card mt-2';
    const goals = p.goals || [];
    
    wrapper.innerHTML = `
      <div class="q-widget-header">
        <div class="q-widget-title">
          <i class="bi bi-flag-fill text-primary"></i> ${escapeHtml(p.title || 'Goal Progress')}
        </div>
        ${p.view_url ? `<a href="${p.view_url}" class="text-primary text-decoration-none small">Goals ↗</a>` : ''}
      </div>
      <div class="d-flex flex-column gap-2 mt-2">
        ${goals.length === 0 ? '<div class="text-muted small">No goals recorded yet.</div>' : goals.map(g => {
          const pct = Math.min(100, Math.max(0, g.progress_percentage || 0));
          return `
            <div class="p-2 rounded" style="background:var(--q-bg-elevated); border:1px solid var(--q-border);">
              <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="fw-bold" style="font-size:0.84rem;">${escapeHtml(g.title)}</span>
                <span class="badge bg-primary" style="font-size:0.7rem;">${pct}%</span>
              </div>
              <div class="progress" style="height:6px; background:var(--q-border);">
                <div class="progress-bar bg-primary" style="width:${pct}%;"></div>
              </div>
              ${g.target_date ? `<div class="text-muted mt-1" style="font-size:0.7rem;">Target: ${escapeHtml(g.target_date)}</div>` : ''}
            </div>
          `;
        }).join('')}
      </div>
    `;
    return wrapper;
  }

  // 5. Monte Carlo Fan Chart Widget
  if (widget.type === 'fan_chart') {
    wrapper.className = 'q-widget-chart-card mt-2';
    const chartId = 'chat-chart-' + Math.random().toString(36).substr(2, 9);
    
    wrapper.innerHTML = `
      <div class="q-widget-header">
        <div class="q-widget-title">
          <i class="bi bi-diagram-3-fill text-info"></i> ${escapeHtml(p.title || 'Monte Carlo Fan')}
        </div>
        <div class="d-flex align-items-center gap-2">
          <span class="badge ${p.prob_shortfall > 25 ? 'bg-danger' : 'bg-success'}" style="font-size:0.72rem;">
            Shortfall Risk: ${p.prob_shortfall || 0}%
          </span>
          ${p.view_url ? `<a href="${p.view_url}" class="text-primary text-decoration-none small">Sim Lab ↗</a>` : ''}
        </div>
      </div>
      <div style="position:relative; height:190px; width:100%;">
        <canvas id="${chartId}"></canvas>
      </div>
    `;

    setTimeout(() => {
      const canvas = document.getElementById(chartId);
      if (!canvas || !window.Chart) return;
      
      const isLight = document.body.classList.contains('light-theme');
      const textColor = isLight ? '#475569' : '#94a3b8';
      const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.06)';
      const labels = (p.dates || []).map(d => typeof d === 'string' ? d.slice(5) : d);
      
      new window.Chart(canvas, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Median (P50)',
              data: p.p50 || [],
              borderColor: isLight ? '#0d9488' : '#38bdf8',
              borderWidth: 2,
              fill: false,
              pointRadius: 0
            },
            {
              label: 'Optimistic (P95)',
              data: p.p95 || [],
              borderColor: 'rgba(16, 185, 129, 0.4)',
              borderDash: [3, 3],
              borderWidth: 1.5,
              fill: false,
              pointRadius: 0
            },
            {
              label: 'Downside (P5)',
              data: p.p5 || [],
              borderColor: 'rgba(239, 68, 68, 0.4)',
              borderDash: [3, 3],
              borderWidth: 1.5,
              fill: false,
              pointRadius: 0
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              labels: { color: textColor, boxWidth: 10, font: { size: 10 } }
            }
          },
          scales: {
            x: { grid: { color: gridColor }, ticks: { color: textColor, maxTicksLimit: 6, font: { size: 10 } } },
            y: {
              grid: { color: gridColor },
              ticks: {
                color: textColor,
                font: { size: 10 },
                callback: (v) => `₹${Number(v).toLocaleString()}`
              }
            }
          }
        }
      });
    }, 60);

    return wrapper;
  }

  // 6. Clarification Chips Widget (Interactive Disambiguation)
  if (widget.type === 'clarification_chips') {
    wrapper.className = 'q-widget-clarification mt-2';
    const options = p.options || [];
    
    wrapper.innerHTML = `
      <div class="small fw-bold text-muted mb-2"><i class="bi bi-compass me-1"></i> ${escapeHtml(p.title || 'Choose a focus area to inspect:')}</div>
      <div class="d-flex flex-wrap gap-2">
        ${options.map(opt => `
          <button class="btn btn-sm btn-outline-primary rounded-pill py-1 px-3 d-flex align-items-center gap-1 q-clarify-chip"
                  data-prompt="${escapeHtml(opt.prompt)}">
            ${opt.icon ? `<i class="bi ${escapeHtml(opt.icon)}"></i>` : ''}
            <span>${escapeHtml(opt.label)}</span>
          </button>
        `).join('')}
      </div>
    `;

    wrapper.querySelectorAll('.q-clarify-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const promptText = btn.getAttribute('data-prompt');
        if (promptText && inputEl) {
          inputEl.value = promptText;
          handleSendMessage();
        }
      });
    });

    return wrapper;
  }

  // 7. Productivity Snapshot Widget
  if (widget.type === 'productivity_snapshot') {
    wrapper.className = 'q-widget-snapshot mt-2';
    wrapper.innerHTML = `
      <div class="q-widget-header">
        <div class="q-widget-title">
          <i class="bi bi-speedometer2 text-primary"></i> ${escapeHtml(p.title || 'Productivity Snapshot')}
        </div>
        <div class="q-widget-badge">
          <i class="bi bi-arrow-up-short"></i> ${escapeHtml(p.trend_text || 'Active')}
        </div>
      </div>
      <div class="q-widget-grid">
        <div>
          <div class="q-widget-stat-val text-primary">${p.score || 0}/100</div>
          <div class="q-widget-stat-lbl">Productivity Score</div>
        </div>
        <div>
          <div class="q-widget-stat-val">${p.focus_time_hrs || 0}h</div>
          <div class="q-widget-stat-lbl">${escapeHtml(p.focus_label || 'Focus Time')}</div>
        </div>
        <div>
          <div class="q-widget-stat-val">${p.consistency_pct || 0}%</div>
          <div class="q-widget-stat-lbl">${escapeHtml(p.consistency_label || 'Consistency')}</div>
        </div>
      </div>
      <div class="q-widget-footer">
        <span>Peak Window: <strong>${escapeHtml(p.peak_window || 'N/A')}</strong></span>
        <a href="${p.view_url || '/productivity'}" class="btn btn-sm btn-outline-primary rounded-pill px-3" style="font-size:0.75rem;">View Analytics ↗</a>
      </div>
    `;
    return wrapper;
  }

  // 8. Insight Card Widget
  if (widget.type === 'insight_card') {
    wrapper.className = 'q-widget-insight mt-2';
    wrapper.innerHTML = `
      <div class="d-flex align-items-center gap-2 text-warning fw-bold mb-2" style="font-size:0.85rem;">
        <i class="bi bi-lightbulb-fill"></i> Productivity Insight Card
      </div>
      <div class="q-widget-insight-heading fw-bold text-light">${escapeHtml(p.heading || '')}</div>
      <div class="q-widget-insight-why mt-1 text-muted small">${escapeHtml(p.why_it_matters || '')}</div>
      ${p.focus_window ? `<div class="mt-2 text-muted small"><i class="bi bi-clock me-1 text-primary"></i>Peak Window: <strong>${escapeHtml(p.focus_window)}</strong></div>` : ''}
      <div class="mt-3 text-end">
        <a href="${p.view_url || '/study'}" class="btn btn-sm btn-warning rounded-pill px-3 text-dark font-weight-bold" style="font-size:0.75rem;">Explore Insight Details ↗</a>
      </div>
    `;
    return wrapper;
  }

  return null;
}

function buildToolBadge(toolCalls) {
  const container = document.createElement('div');
  container.className = 'mt-1 mb-1';
  container.style.fontSize = '0.75rem';

  const toggle = document.createElement('button');
  toggle.className = 'btn btn-sm btn-outline-secondary py-0 px-2 rounded-pill';
  toggle.style.fontSize = '0.72rem';
  toggle.innerHTML = `<i class="bi bi-cpu me-1 text-primary"></i> Quanta executed ${toolCalls.length} data tool${toolCalls.length > 1 ? 's' : ''}`;

  const details = document.createElement('div');
  details.className = 'd-none mt-1 p-2 rounded bg-dark text-light border border-secondary';
  details.innerHTML = toolCalls.map(tc => `
    <div class="d-flex justify-content-between gap-2 py-1 border-bottom border-secondary">
      <span class="fw-bold text-primary">${escapeHtml(tc.tool)}</span>
      <span class="text-muted small">${escapeHtml(tc.result_summary)}</span>
    </div>
  `).join('');

  toggle.addEventListener('click', () => {
    details.classList.toggle('d-none');
  });

  container.appendChild(toggle);
  container.appendChild(details);
  return container;
}

function appendTypingIndicator() {
  const container = getTargetContainer();
  const row = document.createElement('div');
  row.className = 'q-msg-row assistant';
  row.id = 'q-typing-row';

  row.innerHTML = `
    <div class="q-avatar assistant"><i class="bi bi-stars"></i></div>
    <div class="q-bubble assistant d-flex align-items-center gap-2">
      <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
      <span style="font-size:0.88rem; color:var(--q-muted);">Quanta Assistant is retrieving live data &amp; formulating response...</span>
    </div>
  `;

  container.appendChild(row);
  scrollToBottom();
  return row;
}

function removeTypingIndicator() {
  const el = document.getElementById('q-typing-row');
  if (el) el.remove();
}

function scrollToBottom() {
  if (messagesFeedEl) {
    messagesFeedEl.scrollTop = messagesFeedEl.scrollHeight;
  }
}

// ── Saved Insights Logic ─────────────────────────────────────────────────────
async function saveInsightFromMessage(text) {
  const title = prompt('Insight Title:', text.slice(0, 30) + '...');
  if (!title) return;

  try {
    await fetchApi('/api/chat/insights', {
      method: 'POST',
      body: JSON.stringify({
        title: title.trim(),
        content: text.slice(0, 300),
        domain: 'AI Twin'
      })
    });
    showToast('Insight saved to Right Context Panel!', 'success');
    loadContextSummary();
  } catch (err) {
    showToast('Failed to save insight: ' + err.message, 'danger');
  }
}

// ── Right Context Panel Dynamic Sync ────────────────────────────────────────
async function loadContextSummary() {
  try {
    const data = await fetchApi('/api/chat/context-summary');
    if (!data) return;

    // Populate Domain Summaries
    if (data.domain_summaries) {
      const dom = data.domain_summaries;
      if (ctxProdScoreEl && dom.productivity) ctxProdScoreEl.textContent = dom.productivity.score || '84/100';
      if (ctxProdConsistencyEl && dom.productivity) ctxProdConsistencyEl.textContent = dom.productivity.consistency || '64.3%';
      if (ctxHabitsValEl && dom.habits) ctxHabitsValEl.textContent = `${dom.habits.active_count || 0} active`;
      if (ctxStudyValEl && dom.study) ctxStudyValEl.textContent = dom.study.recent_hours || '0.0 hrs';
    }

    // Populate Sources Used
    if (data.data_sources && qContextSourcesEl) {
      if (ctxSourcesCountEl) ctxSourcesCountEl.textContent = `${data.data_sources.length} sources active`;
      qContextSourcesEl.innerHTML = data.data_sources.map(src => `
        <div class="q-metric-pill">
          <span><i class="bi bi-check-circle-fill text-success me-2"></i>${escapeHtml(src.name)}</span>
        </div>
      `).join('');
    }

    // Populate Saved Insights
    const insights = data.saved_insights || [];
    if (ctxInsightsCountEl) ctxInsightsCountEl.textContent = insights.length;
    renderSavedInsights(insights);
  } catch (err) {
    console.warn('Could not load right context summary:', err);
  }
}

function renderSavedInsights(insights) {
  if (!savedInsightsContainer) return;

  if (insights.length === 0) {
    savedInsightsContainer.innerHTML = `<div class="text-muted small text-center py-3">No saved insights yet. Click "Save Insight" on any AI response to pin it here.</div>`;
    return;
  }

  savedInsightsContainer.innerHTML = insights.map(item => `
    <div class="q-saved-insight-item border-bottom border-secondary py-2">
      <div class="d-flex justify-content-between align-items-start mb-1">
        <strong class="text-primary small">${escapeHtml(item.title)}</strong>
        <button class="btn btn-link btn-sm text-danger p-0 ms-2 btn-delete-insight" data-id="${item.id}">
          <i class="bi bi-x-circle"></i>
        </button>
      </div>
      <div class="text-muted small" style="font-size:0.74rem; line-height:1.4;">${escapeHtml(item.content)}</div>
    </div>
  `).join('');

  savedInsightsContainer.querySelectorAll('.btn-delete-insight').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      try {
        await fetchApi(`/api/chat/insights/${id}`, { method: 'DELETE' });
        showToast('Insight removed.', 'info');
        loadContextSummary();
      } catch (err) {
        showToast('Failed to delete insight: ' + err.message, 'danger');
      }
    });
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
