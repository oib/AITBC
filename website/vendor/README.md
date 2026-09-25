Vendored third-party browser libraries — pinned versions, replaces CDN
script tags (unpkg @latest was floating; jsdelivr leaked visitor IPs).

| file | package | version | upstream | license |
|---|---|---|---|---|
| lucide.min.js | lucide | 1.47.0 | https://unpkg.com/lucide@1.47.0/dist/umd/lucide.min.js | ISC |
| chart.umd.min.js | chart.js | 4.5.1 | https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js | MIT |

Fetched 2026-09-25. Update deliberately: bump the URL version, download,
verify `createIcons`/`Chart` globals are still exposed.
