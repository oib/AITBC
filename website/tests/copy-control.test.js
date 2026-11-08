/**
 * @jest-environment jsdom
 */

const { loadWebsiteScript } = require('./helpers/loadWebsiteScript');

describe('copy.js markup + escaping', () => {
  beforeAll(() => {
    document.body.innerHTML = '<span id="sr-announcer" class="visually-hidden"></span>';
    loadWebsiteScript('copy.js');
  });

  test('aitbcCopyBtn escapes attribute-breaking characters', () => {
    const evil = '"><img onerror=alert(1) foo=\'bar';
    const html = window.aitbcCopyBtn(evil, 'transaction hash');
    expect(html).toContain('data-copy="');
    expect(html).not.toMatch(/data-copy="[^"]*"><img/);
    expect(html).toContain('&quot;');
    expect(html).toContain('aria-label="Copy transaction hash"');
  });

  test('delegated click copies resolved data-copy value', async () => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.setAttribute('data-copy', '0xabc');
    document.body.appendChild(btn);

    const write = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText: write } });

    btn.click();
    await Promise.resolve();
    await Promise.resolve();
    expect(write).toHaveBeenCalledWith('0xabc');
  });
});
