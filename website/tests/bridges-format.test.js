/**
 * @jest-environment jsdom
 */

const { loadWebsiteScript } = require('./helpers/loadWebsiteScript');

describe('bridges.js formatting helpers', () => {
  beforeAll(() => {
    document.body.innerHTML = '<span id="sr-announcer"></span>';
    loadWebsiteScript('status.js');
    loadWebsiteScript('copy.js');
    loadWebsiteScript('bridges.js');
  });

  test('statusBadge escapes unknown status text', () => {
    const html = window.statusBadge('<pending>');
    expect(html).toContain('&lt;pending&gt;');
    expect(html).toContain('bridge-status-unknown');
  });

  test('shortAddr truncates long addresses and includes copy control', () => {
    const addr = '0x' + 'a'.repeat(40);
    const html = window.shortAddr(addr);
    expect(html).toContain('bridge-addr-a');
    expect(html).toContain('copy-btn');
    expect(html).toContain('...aaaaaa');
    expect(html).not.toMatch(/bridge-addr-a">0xaaaaaaaaaaaaaaaa/);
  });

  test('fmtAit converts base units using shared num helper', () => {
    expect(window.fmtAit(36000000)).toBe('1');
    expect(window.fmtAit(null)).toBe('-');
  });
});
