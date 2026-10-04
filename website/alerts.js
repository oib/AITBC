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
    const el = document.getElementById('monitor-strip');
    const parts = [];
    if (data.prometheus_ok) {
        parts.push('<span class="mon-ok">Prometheus: reachable</span>');
    } else {
        parts.push('<span class="mon-bad">Prometheus: unreachable</span> — showing the last state the watcher recorded');
    }
    const w = data.watcher;
    if (w) {
        if (!w.present) {
            parts.push('<span class="mon-bad">Watcher heartbeat: absent</span>');
        } else if (w.stale) {
            parts.push(`<span class="mon-bad">Watcher heartbeat: stale (${relTime(Date.now() / 1000 - w.last_poll_age_seconds)})</span>`);
        } else {
            parts.push(`<span class="mon-ok">Watcher: polled ${relTime(Date.now() / 1000 - w.last_poll_age_seconds)}</span>`);
        }
    } else if (!data.prometheus_ok) {
        parts.push('<span class="mon-warn">Watcher heartbeat: unknown (Prometheus down)</span>');
    }
    el.innerHTML = parts.join('<span class="mon-sep">&middot;</span>');
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

function renderFiring(data) {
    const box = document.getElementById('firing-container');
    const firing = data.firing || [];
    if (firing.length === 0) {
        box.innerHTML = '<p class="alerts-clear">No alerts firing.</p>';
    } else {
        box.innerHTML = firing.map(a => alertCard(a)).join('');
    }
    const pending = data.pending || [];
    const pbox = document.getElementById('pending-container');
    if (pending.length === 0) {
        pbox.style.display = 'none';
    } else {
        pbox.style.display = 'block';
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
    if (events.length === 0) {
        box.innerHTML = body.log_available === false
            ? '<p class="loading">No watcher event log on this host yet.</p>'
            : '<p class="loading">No alert events recorded.</p>';
        return;
    }
    box.innerHTML = `<table class="alerts-table">
        <thead><tr><th>When</th><th>Event</th><th>Alert</th><th>Node</th><th>Via</th><th>Detail</th></tr></thead>
        <tbody>${events.slice(0, 20).map(eventRow).join('')}</tbody>
    </table>`;
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
    if (entries.length === 0) {
        box.innerHTML = body.journal_access === false
            ? '<p class="loading">Journal not readable on this host yet (aitbc needs the systemd-journal group — deploying).</p>'
            : '<p class="loading">No warning-or-worse journal entries from aitbc units in the window.</p>';
        return;
    }
    box.innerHTML = `<table class="alerts-table">
        <thead><tr><th>When</th><th>Level</th><th>Unit</th><th>Message</th></tr></thead>
        <tbody>${entries.map(e => `<tr>
            <td class="evt-time">${escapeHtml(e.timestamp_unix ? relTime(e.timestamp_unix) : '')}</td>
            <td>${priBadge(e.priority, e.priority_name)}</td>
            <td class="evt-name">${escapeHtml(e.unit)}</td>
            <td class="evt-detail">${escapeHtml(e.message)}</td>
        </tr>`).join('')}</tbody>
    </table>`;
}

async function loadJournal() {
    const unit = document.getElementById('journal-unit').value;
    const priority = document.getElementById('journal-priority').value;
    const qs = `priority=${encodeURIComponent(priority)}&limit=50${unit ? '&unit=' + encodeURIComponent(unit) : ''}`;
    try {
        const resp = await fetch(`${EXPLORER_API_URL}/api/journal/recent?${qs}`);
        renderJournal(resp.ok ? await resp.json() : { entries: [], journal_access: false });
    } catch (err) {
        document.getElementById('journal-container').innerHTML =
            `<p class="loading">Journal endpoint unreachable — ${escapeHtml(err.message || err)}</p>`;
    }
}

async function loadAlerts() {
    try {
        const [liveResp, histResp] = await Promise.all([
            fetch(`${EXPLORER_API_URL}/api/alerts`),
            fetch(`${EXPLORER_API_URL}/api/alerts/history?limit=100`),
        ]);
        const live = await liveResp.json();
        const hist = await histResp.json();
        renderMonitorStrip(live);
        renderFiring(live);
        renderEvents(hist);
        document.getElementById('updated-note').textContent =
            `Updated ${new Date().toLocaleTimeString()} — auto-refresh every ${REFRESH_MS / 1000}s`;
    } catch (err) {
        document.getElementById('monitor-strip').innerHTML =
            `<span class="mon-bad">Alert API unreachable</span> — ${escapeHtml(err.message || err)}`;
    }
    await Promise.all([loadJournal(), loadJournalCounts()]);
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('journal-unit').addEventListener('change', loadJournal);
    document.getElementById('journal-priority').addEventListener('change', loadJournal);
    loadAlerts();
    setInterval(loadAlerts, REFRESH_MS);
});
