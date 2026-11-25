# Licensing

AITBC is multi-licensed by directory. Unless a carve-out below applies, the
product core in this repository is licensed under the GNU Affero General
Public License v3.0 (AGPLv3). The complete AGPLv3 text is in [LICENSE](LICENSE).

The product core includes the AITBC applications, CLI, shared Python packages,
MCP server, tests, and product deployment machinery — for example `apps/`,
`cli/`, `packages/py/`, `mcp-server/`, `tests/`, and product scripts.

This licensing change applies forward only. Versions and commit history
published before the 25 November 2026 relicensing ruling were distributed
under the MIT License and remain available under those terms.

## Permissive carve-outs

The following parts of the repository remain licensed under the MIT License:

- `contracts/` — smart-contract source and tests. Deployed contract bytecode
  is public, and permissive licensing preserves composability for contracts
  and integrations.
- `docs/` — documentation, unless a document states otherwise.
- `website/` — public website assets, unless a file states otherwise.

### MIT License text for carve-outs

Copyright (c) 2025–2026 AITBC

Permission is hereby granted, free of charge, to any person obtaining a copy
of the carved-out software, documentation, or website assets and associated
files (the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom
the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Commercial licensing

Commercial licenses for the AGPLv3 product core are available from the rights
holder for users who cannot or do not wish to comply with AGPLv3. Contact:
[aitbc@bubuit.net](mailto:aitbc@bubuit.net).
