import { apiCall, showToast, formatDate, formatCurrency } from './api.js';
import { onAuthChange } from './auth.js';

export function initCrudPage(config) {
    const { entityName, apiUrl, fields, tableColumns, onSuccess, renderCustomActions } = config;
    const form = document.getElementById('create-form');
    const tableBody = document.getElementById('records-table-body');
    const clearBtn = document.getElementById('clear-btn');
    const submitBtn = document.getElementById('submit-btn');
    const editIdInput = document.getElementById('edit-id');

    let records = [];

    async function loadRecords() {
        try {
            const res = await apiCall(apiUrl);
            records = res.data || [];
            renderTable();
        } catch (error) {
            showToast(`Failed to load ${entityName}`, 'danger');
        }
    }

    function renderTable() {
        if (!tableBody) return;
        tableBody.innerHTML = '';
        if (records.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="${tableColumns.length + 1}" class="text-center py-4 q-muted-text">No records found</td></tr>`;
            return;
        }

        records.forEach(record => {
            const recId = record.id || record.doc_id || '';
            const tr = document.createElement('tr');

            tableColumns.forEach(col => {
                const td = document.createElement('td');
                let val = record[col.key];
                if (col.format === 'date') val = formatDate(val);
                else if (col.format === 'currency') val = val !== undefined && val !== null ? formatCurrency(parseFloat(val)) : '';
                else if (col.format === 'boolean') val = val ? 'Active' : 'Inactive';

                td.textContent = val !== undefined && val !== null ? val : '';
                tr.appendChild(td);
            });

            const actionTd = document.createElement('td');
            actionTd.className = 'text-nowrap';

            let extraButtons = '';
            if (renderCustomActions) {
                extraButtons = renderCustomActions(record);
            } else if (entityName.toLowerCase() === 'habit') {
                extraButtons = `<button class="btn btn-sm btn-outline-success checkin-btn me-1" data-id="${recId}" title="Check-In (+1 Streak)"><i class="bi bi-fire"></i> +1</button>`;
            }

            actionTd.innerHTML = `
                ${extraButtons}
                <button class="btn btn-sm btn-outline-primary edit-btn me-1" data-id="${recId}" title="Edit Record"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger delete-btn" data-id="${recId}" title="Delete Record"><i class="bi bi-trash"></i></button>
            `;
            tr.appendChild(actionTd);
            tableBody.appendChild(tr);
        });
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const data = {};
            fields.forEach(f => {
                const input = document.getElementById(`field-${f.name}`);
                if (input) {
                    if (f.type === 'checkbox') data[f.name] = input.checked;
                    else if (f.type === 'number') data[f.name] = parseFloat(input.value) || 0;
                    else data[f.name] = input.value;
                }
            });

            const id = editIdInput ? editIdInput.value : '';
            try {
                if (id) {
                    await apiCall(`${apiUrl}/${id}`, 'PUT', data);
                    showToast(`${entityName} updated successfully`, 'success');
                } else {
                    await apiCall(apiUrl, 'POST', data);
                    showToast(`${entityName} created successfully`, 'success');
                }

                // Hide modal if inside bootstrap modal
                const modalEl = form.closest('.modal');
                if (modalEl && window.bootstrap) {
                    const modal = window.bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }

                resetForm();
                if (onSuccess) onSuccess();
                loadRecords();
            } catch (error) {
                showToast(error.message || 'Operation failed', 'danger');
            }
        });
    }

    if (tableBody) {
        tableBody.addEventListener('click', async (e) => {
            const editBtn = e.target.closest('.edit-btn');
            const deleteBtn = e.target.closest('.delete-btn');
            const checkinBtn = e.target.closest('.checkin-btn');

            if (editBtn) {
                const id = editBtn.dataset.id;
                const record = records.find(r => (r.id === id || r.doc_id === id));
                if (record) {
                    fields.forEach(f => {
                        const input = document.getElementById(`field-${f.name}`);
                        if (input) {
                            if (f.type === 'checkbox') input.checked = !!record[f.name];
                            else input.value = record[f.name] !== undefined ? record[f.name] : '';
                        }
                    });
                    if (editIdInput) editIdInput.value = id;
                    if (submitBtn) submitBtn.textContent = 'Update Record';

                    // Show modal automatically
                    const modalEl = form ? form.closest('.modal') : document.querySelector('#addHabitModal, #addModal, .modal');
                    if (modalEl && window.bootstrap) {
                        const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
                        modal.show();
                    }
                }
            }

            if (checkinBtn) {
                const id = checkinBtn.dataset.id;
                const record = records.find(r => (r.id === id || r.doc_id === id));
                if (record) {
                    const curStreak = parseInt(record.current_streak || record.streak || 0);
                    const newStreak = curStreak + 1;
                    const todayIso = new Date().toISOString().split('T')[0];
                    checkinBtn.disabled = true;
                    try {
                        await apiCall(`${apiUrl}/${id}`, 'PUT', {
                            current_streak: newStreak,
                            streak: newStreak,
                            streak_count: newStreak,
                            last_completed: todayIso
                        });
                        showToast(`🔥 Logged +1 Streak check-in for '${record.name || 'Habit'}'!`, 'success');
                        if (onSuccess) onSuccess();
                        loadRecords();
                    } catch (error) {
                        showToast('Check-in failed: ' + error.message, 'danger');
                    } finally {
                        checkinBtn.disabled = false;
                    }
                }
            }

            if (deleteBtn) {
                const id = deleteBtn.dataset.id;
                if (confirm('Are you sure you want to delete this record?')) {
                    try {
                        await apiCall(`${apiUrl}/${id}`, 'DELETE');
                        showToast(`${entityName} deleted successfully`, 'success');
                        if (onSuccess) onSuccess();
                        loadRecords();
                    } catch (error) {
                        showToast(error.message, 'danger');
                    }
                }
            }
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', resetForm);
    }

    function resetForm() {
        if (form) form.reset();
        if (editIdInput) editIdInput.value = '';
        if (submitBtn) submitBtn.textContent = 'Save Record';
    }

    const unsubscribe = onAuthChange(user => {
        if (user) {
            unsubscribe();
            loadRecords();
        }
    });
}
