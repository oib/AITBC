'use strict';

const fs = require('fs');
const path = require('path');

const WEBSITE_ROOT = path.resolve(__dirname, '../..');

/** Evaluate a classic browser script the same way nginx serves it: <script> in the page. */
function loadWebsiteScript(relativePath) {
  const full = path.join(WEBSITE_ROOT, relativePath);
  const code = fs.readFileSync(full, 'utf8');
  const script = document.createElement('script');
  script.textContent = code;
  document.head.appendChild(script);
}

module.exports = { loadWebsiteScript, WEBSITE_ROOT };
