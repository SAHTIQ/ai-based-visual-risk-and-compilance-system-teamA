/**
 * QUANTA — Chat Frontend
 * Handles: sending messages, rendering responses, tool call badges,
 * conversation history loading, suggested prompts, and clear history.
 */

import { onAuthChange } from './auth.js';
import { getIdToken } from './auth.js';

// ── State ─────────────────────────────────────────────────────────────────────

let _idToken = null;

// ── Auth ─────────────────────────────────────────────────────────────────────

onAuthChange(user => {
    if (!user && window.location.pathname !== '/login') {
        window.location.href = '/login';
        return;
    }
    if (user) {
        user.getIdToken().then(t => {
            _idToken = t;
            loadHistory();
        });
    }
});

async function getToken() {
    if (_idToken) return _idToken;
    _idToken = await getIdToken();
    return _idToken;
}

// ── DOM refs ─────────────────────────────────────────────────────────────────

const messagesEl    = document.getElementById('q-chat-messages');
const inputEl       = document.getElementById('q-chat-input');
const sendBtn       = document.getElementById('q-chat-send');
const clearBtn      = document.getElementById('q-chat-clear');
const suggestArea   = document.getElementById('q-suggestions');

// ── API helpers ──────────────────────────────────────────────────────────────

async function apiChat(message) {
    const token = await getToken();
    const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Request failed');
    return data.data;
}

async function apiHistory() {
    const token = await getToken();
    const res = await fetch('/api/chat/history', {
        headers: { 'Authorization': `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Failed to load history');
    return data.data;
}

async function apiClearHistory() {
    const token = await getToken();
    const res = await fetch('/api/chat/history', {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
    });
    return res.json();
}

// ── Render ────────────────────────────────────────────────────────────────────

/**
 * Minimal safe markdown renderer: bold, italic, inline code,
 * code blocks, bullet lists, numbered lists, and line breaks.
 */
function renderMarkdown(text) {
    if (!text) return '';
    let html = text
        // Escape HTML first
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        // Fenced code blocks
        .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
        // Inline code
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Bold
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        // Numbered list
        .replace(/^\d+\.\s(.+)$/gm, '<li class="q-list-item-num">$1</li>')
        // Bullet list
        .replace(/^[-•]\s(.+)$/gm, '<li class="q-list-item">$1</li>')
        // Wrap consecutive <li> in <ul>/<ol>
        .replace(/(<li class="q-list-item">[\s\S]*?<\/li>(?:\s*<li class="q-list-item">[\s\S]*?<\/li>)*)/g, '<ul class="q-md-list">$1</ul>')
        .replace(/(<li class="q-list-item-num">[\s\S]*?<\/li>(?:\s*<li class="q-list-item-num">[\s\S]*?<\/li>)*)/g, '<ol class="q-md-list">$1</ol>')
        // Line breaks
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    return `<p>${html}</p>`;
}

function appendMessage(role, content, toolCalls = []) {
    const isUser = role === 'user';

    const wrapper = document.createElement('div');
    wrapper.className = `q-msg-wrapper ${isUser ? 'q-msg-user' : 'q-msg-model'}`;

    const bubble = document.createElement('div');
    bubble.className = `q-msg-bubble ${isUser ? 'q-msg-bubble-user' : 'q-msg-bubble-model'}`;

    if (isUser) {
        bubble.textContent = content;
    } else {
        // Render markdown for model responses
        bubble.innerHTML = renderMarkdown(content);

        // Tool call badges (collapsed by default)
        if (toolCalls && toolCalls.length > 0) {
            const badge = buildToolBadge(toolCalls);
            wrapper.appendChild(badge);
        }
    }

    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

function buildToolBadge(toolCalls) {
    const container = document.createElement('div');
    container.className = 'q-tool-badge-container';

    const toggle = document.createElement('button');
    toggle.className = 'q-tool-toggle';
    toggle.innerHTML = `<i class="bi bi-cpu"></i> Quanta fetched ${toolCalls.length} data source${toolCalls.length > 1 ? 's' : ''} <i class="bi bi-chevron-down" id="tc-chevron-${Date.now()}"></i>`;

    const details = document.createElement('div');
    details.className = 'q-tool-details d-none';

    toolCalls.forEach(tc => {
        const item = document.createElement('div');
        item.className = 'q-tool-item';
        item.innerHTML = `<span class="q-tool-name">${tc.tool}</span><span class="q-tool-result">${tc.result_summary}</span>`;
        details.appendChild(item);
    });

    toggle.addEventListener('click', () => {
        details.classList.toggle('d-none');
        const chevron = toggle.querySelector('[id^="tc-chevron"]');
        if (chevron) {
            chevron.className = details.classList.contains('d-none')
                ? 'bi bi-chevron-down'
                : 'bi bi-chevron-up';
        }
    });

    container.appendChild(toggle);
    container.appendChild(details);
    return container;
}

function appendTypingIndicator() {
    const wrapper = document.createElement('div');
    wrapper.className = 'q-msg-wrapper q-msg-model';
    wrapper.id = 'q-typing';

    const bubble = document.createElement('div');
    bubble.className = 'q-msg-bubble q-msg-bubble-model q-typing';
    bubble.innerHTML = '<span></span><span></span><span></span>';

    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

function removeTypingIndicator() {
    const el = document.getElementById('q-typing');
    if (el) el.remove();
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showWelcome() {
    if (messagesEl.children.length === 0) {
        const el = document.createElement('div');
        el.id = 'q-welcome';
        el.className = 'q-welcome';
        el.innerHTML = `
          <div class="q-welcome-logo"><i class="bi bi-stars"></i></div>
          <h2 class="q-welcome-title">How can I help you today?</h2>
          <p class="q-welcome-sub">I have access to your financial records, study sessions, habits, goals, and ML predictions.</p>
        `;
        messagesEl.appendChild(el);
    }
}

function removeWelcome() {
    const el = document.getElementById('q-welcome');
    if (el) el.remove();
}

// ── Send message ──────────────────────────────────────────────────────────────

async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;

    removeWelcome();
    if (suggestArea) suggestArea.classList.add('d-none');

    inputEl.value = '';
    inputEl.style.height = 'auto';
    setLoading(true);

    appendMessage('user', text);
    const typing = appendTypingIndicator();

    try {
        const result = await apiChat(text);
        removeTypingIndicator();
        appendMessage('model', result.reply, result.tool_calls);
    } catch (err) {
        removeTypingIndicator();
        appendMessage('model', `⚠️ ${err.message || 'Something went wrong. Please try again.'}`);
    } finally {
        setLoading(false);
        inputEl.focus();
    }
}

function setLoading(on) {
    sendBtn.disabled = on;
    inputEl.disabled = on;
    sendBtn.innerHTML = on
        ? '<span class="spinner-border spinner-border-sm" role="status"></span>'
        : '<i class="bi bi-send-fill"></i>';
}

// ── Load history ──────────────────────────────────────────────────────────────

async function loadHistory() {
    try {
        const history = await apiHistory();
        if (!history || history.length === 0) {
            showWelcome();
            return;
        }
        removeWelcome();
        if (suggestArea) suggestArea.classList.add('d-none');
        history.forEach(msg => {
            appendMessage(msg.role, msg.content, msg.tool_calls || []);
        });
    } catch (err) {
        console.warn('Could not load chat history:', err.message);
        showWelcome();
    }
}

// ── Clear history ─────────────────────────────────────────────────────────────

if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
        if (!confirm('Clear your entire conversation history? This cannot be undone.')) return;
        try {
            await apiClearHistory();
            messagesEl.innerHTML = '';
            if (suggestArea) suggestArea.classList.remove('d-none');
            showWelcome();
        } catch (err) {
            alert('Failed to clear history: ' + err.message);
        }
    });
}

// ── Input events ──────────────────────────────────────────────────────────────

if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
}

if (inputEl) {
    inputEl.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    inputEl.addEventListener('input', () => {
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
    });
}

// ── Suggested prompts ─────────────────────────────────────────────────────────

document.querySelectorAll('[data-prompt]').forEach(btn => {
    btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        if (prompt) {
            inputEl.value = prompt;
            sendMessage();
        }
    });
});
