/**
 * MB Associates Solar Website — Staff Operations Queue Script
 * Handles live queue listing, debounced search, status filtering,
 * modal details, status updates, and internal staff notes.
 */

let currentEnquiries = [];
let activeEnquiryId = null;
let searchDebounceTimer = null;

document.addEventListener('DOMContentLoaded', function () {
  loadEnquiries();

  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        loadEnquiries();
      }, 300);
    });
  }

  const statusFilter = document.getElementById('status-filter');
  if (statusFilter) {
    statusFilter.addEventListener('change', function () {
      loadEnquiries();
    });
  }
});

async function loadEnquiries() {
  const tbody = document.getElementById('enquiries-table-body');
  const emptyState = document.getElementById('empty-state');
  const searchInput = document.getElementById('search-input');
  const statusFilter = document.getElementById('status-filter');

  const search = searchInput ? searchInput.value.trim() : '';
  const status = statusFilter ? statusFilter.value : 'All';

  // Show loading in table
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="py-12 text-center text-on-surface-variant">
          <div class="inline-flex items-center gap-2">
            <span class="material-symbols-outlined animate-spin text-secondary text-[22px]">progress_activity</span>
            <span>Fetching staff operations queue...</span>
          </div>
        </td>
      </tr>
    `;
  }
  if (emptyState) emptyState.classList.add('hidden');

  try {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (status && status !== 'All') params.append('status', status);

    const resp = await fetch(`/api/staff/enquiries?${params.toString()}`, {
      headers: { 'Accept': 'application/json' }
    });

    if (resp.status === 401) {
      window.location.href = '/staff/login';
      return;
    }

    if (!resp.ok) {
      throw new Error(`Failed to load enquiries: ${resp.status}`);
    }

    const data = await resp.json();
    currentEnquiries = data;

    updateTelemetryCounters(data);
    renderTable(data);

  } catch (error) {
    console.error('Error loading enquiries:', error);
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="py-8 text-center text-red-600">
            <div class="inline-flex items-center gap-2">
              <span class="material-symbols-outlined text-[20px]">error</span>
              <span>Failed to load enquiries from server. Check connection or verify database status.</span>
            </div>
          </td>
        </tr>
      `;
    }
  }
}

function updateTelemetryCounters(enquiries) {
  const totalEl = document.getElementById('count-total');
  const newEl = document.getElementById('count-new');
  const inProgressEl = document.getElementById('count-in-progress');

  if (totalEl) totalEl.textContent = enquiries.length;
  if (newEl) newEl.textContent = enquiries.filter(e => e.status === 'New').length;
  if (inProgressEl) inProgressEl.textContent = enquiries.filter(e => e.status === 'In Progress').length;
}

function renderTable(enquiries) {
  const tbody = document.getElementById('enquiries-table-body');
  const emptyState = document.getElementById('empty-state');

  if (!tbody) return;
  tbody.innerHTML = '';

  if (!enquiries || enquiries.length === 0) {
    if (emptyState) emptyState.classList.remove('hidden');
    return;
  }
  if (emptyState) emptyState.classList.add('hidden');

  enquiries.forEach(enq => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-50 transition-colors cursor-pointer border-b border-border-subtle';
    tr.onclick = (e) => {
      // Don't trigger if clicked directly on an action button
      if (e.target.closest('button')) return;
      openEnquiryDetail(enq.id);
    };

    const statusPill = getStatusPillHtml(enq.status);
    const dateFormatted = enq.created_at ? formatDate(enq.created_at) : '--';
    const notesBadge = enq.notes_count > 0 
      ? `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-bold"><span class="material-symbols-outlined text-[12px]">note</span>${enq.notes_count}</span>` 
      : '';

    tr.innerHTML = `
      <td class="py-3.5 px-4 font-mono font-semibold text-secondary whitespace-nowrap">
        ${escapeHtml(enq.reference)}
      </td>
      <td class="py-3.5 px-4 font-semibold text-on-surface">
        <div class="flex items-center gap-1.5">
          <span>${escapeHtml(enq.name)}</span>
          ${notesBadge}
        </div>
      </td>
      <td class="py-3.5 px-4 text-xs font-mono">
        <div>${escapeHtml(enq.contact_detail)}</div>
        <span class="text-[10px] text-slate-400 uppercase">${escapeHtml(enq.contact_method)}</span>
      </td>
      <td class="py-3.5 px-4 font-mono text-xs">${escapeHtml(enq.pin_code)}</td>
      <td class="py-3.5 px-4 text-xs text-on-surface-variant">${escapeHtml(enq.property_type)}</td>
      <td class="py-3.5 px-4">
        <span class="px-2 py-0.5 rounded text-[11px] font-medium ${enq.request_type === 'site_visit' ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-700'}">
          ${enq.request_type === 'site_visit' ? 'Site Visit' : 'General'}
        </span>
      </td>
      <td class="py-3.5 px-4">${statusPill}</td>
      <td class="py-3.5 px-4 text-xs text-slate-400 whitespace-nowrap">${dateFormatted}</td>
      <td class="py-3.5 px-4 text-right">
        <button
          onclick="openEnquiryDetail('${enq.id}')"
          class="px-2.5 py-1 rounded-lg bg-surface-container hover:bg-slate-200 text-xs font-semibold text-on-surface transition-colors"
        >
          View
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function getStatusPillHtml(status) {
  let colorClasses = 'bg-slate-100 text-slate-800 border-slate-300';
  if (status === 'New') {
    colorClasses = 'bg-amber-50 text-amber-800 border-amber-300';
  } else if (status === 'Contacted') {
    colorClasses = 'bg-blue-50 text-blue-800 border-blue-300';
  } else if (status === 'In Progress') {
    colorClasses = 'bg-indigo-50 text-indigo-800 border-indigo-300';
  } else if (status === 'Closed') {
    colorClasses = 'bg-emerald-50 text-emerald-800 border-emerald-300';
  }
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${colorClasses}">${escapeHtml(status)}</span>`;
}

async function openEnquiryDetail(enquiryId) {
  activeEnquiryId = enquiryId;
  const modal = document.getElementById('detail-modal');
  if (!modal) return;

  modal.classList.remove('hidden');

  try {
    const resp = await fetch(`/api/staff/enquiries/${enquiryId}`, {
      headers: { 'Accept': 'application/json' }
    });

    if (!resp.ok) {
      alert('Failed to retrieve enquiry details.');
      closeModal();
      return;
    }

    const data = await resp.json();

    // Populate modal fields
    document.getElementById('modal-ref').textContent = data.reference;
    document.getElementById('modal-name').textContent = data.name;
    document.getElementById('modal-contact').textContent = data.contact_detail;
    document.getElementById('modal-method-badge').textContent = data.contact_method;
    document.getElementById('modal-pin').textContent = data.pin_code;
    document.getElementById('modal-property').textContent = data.property_type;
    document.getElementById('modal-roof-area').textContent = data.roof_area || 'Not specified';
    document.getElementById('modal-monthly-bill').textContent = data.monthly_bill ? `₹${data.monthly_bill}` : 'Not specified';
    document.getElementById('modal-notes').textContent = data.notes || 'None provided by customer';
    document.getElementById('modal-created-at').textContent = `Received: ${formatDate(data.created_at)}`;

    // Status
    const statusSelect = document.getElementById('update-status-select');
    if (statusSelect) statusSelect.value = data.status;
    const badge = document.getElementById('modal-status-badge');
    if (badge) {
      badge.textContent = data.status;
      badge.className = 'px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ' + 
        (data.status === 'New' ? 'bg-amber-100 text-amber-800' :
         data.status === 'Contacted' ? 'bg-blue-100 text-blue-800' :
         data.status === 'In Progress' ? 'bg-indigo-100 text-indigo-800' : 'bg-emerald-100 text-emerald-800');
    }

    // Assistance chips
    const assistanceContainer = document.getElementById('modal-assistance');
    if (assistanceContainer) {
      assistanceContainer.innerHTML = '';
      (data.assistance || []).forEach(scope => {
        const span = document.createElement('span');
        span.className = 'px-2.5 py-1 rounded-lg bg-surface-container text-xs font-semibold text-on-surface';
        span.textContent = scope;
        assistanceContainer.appendChild(span);
      });
    }

    // Notes list
    renderStaffNotes(data.staff_notes || []);

  } catch (error) {
    console.error('Error fetching detail:', error);
  }
}

function renderStaffNotes(notes) {
  const container = document.getElementById('modal-notes-list');
  if (!container) return;
  container.innerHTML = '';

  if (!notes || notes.length === 0) {
    container.innerHTML = `
      <div class="p-3 rounded-xl bg-surface-container-low text-xs text-slate-400 italic text-center">
        No internal notes added yet. Add a note below to record calls, vendor coordination, or DISCOM status.
      </div>
    `;
    return;
  }

  notes.forEach(note => {
    const div = document.createElement('div');
    div.className = 'p-3 rounded-xl bg-surface-container-low border border-border-subtle flex flex-col gap-1 text-xs';
    div.innerHTML = `
      <div class="flex items-center justify-between text-[11px] text-slate-400">
        <strong class="text-on-surface font-semibold">${escapeHtml(note.staff_name || 'Staff Coordinator')}</strong>
        <span>${formatDate(note.created_at)}</span>
      </div>
      <p class="text-on-surface leading-relaxed whitespace-pre-wrap">${escapeHtml(note.content)}</p>
    `;
    container.appendChild(div);
  });
}

async function saveStatusUpdate() {
  if (!activeEnquiryId) return;
  const select = document.getElementById('update-status-select');
  const saveBtn = document.getElementById('save-status-btn');
  const newStatus = select.value;

  if (saveBtn) saveBtn.disabled = true;

  try {
    const resp = await fetch(`/api/staff/enquiries/${activeEnquiryId}/status`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ status: newStatus })
    });

    if (!resp.ok) {
      alert('Failed to update status.');
      return;
    }

    // Refresh modal badge
    const badge = document.getElementById('modal-status-badge');
    if (badge) {
      badge.textContent = newStatus;
      badge.className = 'px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ' + 
        (newStatus === 'New' ? 'bg-amber-100 text-amber-800' :
         newStatus === 'Contacted' ? 'bg-blue-100 text-blue-800' :
         newStatus === 'In Progress' ? 'bg-indigo-100 text-indigo-800' : 'bg-emerald-100 text-emerald-800');
    }

    // Refresh queue list in background
    loadEnquiries();

  } catch (error) {
    console.error('Error saving status:', error);
    alert('Network error updating status.');
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function submitStaffNote() {
  if (!activeEnquiryId) return;
  const textarea = document.getElementById('new-note-content');
  const btn = document.getElementById('add-note-btn');
  const content = (textarea.value || '').trim();

  if (!content) return;
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch(`/api/staff/enquiries/${activeEnquiryId}/notes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ content })
    });

    if (!resp.ok) {
      alert('Failed to add note.');
      return;
    }

    const note = await resp.json();
    textarea.value = '';

    // Re-fetch detail to refresh notes list cleanly
    const detailResp = await fetch(`/api/staff/enquiries/${activeEnquiryId}`);
    if (detailResp.ok) {
      const data = await detailResp.json();
      renderStaffNotes(data.staff_notes || []);
    }

  } catch (error) {
    console.error('Error submitting note:', error);
    alert('Network error submitting note.');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function closeModal() {
  const modal = document.getElementById('detail-modal');
  if (modal) modal.classList.add('hidden');
  activeEnquiryId = null;
}

function formatDate(isoString) {
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (e) {
    return isoString;
  }
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
