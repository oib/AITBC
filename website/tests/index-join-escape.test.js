/**
 * @jest-environment jsdom
 */

const { loadWebsiteScript } = require('./helpers/loadWebsiteScript');

describe('index.js join failure DOM', () => {
  beforeAll(() => {
    document.body.innerHTML =
      '<div id="join-result"></div><button id="join-retry-btn" hidden></button>' +
      '<form id="join-form"><input id="join-node-id" /></form>';
    loadWebsiteScript('status.js');
    loadWebsiteScript('copy.js');
    loadWebsiteScript('index.js');
  });

  test('joinFailed escapes HTML in reason and detail', () => {
    window.joinFailed('<bad>', '<detail&>');
    const html = document.getElementById('join-result').innerHTML;
    expect(html).toContain('&lt;bad&gt;');
    expect(html).toContain('&lt;detail&amp;&gt;');
    expect(document.getElementById('join-retry-btn').hidden).toBe(false);
  });
});
