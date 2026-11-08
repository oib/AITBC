/**
 * @jest-environment jsdom
 */

const { loadWebsiteScript } = require('./helpers/loadWebsiteScript');

describe('dashboard.js readApi', () => {
  beforeAll(() => {
    document.body.innerHTML = '<main></main>';
    loadWebsiteScript('status.js');
    loadWebsiteScript('copy.js');
    loadWebsiteScript('dashboard.js');
  });

  beforeEach(() => {
    global.fetch = jest.fn();
    global.sessionStorage.clear();
  });

  test('returns parsed JSON on success', async () => {
    fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [1] }),
    });
    const out = await window.readApi('/v1/jobs', {});
    expect(out).toEqual({ ok: true, status: 200, data: { items: [1] } });
  });

  test('maps network failure to named error', async () => {
    fetch.mockRejectedValue(new Error('offline'));
    const out = await window.readApi('/v1/status', {});
    expect(out.ok).toBe(false);
    expect(out.status).toBe(0);
    expect(out.err).toBe('network request failed');
  });

  test('auth 401 returns credential rejected message', async () => {
    sessionStorage.setItem('aitbc_credential', 'tok');
    fetch.mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
    const out = await window.readApi('/v1/jobs', { auth: true });
    expect(out.ok).toBe(false);
    expect(out.err).toMatch(/Credential rejected/);
  });
});
