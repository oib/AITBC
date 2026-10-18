// Clickable rows carry data-href instead of inline onclick/onkeydown, so
// pages work under a Content-Security-Policy with script-src 'self' (inline
// event handlers are blocked there). One delegated pair of listeners covers
// every [data-href] row on the page, including ones rendered later.
// Only same-site paths ("/..." but not "//...") are followed. Clicks on nested
// controls are left alone; copy buttons already stop propagation in copy.js.
(function () {
    function target(ev) {
        var row = ev.target && ev.target.closest ? ev.target.closest('[data-href]') : null;
        if (!row) return null;
        var href = row.getAttribute('data-href') || '';
        return /^\/(?!\/)/.test(href) ? href : null;
    }
    document.addEventListener('click', function (ev) {
        if (ev.target.closest && ev.target.closest('a, button, input, select, textarea, summary')) return;
        var href = target(ev);
        if (href) location.href = href;
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter' || !ev.target.hasAttribute || !ev.target.hasAttribute('data-href')) return;
        var href = target(ev);
        if (href) location.href = href;
    });
})();
