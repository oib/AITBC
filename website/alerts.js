// Network Alerts page — live firing alerts + watcher event history.
// Data: /api/alerts (Prometheus or event-log fallback) and /api/alerts/history
// on the blockchain-explorer backend, reached via the /explorer-api proxy.

const EXPLORER_API_URL = (window.AITBC_CONFIG && window.AITBC_CONFIG.explorerApiUrl) || '/explorer-api';
const REFRESH_MS = 30000;

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function relTime(isoOrUnix) {
    let then;
    if (typeof isoOrUnix === 'number') {
        then = isoOrUnix * 1000;
    } else {
        then = new Date(isoOrUnix).getTime();
    }
    if (isNaN(then)) return 'unknown';
    const s = Math.max(0, Math.round((Date.now() - then) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
    return `${Math.floor(s / 86400)}d ago`;
}

function sevClass(severity) {
    const s = String(severity || '').toLowerCase();
    if (s === 'critical') return 'sev-critical';
    if (s === 'warning') return 'sev-warning';
    if (s === 'info') return 'sev-info';
    return 'sev-unknown';
}

const EVENT_LABELS = {
    prometheus_alert_firing: ['FIRING', 'evt-firing'],
    prometheus_alert_resolved: ['RESOLVED', 'evt-resolved'],
    prometheus_alert_still_firing: ['STILL FIRING', 'evt-still'],
    prometheus_watch_started: ['WATCH START', 'evt-watch'],
};

function eventBadge(name) {
    const [label, cls] = EVENT_LABELS[name] || [String(name || 'event').replace(/^prometheus_/, '').toUpperCase(), 'evt-other'];
    return `<span class="evt-badge ${cls}">${escapeHtml(label)}</span>`;
}

function renderMonitorStrip(data) {
    // Rendered as Service Health tiles now — same status dot + label as the
    // API probes: Prometheus reachable?, watcher heartbeat fresh?
    updateHealthItem('prometheus', !!data.prometheus_ok, data.prometheus_ok ? 'reachable' : 'unreachable');
    const w = data.watcher;
    if (!w) {
        updateHealthItem('watcher', false, data.prometheus_ok ? 'not reported' : 'unknown');
    } else if (!w.present) {
        updateHealthItem('watcher', false, 'absent');
    } else if (w.stale) {
        updateHealthItem('watcher', false, 'stale ' + relTime(Date.now() / 1000 - w.last_poll_age_seconds));
    } else {
        updateHealthItem('watcher', true, 'polled ' + relTime(Date.now() / 1000 - w.last_poll_age_seconds));
    }
}

function alertCard(a, extraClass) {
    const labels = a.labels || {};
    const node = a.node || labels.instance || '';
    const sev = a.severity || 'unknown';
    return `
    <div class="alert-card ${sevClass(sev)}${extraClass ? ' ' + extraClass : ''}">
        <div class="alert-card-head">
            <span class="sev-badge">${escapeHtml(sev)}</span>
            <span class="alert-name">${escapeHtml(a.alertname || 'unknown')}</span>
            ${node ? `<span class="alert-node">${escapeHtml(node)}</span>` : ''}
            ${a.silenced ? '<span class="silenced-tag">silenced</span>' : ''}
            <span class="alert-since">${a.active_at ? 'since ' + relTime(a.active_at) : ''}</span>
        </div>
        ${a.summary ? `<div class="alert-summary">${escapeHtml(a.summary)}</div>` : ''}
    </div>`;
}

function renderSummary(data) {
    const box = document.getElementById('alerts-summary');
    if (!box) return;
    const title = box.querySelector('.alerts-summary-title');
    const detail = box.querySelector('.alerts-summary-detail');
    let state, head, tail;
    if (!data || data.prometheus_ok !== true) {
        // Green requires a proven live answer: prometheus_ok === true plus a
        // vouching watcher below. Everything else — API down, event-log
        // fallback, or a body with no such field at all — is unknown.
        const firing = (data && data.firing) || [];
        state = 'is-unknown';
        head = 'Alert state unknown';
        if (!data) {
            tail = 'The alerts API did not answer.';
        } else if (data.prometheus_ok === false) {
            tail = 'Prometheus is unreachable; the list below is the watcher log\'s last known state' +
                (firing.length ? ` (${firing.length} alert${firing.length === 1 ? '' : 's'} in it).` : '.');
        } else {
            tail = 'The alerts API returned an unexpected answer.';
        }
    } else {
        const firing = data.firing || [], pending = data.pending || [];
        const bySev = {};
        firing.forEach(a => { const s = (a.severity || 'unknown').toLowerCase(); bySev[s] = (bySev[s] || 0) + 1; });
        const parts = Object.keys(bySev).map(s => `${bySev[s]} ${s}`);
        if (firing.length === 0 && pending.length === 0) { state = 'is-clear'; head = 'No alerts firing'; }
        else if (firing.length === 0) { state = 'is-pending'; head = `No alerts firing, ${pending.length} pending`; }
        else { state = 'is-firing'; head = `${firing.length} alert${firing.length === 1 ? '' : 's'} firing` + (pending.length ? `, ${pending.length} pending` : ''); }
        tail = parts.join(', ');
        const w = data.watcher;
        if (w && w.present && !w.stale) {
            tail += (tail ? '. ' : '') + 'Watcher polled ' + relTime(Date.now() / 1000 - w.last_poll_age_seconds) + '.';
        } else {
            // A stale or absent watcher cannot vouch for the list —
            // clear demotes to unknown (amber title included, so the
            // headline and the colour say the same thing); firing/pending
            // keep their state. present:false arrives with stale:true
            // from the backend — check presence first so the wording
            // says "absent".
            if (state === 'is-clear') {
                state = 'is-unknown';
                head = 'Alert state unknown';
                tail = 'Prometheus answered: no alerts firing';
            }
            tail += (tail ? '. ' : '') + (w && w.present && w.stale ? 'Watcher heartbeat is stale.' : 'Watcher heartbeat is absent.');
        }
    }
    box.className = 'alerts-summary ' + state;
    title.textContent = head;
    detail.textContent = tail || '';
}

function renderFiring(data) {
    const box = document.getElementById('firing-container');
    const aStatus = document.getElementById('sr-announcer');
    let sig, announce;
    if (!data || data.prometheus_ok !== true) {
        // Not a proven live answer — the card must never claim all-clear.
        // The event-log fallback may still carry the watcher's last-known
        // firing set; it is labelled as a replay, never as a live list.
        if (data && data.prometheus_ok === false) {
            const firing = data.firing || [];
            box.innerHTML = firing.length
                ? '<p class="alerts-unknown">Prometheus is unreachable — the cards below are the watcher log\u2019s last known state, not a live answer:</p>' +
                  firing.map(a => alertCard(a)).join('')
                : '<p class="alerts-unknown">Alert state unknown — Prometheus is unreachable and the watcher log records no firing alerts.</p>';
        } else {
            box.innerHTML = `<p class="alerts-unknown">${escapeHtml(!data
                ? 'Alert state unknown — the alerts API did not answer.'
                : 'Alert state unknown — the alerts API returned an unexpected answer.')}</p>`;
        }
        sig = '__unknown__';
        announce = 'Alert state unknown';
    } else {
        const firing = data.firing || [];
        box.innerHTML = firing.length === 0
            ? '<p class="alerts-clear">No alerts firing.</p>'
            : firing.map(a => alertCard(a)).join('');
        sig = firing.map(a => a.alertname + '@' + (a.node || '')).join('|');
        announce = firing.length ? `${firing.length} alert${firing.length === 1 ? '' : 's'} firing` : 'No alerts firing';
    }
    if (aStatus && sig !== window.__lastAlertSig) {
        window.__lastAlertSig = sig;
        aStatus.textContent = announce;
    }
    const pending = (data && data.prometheus_ok === true && data.pending) || [];
    const pbox = document.getElementById('pending-container');
    if (pending.length === 0) {
        pbox.hidden = true;
    } else {
        pbox.hidden = false;
        document.getElementById('pending-list').innerHTML = pending.map(a => alertCard(a, 'alert-pending')).join('');
    }
}

function eventRow(e) {
    const labels = e.labels || {};
    const node = labels.node || labels.instance || '';
    const when = e.timestamp_unix || e.timestamp || '';
    let detail = e.summary || e.silence_reason || '';
    if (e.event === 'prometheus_watch_started') {
        detail = `watching ${e.firing_count ?? '?'} alert(s)`;
    } else if (e.event === 'prometheus_alert_resolved' && e.duration_seconds != null) {
        const m = Math.round(e.duration_seconds / 60);
        detail = (detail ? detail + ' — ' : '') + `lasted ${m < 1 ? '<1' : m}m`;
    }
    return `<tr>
        <td class="evt-time">${escapeHtml(when ? relTime(when) : '')}</td>
        <td>${eventBadge(e.event)}${e.silenced ? ' <span class="silenced-tag">silenced</span>' : ''}</td>
        <td class="evt-name">${escapeHtml(e.alertname || '—')}</td>
        <td>${escapeHtml(node)}</td>
        <td class="evt-via">${escapeHtml(e.via || '')}</td>
        <td class="evt-detail">${escapeHtml(detail)}</td>
    </tr>`;
}

function renderEvents(body) {
    const box = document.getElementById('events-container');
    const events = body.events || [];
    if (body.__events_error) {
        if (box.querySelector('.table-wrap')) {
            let note = box.querySelector('.endpoint-note');
            if (!note) {
                note = document.createElement('p');
                note.className = 'endpoint-note';
                box.prepend(note);
            }
            note.textContent = `Refresh failed (${body.__events_error}) — showing last good history.`;
            return;
        }
        box.innerHTML = `<p class="alerts-unknown">Alert event history unavailable (${escapeHtml(body.__events_error)}) — retrying automatically.</p>`;
        return;
    }
    if (events.length === 0) {
        box.innerHTML = body.log_available === false
            ? '<p class="loading">No watcher event log on this host yet.</p>'
            : '<p class="loading">No alert events recorded.</p>';
        return;
    }
    box.innerHTML = `<div class="table-wrap" role="region" tabindex="0" aria-label="Alert event history"><table class="alerts-table" aria-label="Alert event history">
        <thead><tr><th scope="col">When</th><th scope="col">Event</th><th scope="col">Alert</th><th scope="col">Node</th><th scope="col">Via</th><th scope="col">Detail</th></tr></thead>
        <tbody>${events.slice(0, 20).map(eventRow).join('')}</tbody>
    </table></div>`;
}

const JOURNAL_UNITS = new Set();

function renderJournalNodes(body) {
    const el = document.getElementById('journal-nodes');
    if (!body || !body.prometheus_ok) {
        el.innerHTML = '<span class="mon-warn">fleet counts unavailable</span>';
        return;
    }
    const nodes = body.nodes || [];
    if (nodes.length === 0) {
        el.innerHTML = '<span class="mon-warn">no collector metrics yet</span>';
        return;
    }
    el.innerHTML = nodes.map(n => {
        const cls = n.stale ? 'mon-warn' : (n.errors > 0 ? 'mon-bad' : (n.warnings > 0 ? 'mon-warn' : 'mon-ok'));
        const text = n.stale
            ? `collector stale (${relTime(Date.now() / 1000 - (n.scan_age_seconds || 0))})`
            : `${n.errors} err &middot; ${n.warnings} warn`;
        return `<span class="jn-chip ${cls}">${escapeHtml(n.node)}: ${text}</span>`;
    }).join(' ');
}

async function loadJournalCounts() {
    try {
        const resp = await fetch(`${EXPLORER_API_URL}/api/journal/counts`);
        renderJournalNodes(resp.ok ? await resp.json() : { prometheus_ok: false });
    } catch (err) {
        document.getElementById('journal-nodes').innerHTML = '<span class="mon-warn">fleet counts unreachable</span>';
    }
}

function priBadge(priority, name) {
    const cls = priority <= 3 ? 'evt-firing' : 'evt-still';
    return `<span class="evt-badge ${cls}">${escapeHtml(name || priority)}</span>`;
}

function renderJournal(body) {
    const box = document.getElementById('journal-container');
    const entries = body.entries || [];
    entries.forEach(e => JOURNAL_UNITS.add(e.unit));
    const sel = document.getElementById('journal-unit');
    const wanted = sel.value;
    const known = [...JOURNAL_UNITS].sort();
    sel.innerHTML = '<option value="">all aitbc units</option>' +
        known.map(u => `<option${u === wanted ? ' selected' : ''} value="${escapeHtml(u)}">${escapeHtml(u)}</option>`).join('');
    if (body.__journal_error) {
        if (box.querySelector('.table-wrap')) {
            let note = box.querySelector('.endpoint-note');
            if (!note) {
                note = document.createElement('p');
                note.className = 'endpoint-note';
                box.prepend(note);
            }
            note.textContent = `Refresh failed (${body.__journal_error}) — showing last good journal.`;
            return;
        }
        box.innerHTML = `<p class="alerts-unknown">Journal unavailable (${escapeHtml(body.__journal_error)}).</p>`;
        return;
    }
    if (entries.length === 0) {
        box.innerHTML = body.journal_access === false
            ? '<p class="loading">Journal not readable on this host yet (aitbc needs the systemd-journal group — deploying).</p>'
            : '<p class="loading">No warning-or-worse journal entries from aitbc units in the window.</p>';
        return;
    }
    box.innerHTML = `<div class="table-wrap" role="region" tabindex="0" aria-label="Journal entries"><table class="alerts-table" aria-label="Journal entries">
        <thead><tr><th scope="col">When</th><th scope="col">Level</th><th scope="col">Unit</th><th scope="col">Message</th></tr></thead>
        <tbody>${entries.map(e => `<tr>
            <td class="evt-time">${escapeHtml(e.timestamp_unix ? relTime(e.timestamp_unix) : '')}</td>
            <td>${priBadge(e.priority, e.priority_name)}</td>
            <td class="evt-name">${escapeHtml(e.unit)}</td>
            <td class="evt-detail">${escapeHtml(e.message)}</td>
        </tr>`).join('')}</tbody>
    </table></div>`;
}

async function loadJournal() {
    const unit = document.getElementById('journal-unit').value;
    const priority = document.getElementById('journal-priority').value;
    const qs = `priority=${encodeURIComponent(priority)}&limit=50${unit ? '&unit=' + encodeURIComponent(unit) : ''}`;
    try {
        const resp = await fetch(`${EXPLORER_API_URL}/api/journal/recent?${qs}`);
        renderJournal(resp.ok ? await resp.json() : { entries: [], __journal_error: `HTTP ${resp.status}` });
    } catch (err) {
        renderJournal({ entries: [], __journal_error: err.message || String(err) });
    }
}

async function loadAlerts() {
    try {
        const [liveResp, histResp] = await Promise.all([
            fetch(`${EXPLORER_API_URL}/api/alerts`),
            fetch(`${EXPLORER_API_URL}/api/alerts/history?limit=100`),
        ]);
        const live = liveResp.ok ? await liveResp.json() : null;
        const hist = histResp.ok ? await histResp.json() : { __events_error: `HTTP ${histResp.status}` };
        renderSummary(live);
        renderMonitorStrip(live || {});
        renderFiring(live);
        renderEvents(hist);
        document.getElementById('updated-note').textContent =
            `Updated ${aitbcFmt.time()} — auto-refresh every ${REFRESH_MS / 1000}s`;
    } catch (err) {
        renderSummary(null);
        renderFiring(null);
        renderEvents({ __events_error: 'unreachable' });
        updateHealthItem('prometheus', false, 'API unreachable');
        updateHealthItem('watcher', false, 'unreachable');
        console.error('Alert API unreachable:', err);
    }
    await Promise.all([loadJournal(), loadJournalCounts()]);
}

// Service health check — same up/down probe the marketplace card ran,
// now fronting the alerts/journal status view.
async function checkServiceHealth() {
    const services = [
        { name: 'marketplace', url: '/v1/market/status' },
        { name: 'explorer', url: '/explorer-api/api/chain/head' },
        { name: 'coordinator', url: '/c/health' },
    ];

    // Probes run in parallel — a serial round would stretch the checking
    // state to three times the slowest answer.
    await Promise.all(services.map(async (svc) => {
        const start = performance.now();
        try {
            const response = await fetch(svc.url, { method: 'GET' });
            const latency = Math.round(performance.now() - start);
            updateHealthItem(svc.name, response.ok, response.ok ? `${latency}ms` : `HTTP ${response.status}`);
        } catch (e) {
            updateHealthItem(svc.name, false, 'unreachable');
        }
    }));
}

function updateHealthItem(name, up, latency) {
    const item = document.querySelector(`.health-item[data-service="${name}"]`);
    if (!item) return;
    item.removeAttribute('aria-busy');
    const statusEl = item.querySelector('.health-status');
    const latencyEl = item.querySelector('.health-latency');
    statusEl.className = 'health-status ' + (up ? 'up' : 'down');
    latencyEl.textContent = up ? latency : (latency || 'unreachable');
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('journal-unit').addEventListener('change', loadJournal);
    document.getElementById('journal-priority').addEventListener('change', loadJournal);
    checkServiceHealth();
    setInterval(checkServiceHealth, REFRESH_MS);
    loadAlerts();
    setInterval(loadAlerts, REFRESH_MS);
});
