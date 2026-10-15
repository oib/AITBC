#!/usr/bin/env node
/* WEB-FIX-1 W5 — standalone 375px layout check for the in-app browser.
 *
 * What it is: a dependency-free measurement snippet. Paste it into the
 * devtools console of any AITBC website page with the device toolbar set to
 * a 375px-wide viewport, or serve a page and run it there. It prints:
 *
 *   - documentElement.scrollWidth vs innerWidth  (the W1/W2 assertion:
 *     scrollWidth must be <= innerWidth, i.e. no horizontal page scroll)
 *   - every element whose box or scrollable overflow crosses the viewport
 *     right edge (the offenders, with class/id for inspection)
 *   - counts of interactive elements under 44px in the W3 classes and form
 *     controls under 16px (W4)
 *
 * What it is NOT: it does not stub API calls — run it against a page that
 * has already rendered its live data (or against a test page populated via
 * tests/unit/test_website_layout_375.py's fixtures).
 *
 * Exit: returns true when scrollWidth <= innerWidth and no W3/W4 element is
 * undersized; also sets document.title to PASS/FAIL for scripted callers.
 */
(function () {
  "use strict";
  var vw = window.innerWidth;
  var docSW = document.documentElement.scrollWidth;
  var bodySW = document.body ? document.body.scrollWidth : 0;
  var lines = [
    "scrollWidth=" + docSW + " innerWidth=" + vw + " bodySW=" + bodySW +
      (docSW <= vw ? "  OK" : "  OVERFLOW"),
  ];
  var seen = {};
  var offenders = 0;
  Array.prototype.forEach.call(document.querySelectorAll("*"), function (el) {
    if (!el.getBoundingClientRect) return;
    var r = el.getBoundingClientRect();
    // A scroll container's own scrollWidth is internal scroll content, not
    // page overflow — only flag it if its box itself crosses the viewport.
    if (r.right > vw + 1) {
      var key = el.tagName + "." + Array.prototype.join.call(el.classList, ".") + "#" + (el.id || "") + Math.round(r.right);
      if (seen[key]) return;
      seen[key] = 1;
      offenders++;
      var inScroller = el.closest(".table-wrap") ? " (inside .table-wrap scroll region)" : "";
      lines.push("OFFENDER " + el.tagName + "." + Array.prototype.join.call(el.classList, ".") +
        (el.id ? "#" + el.id : "") + " w=" + Math.round(r.width) + " right=" + Math.round(r.right) + inScroller);
    }
  });
  var groups = {
    "status-strip a.status-part": ".status-strip a.status-part",
    "site-footer a": ".site-footer a",
    "filter-btn": ".filter-btn",
    "block-item": ".block-item",
    "journal-controls select": ".journal-controls select",
    "table td a": ".block-list-table td a, .alerts-table td a, .top-addresses-table td a",
  };
  var undersized = 0;
  Object.keys(groups).forEach(function (name) {
    var els = document.querySelectorAll(groups[name]);
    if (!els.length) return;
    var small = Array.prototype.filter.call(els, function (e) {
      return e.getBoundingClientRect().height < 44;
    });
    undersized += small.length;
    lines.push(name + ": " + els.length + " els, " + small.length + " <44px");
  });
  var controls = document.querySelectorAll('input:not([type="checkbox"]):not([type="radio"]), select, textarea');
  var smallFont = Array.prototype.filter.call(controls, function (e) {
    return parseFloat(getComputedStyle(e).fontSize) < 16;
  });
  if (controls.length) lines.push("form controls: " + controls.length + " els, " + smallFont.length + " <16px");
  var pass = docSW <= vw && undersized === 0 && smallFont.length === 0;
  lines.push(pass ? "PASS" : "FAIL");
  document.title = (pass ? "PASS" : "FAIL") + " 375px " + document.title;
  var text = lines.join("\n");
  if (typeof console !== "undefined") console.log(text);
  return pass;
})();
