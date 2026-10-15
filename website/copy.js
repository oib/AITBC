// Shared copy control for truncated hashes and addresses (WEB-FIX-2).
// One implementation for every page: pages emit buttons via
// aitbcCopyBtn(value, what) — or static markup with data-copy="<full>"
// / data-copy-from="<element id>" — and a delegated click handler does the
// rest. Values always come from DOM data already on the page (a data-
// attribute or an element's own text), never from a re-fetch.
(function () {
    'use strict';

    function esc(s) {
        return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    // One shared polite live region. Most pages already carry
    // #sr-announcer; pages without one get it created on demand.
    function announcer() {
        var el = document.getElementById('sr-announcer');
        if (!el) {
            el = document.createElement('span');
            el.id = 'sr-announcer';
            el.className = 'visually-hidden';
            el.setAttribute('role', 'status');
            el.setAttribute('aria-live', 'polite');
            document.body.appendChild(el);
        }
        return el;
    }

    function announce(msg) {
        var s = announcer();
        s.textContent = '';
        setTimeout(function () { s.textContent = msg; }, 50);
    }

    // Swap the visible label briefly; the button's own aria-live plus the
    // shared region announce the outcome. textContent only — no sink.
    function flash(btn, text, cls) {
        if (btn._copyTimer) clearTimeout(btn._copyTimer);
        btn.textContent = text;
        btn.classList.remove('copy-ok', 'copy-fail');
        if (cls) btn.classList.add(cls);
        btn._copyTimer = setTimeout(function () {
            btn.textContent = 'copy';
            btn.classList.remove('copy-ok', 'copy-fail');
            btn._copyTimer = null;
        }, 1500);
    }

    // Non-secure-context fallback: select the value in a textarea and use
    // execCommand. If even that fails, leave the pre-selected text visible
    // so the user can press Ctrl+C — failure is shown, never swallowed.
    function fallbackCopy(text, btn) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.className = 'copy-fallback';
        ta.setAttribute('readonly', '');
        document.body.appendChild(ta);
        ta.select();
        ta.setSelectionRange(0, ta.value.length);
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        if (ok) {
            document.body.removeChild(ta);
            announce('Copied to clipboard');
            flash(btn, 'copied', 'copy-ok');
            return;
        }
        ta.classList.add('copy-fallback-visible');
        ta.focus();
        ta.select();
        announce('Copy failed — text selected, press Ctrl+C');
        flash(btn, 'press Ctrl+C', 'copy-fail');
        setTimeout(function () {
            if (ta.parentNode) ta.parentNode.removeChild(ta);
        }, 15000);
    }

    function copyText(text, btn) {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            navigator.clipboard.writeText(text).then(function () {
                announce('Copied to clipboard');
                flash(btn, 'copied', 'copy-ok');
            }, function () {
                fallbackCopy(text, btn);
            });
        } else {
            fallbackCopy(text, btn);
        }
    }

    function resolveValue(btn) {
        var text = btn.getAttribute('data-copy');
        if (text === null) {
            var src = btn.getAttribute('data-copy-from');
            var el = src && document.getElementById(src);
            text = el ? el.textContent : '';
        }
        return (text || '').trim();
    }

    document.addEventListener('click', function (ev) {
        var btn = ev.target && ev.target.closest ? ev.target.closest('button.copy-btn') : null;
        if (!btn) return;
        // Copy buttons sit inside clickable rows/links — do not let the
        // click reach the row's own handler.
        ev.stopPropagation();
        var text = resolveValue(btn);
        if (!text || /^(loading\.{3}|-|n\/a)$/i.test(text)) {
            announce('Nothing to copy');
            return;
        }
        copyText(text, btn);
    });

    // Markup builder for JS emitters. `what` names the value so the
    // accessible name contains the visible word ("copy") plus what is
    // copied, e.g. "Copy transaction hash" (WCAG label-in-name).
    window.aitbcCopyBtn = function (value, what) {
        var w = what ? String(what) : 'value';
        return '<button type="button" class="copy-btn" aria-live="polite" data-copy="' +
            esc(value == null ? '' : value) +
            '" aria-label="Copy ' + esc(w) + '" title="Copy ' + esc(w) + '">copy</button>';
    };
    window.aitbcCopy = copyText;
})();
