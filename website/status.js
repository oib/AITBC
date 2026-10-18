// AITBC hub status strip — progressive enhancement only.
// Renders chain head height + age and the firing-alerts count into the
// .status-strip container that every page carries in its static HTML.
// Pages are complete without this file: on any failure the strip shows a
// muted "status unavailable" and polling backs off, then stops.
//
// Endpoints (same-origin, public):
//   /explorer-api/api/chain/head   -> {height, timestamp}
//   /explorer-api/api/alerts       -> {firing: [...], prometheus_ok, watcher}
(function () {
    'use strict';

    // Shared number/date format (WEB-PAGES-1, operator choice): one fixed
    // convention on every page — numbers in en-US, dates ISO-style
    // "YYYY-MM-DD HH:mm", clock times 24-hour HH:MM:SS. Defined here because
    // status.js is the only script every page loads. Exposed before the
    // early return so a page without a strip still gets the helpers.
    window.aitbcFmt = {
        num: function (v, maxDigits) {
            var n = Number(v);
            if (!isFinite(n)) return '-';
            return maxDigits == null
                ? n.toLocaleString('en-US')
                : n.toLocaleString('en-US', { maximumFractionDigits: maxDigits });
        },
        date: function (v) {
            // No argument means "now" (the common clock-stamp call).
            var t = (v == null) ? new Date() : (v instanceof Date) ? v : new Date(v);
            if (isNaN(t.getTime())) return '-';
            var p = function (n) { return String(n).padStart(2, '0'); };
            return t.getFullYear() + '-' + p(t.getMonth() + 1) + '-' + p(t.getDate()) + ' ' + p(t.getHours()) + ':' + p(t.getMinutes());
        },
        time: function (v) {
            var t = (v == null) ? new Date() : (v instanceof Date) ? v : new Date(v);
            if (isNaN(t.getTime())) return '';
            return t.toLocaleTimeString('en-GB');
        }
    };

    // Back-to-top button (shared by every page that loads status.js).
    // Injected here so no page needs extra markup; hidden until the visitor
    // has scrolled a screen or so. Placed before the .status-strip early
    // return so pages without a strip still get it.
    (function backToTop() {
        if (document.querySelector('.back-to-top')) { return; }
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'back-to-top';
        btn.setAttribute('aria-label', 'Back to top');
        btn.title = 'Back to top';
        btn.textContent = '↑';
        btn.addEventListener('click', function () {
            // scroll-behavior is neutralised by prefers-reduced-motion in CSS.
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
        var ticking = false;
        function update() {
            ticking = false;
            btn.classList.toggle('back-to-top-on', window.scrollY > 400);
        }
        window.addEventListener('scroll', function () {
            if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
        }, { passive: true });
        document.body.appendChild(btn);
        update();
    })();

    var POLL_MS = 45000;            // one request per endpoint per cycle; >= 30 s
    var JITTER_MS = 8000;           // desynchronize visitors
    var STALE_AFTER_MS = 300000;    // ~4.5x the ~67 s block cadence -> "stale"
    var SKEW_TOLERANCE_MS = 60000;  // viewer clock this far ahead -> hide age
    var MAX_FAILURES = 4;           // then stop until user returns/interacts
    var BACKOFF_CAP_MS = 300000;

    var strip = document.querySelector('.status-strip');
    if (!strip) {
        return;
    }

    var failures = 0;
    var timer = null;
    var stopped = false;

    function show() {
        strip.classList.add('status-on');
    }

    function muted(text) {
        strip.textContent = text;
        strip.classList.add('status-unavailable');
        show();
    }

    function fmtAge(ms) {
        var s = Math.round(ms / 1000);
        if (s < 60) { return s + 's ago'; }
        var m = Math.floor(s / 60);
        if (m < 60) { return m + 'm ago'; }
        var h = Math.floor(m / 60);
        if (h < 24) { return h + 'h ago'; }
        return Math.floor(h / 24) + 'd ago';
    }

    function render(head, alerts) {
        if (!head && !alerts) {
            muted('network status unavailable');
            return false;
        }
        var frag = document.createDocumentFragment();
        var ok = false;

        if (head && typeof head.height === 'number') {
            var h = document.createElement('span');
            h.className = 'status-part';
            var label = 'height ' + head.height;
            if (head.timestamp) {
                var age = Date.now() - Date.parse(head.timestamp + 'Z');
                if (isNaN(age) || age <= -SKEW_TOLERANCE_MS) {
                    // Unparseable timestamp or viewer clock ahead of chain — no age claim
                    label += ' · live';
                } else {
                    if (age < 0) { age = 0; }
                    label += ' · ' + (age <= STALE_AFTER_MS ? 'live' : 'stale') + ' ' + fmtAge(age);
                }
            }
            h.textContent = label;
            frag.appendChild(h);
            ok = true;
        }

        var sep = document.createElement('span');
        sep.className = 'status-sep';
        sep.textContent = '·';
        frag.appendChild(sep);

        var a = document.createElement('a');
        a.href = '/alerts.html';
        a.className = 'status-part';
        var firing = alerts && Array.isArray(alerts.firing) ? alerts.firing : null;
        var freshWatcher = !!(alerts && alerts.watcher &&
            alerts.watcher.present !== false && alerts.watcher.stale !== true);
        // Firing count is a live Prometheus answer — show it even when the
        // watcher can't vouch. The "no alerts" claim needs both.
        if (alerts && alerts.prometheus_ok === true && firing &&
            (firing.length > 0 || freshWatcher)) {
            var n = firing.length;
            a.textContent = n === 0 ? 'no alerts firing' : n + ' alert' + (n === 1 ? '' : 's') + ' firing';
            ok = true;
        } else if (alerts) {
            a.textContent = 'alerts unknown';
            a.classList.add('status-unavailable');
        } else {
            a.textContent = 'alerts unavailable';
            a.classList.add('status-unavailable');
        }
        frag.appendChild(a);

        strip.textContent = '';
        strip.appendChild(frag);
        strip.classList.remove('status-unavailable');
        show();
        return ok;
    }

    function getJSON(path) {
        return fetch(path, { headers: { 'Accept': 'application/json' } }).then(function (r) {
            return r.ok ? r.json() : null;
        }).catch(function () { return null; });
    }

    function tick() {
        Promise.all([
            getJSON('/explorer-api/api/chain/head'),
            getJSON('/explorer-api/api/alerts')
        ]).then(function (rs) {
            var ok = render(rs[0], rs[1]);
            failures = ok ? 0 : failures + 1;
            if (failures >= MAX_FAILURES) {
                stopped = true;
                return;  // resumes on visibilitychange / user interaction
            }
            schedule();
        });
    }

    function schedule() {
        if (stopped || document.hidden) { return; }
        var delay = Math.min(POLL_MS * Math.pow(2, failures), BACKOFF_CAP_MS);
        delay += Math.floor(Math.random() * JITTER_MS);
        timer = setTimeout(tick, delay);
    }

    function resume() {
        if (document.hidden) { return; }
        stopped = false;
        failures = 0;
        clearTimeout(timer);
        tick();
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            clearTimeout(timer);
        } else {
            resume();
        }
    });
    window.addEventListener('focus', resume);
    document.addEventListener('click', function once() {
        if (stopped) { resume(); }
    });

    tick();
})();
