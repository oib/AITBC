/**
 * @jest-environment jsdom
 */

const { loadWebsiteScript } = require('./helpers/loadWebsiteScript');

describe('status.js aitbcFmt', () => {
  beforeAll(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ height: 1, timestamp: new Date().toISOString() }),
    });
    document.body.innerHTML = '<div class="status-strip"></div>';
    loadWebsiteScript('status.js');
  });

  test('num formats en-US and rejects non-finite', () => {
    expect(window.aitbcFmt.num(1234567.89)).toBe('1,234,567.89');
    expect(window.aitbcFmt.num(1.23456789, 2)).toBe('1.23');
    expect(window.aitbcFmt.num(NaN)).toBe('-');
  });

  test('date returns ISO-style local stamp', () => {
    const s = window.aitbcFmt.date(new Date('2026-03-15T14:05:00'));
    expect(s).toBe('2026-03-15 14:05');
    expect(window.aitbcFmt.date('not-a-date')).toBe('-');
  });

  test('type humanizes snake types with acronyms', () => {
    expect(window.aitbcFmt.type('GPU_MARKET')).toBe('GPU market');
    expect(window.aitbcFmt.type('BRIDGE_LOCK')).toBe('Bridge lock');
    expect(window.aitbcFmt.type('')).toBe('');
  });

  test('zone returns a short label for a valid date', () => {
    const z = window.aitbcFmt.zone(new Date('2026-01-01T12:00:00Z'));
    expect(typeof z).toBe('string');
    expect(z.length).toBeGreaterThan(0);
  });
});
