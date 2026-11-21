/**
 * @jest-environment jsdom
 */

const { loadWebsiteScript } = require('./helpers/loadWebsiteScript');

describe('block.js unit formatting (EXPLORER-UNITS-1)', () => {
  beforeAll(() => {
    document.body.innerHTML = '<div id="loading"></div><div id="content"></div>';
    loadWebsiteScript('status.js');
    loadWebsiteScript('copy.js');
    loadWebsiteScript('block.js');
  });

  test('fmtUnits converts compute-units to AIT (1 AIT = 36,000,000 units)', () => {
    // The S57 grant: 3,600,000,000 units must render as 100, not 3.6 billion.
    expect(window.fmtUnits(3600000000)).toBe('100');
    expect(window.fmtUnits(36000000)).toBe('1');
    expect(window.fmtUnits(10)).toBe('0.00000028');
  });

  test('fmtUnits passes through missing values', () => {
    expect(window.fmtUnits(null)).toBe('N/A');
    expect(window.fmtUnits(undefined)).toBe('N/A');
    expect(window.fmtUnits('N/A')).toBe('N/A');
  });
});
