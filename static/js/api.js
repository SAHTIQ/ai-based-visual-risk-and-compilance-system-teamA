import { getIdToken } from './auth.js';

const _pendingRequests = new Map();

export async function apiCall(url, method = 'GET', body = null) {
    const isGet = method.toUpperCase() === 'GET' && !body;
    if (isGet && _pendingRequests.has(url)) {
        return _pendingRequests.get(url);
    }

    const reqPromise = (async () => {
        const token = await getIdToken();
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const config = {
            method: method,
            headers: headers
        };

        if (body) {
            config.body = JSON.stringify(body);
        }

        let response = await fetch(url, config);
        
        // Auto-refresh token and retry on 401
        if (response.status === 401) {
            console.warn(`[apiCall] 401 received for ${url}. Attempting silent token refresh...`);
            try {
                const refreshedToken = await getIdToken(true);
                if (refreshedToken) {
                    headers['Authorization'] = `Bearer ${refreshedToken}`;
                    response = await fetch(url, config);
                }
            } catch (refreshErr) {
                console.error("[apiCall] Token refresh failed:", refreshErr);
            }
        }

        if (response.status === 401) {
            console.warn("Unauthorized API call after refresh attempt. Redirecting to login.");
            import('./auth.js').then(module => {
                module.logoutUser();
            });
            throw new Error('Session expired or invalid. Please sign in again.');
        }

        const data = await response.json();
        
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'API request failed');
        }
        
        return data;
    })();

    if (isGet) {
        _pendingRequests.set(url, reqPromise);
        reqPromise.finally(() => _pendingRequests.delete(url));
    }

    return reqPromise;
}

export function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-bg-${type} border-0 mb-2`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');

    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    toastContainer.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();

    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
}

export function formatDate(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleDateString();
}

export function formatCurrency(amount, currency = 'INR') {
    let formatted = new Intl.NumberFormat('en-IN', { style: 'currency', currency: currency }).format(amount);
    return formatted.replace('INR', '₹').trim();
}
