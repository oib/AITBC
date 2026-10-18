"""WEB-4: website → nginx → app contract test.

Every API path a website script calls must (a) be exposed by a location
in the hub reference nginx config and (b) resolve to a route the serving
app in this repo implements.

Source of truth for nginx is ``examples/nginx/nginx-aitbc.conf.example``
(the sanitized copy of the hub vhost — its header states every location
exists in production). Override with ``AITBC_NGINX_CONF`` to point the
test at a copy of the live config for a drift check:

    AITBC_NGINX_CONF=/tmp/nginx-T.out pytest tests/unit/test_website_api_contract.py

Caveat: the reference file can drift from the deployed config; this test
proves the contract against the reference, not the live hub.

Paths landing on upstreams that cannot be inspected statically (external
127.0.0.1 services, unmapped upstreams) are ``unchecked-app`` and FAIL
unless covered by an explicit entry in ``website_api_contract_allowlist.txt``
(one ``path-prefix<TAB>method-or-*<TAB>upstream-or-*<TAB>reason`` per line).
Allowlist entries matching no extracted call are stale and also fail.

No network, no browser. ``python tests/unit/test_website_api_contract.py``
prints the full extracted-path table for reports.
"""

from __future__ import annotations

import os
import re
import unittest
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEBSITE = REPO / "website"
NGINX_CONF = Path(os.environ.get("AITBC_NGINX_CONF", REPO / "examples/nginx/nginx-aitbc.conf.example"))
ALLOWLIST = Path(__file__).with_name("website_api_contract_allowlist.txt")

HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")

# ---------------------------------------------------------------------------
# JS extraction
# ---------------------------------------------------------------------------


@dataclass
class Call:
    pattern: str  # normalized path pattern ('*' = one wildcard segment)
    method: str
    file: str
    line: int

    def key(self) -> str:
        return f"{self.pattern} [{self.method}]"


_CONST_RE = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*([^;]+);")
_STRING_RE = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`([^`]*)`")
_PROP_RE = re.compile(r"\b(?:url|uri|endpoint)\s*:\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`)")
_CALL_RE = re.compile(
    r"\b(fetch|apiGet|apiPost|apiPostOrGet|fetchJson|getJSON|apiFetch|requestJSON)\s*\("
    r"|\bnew\s+(EventSource|WebSocket)\s*\("
    r"|\.open\(\s*'([A-Z]+)'"
)
_METHOD_RE = re.compile(r"\bmethod\s*:\s*'([A-Z]+)'")
_IDENT_ARG_RE = re.compile(r"^\s*([A-Za-z_$][\w$.]*)")
_MEMBER_PROP_NAMES = {"url", "uri", "endpoint", "path"}


def _literal_strings(expr: str) -> list[str]:
    """All string/template literal bodies inside a JS expression."""
    return [next(g for g in m.groups() if g is not None) for m in _STRING_RE.finditer(expr)]


def _collect_consts(src: str) -> dict[str, list[str]]:
    """name -> literal bodies in its initializer (ternary = several).

    Initializers that reference config properties (`x.y.explorerApiUrl`)
    resolve through _GLOBAL_CONSTS parsed from config.js.
    """
    consts: dict[str, list[str]] = {}
    for name, expr in _CONST_RE.findall(src):
        lits = _literal_strings(expr)
        if lits:
            consts[name] = lits
            continue
        for member in re.findall(r"\.(\w+)", expr):
            if member in _GLOBAL_CONSTS:
                consts[name] = _GLOBAL_CONSTS[member]
                break
    return consts


def _global_consts() -> dict[str, list[str]]:
    """window.AITBC_CONFIG properties in website/config.js."""
    cfg = WEBSITE / "config.js"
    if not cfg.is_file():
        return {}
    return {name: [v] for name, v in re.findall(r"(\w+)\s*:\s*'([^']+)'", cfg.read_text(encoding="utf-8"))}


_GLOBAL_CONSTS: dict[str, list[str]] = _global_consts()


def _collect_obj_props(src: str) -> list[str]:
    """Literal values of url/uri/endpoint properties in object literals."""
    props: list[str] = []
    for m in _PROP_RE.finditer(src):
        body = _literal_strings(m.group(1))
        props.extend(body or [m.group(1).strip("'\"")])
    return props


def _resolve_template(body: str, consts: dict[str, list[str]]) -> list[str]:
    """Resolve a template/string body to candidate path prefixes."""
    out = [""]
    for part in re.split(r"(\$\{[^}]*\})", body):
        if not (part.startswith("${") and part.endswith("}")):
            out = [o + part for o in out]
            continue
        expr = part[2:-1].strip()
        name = expr.split(".")[-1].strip() if re.fullmatch(r"[\w$.]+", expr) else None
        vals = consts.get(name or "", []) or _GLOBAL_CONSTS.get(name or "", [])
        vals = [v for v in vals if "/" in v]  # only path-like constants
        if vals:
            out = [o + v for o in out for v in vals]
        else:
            out = [o + "*" for o in out]
    return out


def _first_arg(src: str, pos: int) -> str:
    """The first argument expression after `callee(` — balanced to `,` or `)`
    at depth 0 so `)` inside encodeURIComponent() etc. does not truncate."""
    depth = 0
    for i in range(pos, min(pos + 400, len(src))):
        ch = src[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return src[pos:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return src[pos:i]
        elif ch in "'\"`" and depth == 0 and i > pos and src[pos:i].strip() == "":
            # literal begins — read to its matching close quote
            j = i + 1
            while j < len(src) and src[j] != ch:
                j += 2 if src[j] == "\\" else 1
            return src[i : j + 1]
    return src[pos : pos + 400]


def _resolve_arg(arg: str, consts: dict[str, list[str]], obj_props: list[str]) -> list[str]:
    """Resolve a call's first argument to candidate path literals."""
    arg = arg.strip()
    if arg[:1] in ("'", '"', "`"):
        bodies = _literal_strings(arg)
        body = bodies[0] if bodies else arg[1:-1]
        return _resolve_template(body, consts)
    m = _IDENT_ARG_RE.match(arg)
    if not m:
        return []
    base = m.group(1).split(".")[-1]
    if base in _MEMBER_PROP_NAMES:
        resolved: list[str] = []
        for p in obj_props:
            resolved.extend(_resolve_template(p, consts))
        return resolved
    out: list[str] = []
    for lit in consts.get(base, []) or _GLOBAL_CONSTS.get(base, []):
        out.extend(_resolve_template(lit, consts))
    return out


def _call_method(callable_name: str, window: str) -> str:
    """apiPostOrGet tries POST and falls back to GET — both recorded."""
    if callable_name == "apiPost":
        return "POST"
    if callable_name == "apiPostOrGet":
        return "POST|GET"
    m = _METHOD_RE.search(window[:300])
    return m.group(1) if m else "GET"


def _norm_path(raw: str) -> str:
    path = raw.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"\*+", "*", path)
    return re.sub(r"/{2,}", "/", path)


def extract_calls_from(src: str, filename: str) -> list[Call]:
    """Find request-call sites and resolve their first-arg literals."""
    consts = _collect_consts(src)
    obj_props = _collect_obj_props(src)
    calls: list[Call] = []
    for m in _CALL_RE.finditer(src):
        callee = m.group(1) or m.group(2) or "open"
        method = m.group(3) or _call_method(callee, src[m.end() : m.end() + 300])
        for raw in _resolve_arg(_first_arg(src, m.end()), consts, obj_props):
            path = _norm_path(raw)
            if path != "/" and ("/" in path):
                line = src.count("\n", 0, m.start()) + 1
                calls.append(Call(path, method, f"{filename}:{line}", line))
    return calls


def _inline_scripts(html: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)]


def extract_all_calls() -> list[Call]:
    calls: list[Call] = []
    for js in sorted(WEBSITE.glob("*.js")):
        calls.extend(extract_calls_from(js.read_text(encoding="utf-8"), js.name))
    for html in sorted(WEBSITE.glob("*.html")):
        text = html.read_text(encoding="utf-8")
        for body in _inline_scripts(text):
            calls.extend(extract_calls_from(body, html.name))
    return calls


def dedupe(calls: list[Call]) -> dict[str, list[Call]]:
    grouped: dict[str, list[Call]] = defaultdict(list)
    for c in calls:
        grouped[c.key()].append(c)
    return dict(grouped)


# ---------------------------------------------------------------------------
# Nginx reference config
# ---------------------------------------------------------------------------


@dataclass
class Location:
    modifier: str  # '=', '~', '~*', '^~', or '' (prefix)
    pattern: str
    body: str
    order: int
    proxy_upstream: str | None = None  # e.g. 'coordinator_api' or '127.0.0.1:8101'
    proxy_uri: str | None = None  # URI part of proxy_pass, may contain $N
    denied: bool = False
    return_code: int | None = None
    allowed_methods: set[str] = field(default_factory=set)  # empty = all
    static_root: str | None = None  # alias/root target
    is_prefix: bool = False


_LOC_RE = re.compile(r"\blocation\s+(=|~\*?|\^~)?\s*(?:\"([^\"]+)\"|(\S+))\s*\{")
_PROXY_RE = re.compile(r"proxy_pass\s+https?://([^/;\s]+)(/[^;]*)?;")
_LIMIT_RE = re.compile(r"limit_except\s+([A-Z ]+?)\s*\{")
_RETURN_RE = re.compile(r"\breturn\s+(\d{3})")


def _brace_block(text: str, start: int) -> str:
    """Return the {...} block body starting at index of '{'-1 (start points at '{')."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return text[start + 1 :]


def _strip_comments(text: str) -> str:
    return re.sub(r"#[^\n]*", "", text)


def parse_nginx(text: str) -> tuple[list[Location], str | None]:
    """Parse location blocks; returns (locations, server-level root)."""
    text = _strip_comments(text)
    server_root = None
    for rm in re.finditer(r"\broot\s+([^;]+);", text):
        server_root = rm.group(1).strip()
    locs: list[Location] = []
    for i, m in enumerate(_LOC_RE.finditer(text)):
        body = _brace_block(text, m.end() - 1)
        pattern = m.group(2) or m.group(3) or ""
        loc = Location(
            modifier=m.group(1) or "",
            pattern=pattern,
            body=body,
            order=i,
            is_prefix=(m.group(1) or "") in ("", "^~"),
        )
        pm = _PROXY_RE.search(body)
        if pm:
            loc.proxy_upstream = pm.group(1)
            # None = no URI (path passed unchanged); "" = URI "/" (strip to root)
            uri = pm.group(2)
            loc.proxy_uri = uri.rstrip("/") if uri is not None else None
        if "deny all" in body and not _LIMIT_RE.search(body):
            loc.denied = True
        rm = _RETURN_RE.search(body)
        if rm:
            loc.return_code = int(rm.group(1))
        for lm in _LIMIT_RE.finditer(body):
            loc.allowed_methods.update(lm.group(1).split())
        am = re.search(r"\b(?:alias|root)\s+([^;]+);", body)
        if am:
            loc.static_root = am.group(1).strip()
        locs.append(loc)
    return locs, server_root


def _server_level_text(text: str) -> str:
    """nginx text with every location block removed (server-level directives only)."""
    text = _strip_comments(text)
    spans = []
    for m in _LOC_RE.finditer(text):
        body = _brace_block(text, m.end() - 1)
        spans.append((m.start(), m.end() + len(body) + 1))
    for a, b in sorted(spans, reverse=True):
        text = text[:a] + text[b:]
    return text


# Server-level security headers deployed on the hub (15 Oct 2026,
# card-attested operator decision; CSP flipped to enforcing 18 Oct 2026
# after WEB-CSP-2 externalized all inline scripts/handlers — verified by
# browser click-through under enforcement). They apply to the static pages
# through `location /`, which defines no add_header of its own. Mirrored
# verbatim — a config sync that drops them fails the guard test.
EXPECTED_SERVER_HEADERS = [
    'Referrer-Policy "strict-origin-when-cross-origin" always',
    "Content-Security-Policy \"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'\" always",
    'Permissions-Policy "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=(), interest-cohort=()" always',
    'Strict-Transport-Security "max-age=31536000; includeSubDomains" always',
]

# Locations serving the HTML pages that must NOT define their own
# add_header — nginx add_header is not inherited, so a location-level
# directive would silently drop the whole server-level security set.
STATIC_LOCATIONS_NO_ADD_HEADER = ("/",)

# Static-page locations that carry their own add_header (Cache-Control for
# the dashboards). nginx add_header inheritance is all-or-nothing, so each
# must repeat the full security set verbatim — deployed on hub 15 Oct after
# WEB-FIX-3 documented the gap; pinned here so config drift on either side
# fails loudly.
SELF_HEADERED_STATIC_LOCATIONS = ("/dashboard/", "/shop/")


def nginx_match(path: str, locs: list[Location]) -> Location | None:
    """nginx matching: exact > longest ^~ > first regex > longest prefix."""
    for loc in locs:
        if loc.modifier == "=" and loc.pattern == path:
            return loc
    best: Location | None = None
    for loc in locs:
        if loc.is_prefix and path.startswith(loc.pattern):
            if best is None or len(loc.pattern) > len(best.pattern):
                best = loc
    if best is not None and best.modifier == "^~":
        return best
    for loc in locs:
        if loc.modifier in ("~", "~*"):
            flags = re.I if loc.modifier == "~*" else 0
            if re.search(loc.pattern, path, flags):
                return loc
    return best


def upstream_path(loc: Location, path: str) -> str:
    """Apply proxy_pass URI rewriting to produce the path the app sees."""
    if loc.proxy_uri is None:
        return path
    uri = loc.proxy_uri
    if "$" in uri:
        if loc.modifier in ("~", "~*"):
            flags = re.I if loc.modifier == "~*" else 0
            m = re.search(loc.pattern, path, flags)
            if m:
                for n, g in enumerate(m.groups(), 1):
                    uri = uri.replace(f"${n}", g or "")
        if "$" in uri:
            return uri  # unresolved variable — caller treats as opaque
    if loc.modifier == "=":
        return uri
    rest = path[len(loc.pattern) :] if loc.is_prefix else path
    return (uri + "/" + rest.lstrip("/")) if rest else (uri or "/")


# ---------------------------------------------------------------------------
# App route discovery
# ---------------------------------------------------------------------------

# upstream name -> (repo-relative app dir, router scan style)
UPSTREAM_APP: dict[str, tuple[str, str]] = {
    "coordinator_api": ("apps/coordinator-api", "fastapi"),
    "blockchain_explorer": ("apps/blockchain-explorer", "fastapi"),
    "blockchain_rpc": ("apps/blockchain-node", "fastapi"),
    "wallet_service": ("apps/wallet", "fastapi"),
    "exchange_service": ("apps/exchange", "exchange"),
    "marketplace_service": ("apps/market", "fastapi"),
    "pool_hub": ("apps/pool-hub", "fastapi"),
    "agent_coordinator": ("apps/agent-coordinator", "fastapi"),
    "api_gateway": ("apps/api-gateway", "fastapi"),
}

_ROUTER_DEF_RE = re.compile(r"(\w+)\s*=\s*APIRouter\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]")
_DECORATOR_RE = re.compile(r"@(\w+)\.(get|post|put|delete|patch|api_route)\(\s*['\"]([^'\"]+)['\"]", re.I)
_INCLUDE_RE = re.compile(r"include_router\(\s*([\w.]+)(?:\s*,\s*prefix\s*=\s*['\"]([^'\"]+)['\"])?")
_IMPORT_RE = re.compile(r"from\s+([\w.]+)\s+import\s+\(?\s*([^)\n]+)")
_METHODS_RE = re.compile(r"methods\s*=\s*\[([^\]]+)\]")


def _py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*.py") if "tests" not in p.parts and "test_" not in p.name]


def _module_files(root: Path) -> dict[str, Path]:
    """basename (no ext) -> file, for resolving include_router arguments."""
    return {p.stem: p for p in _py_files(root)}


def _file_routes(text: str) -> dict[str, list[tuple[str, str]]]:
    """receiver name -> [(method, decorated-path)] for one file.

    api_route decorators are handled in the second sweep of
    fastapi_routes (method list needs the decorator tail context).
    """
    local_prefix = dict(_ROUTER_DEF_RE.findall(text))
    routes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for recv, meth, path in _DECORATOR_RE.findall(text):
        if meth.lower() == "api_route":
            continue
        routes[recv].append((meth.upper(), local_prefix.get(recv, "") + path))
    return routes


def _api_route_methods(text: str, start: int) -> list[str]:
    mm = _METHODS_RE.search(text, start, start + 300)
    if not mm:
        return ["GET"]
    return [m.strip().strip("'\"").upper() for m in mm.group(1).split(",")]


def _imported_modules(text: str) -> dict[str, str]:
    """imported name -> last module path component (for include resolution)."""
    out: dict[str, str] = {}
    for mod, names in _IMPORT_RE.findall(text):
        leaf = mod.split(".")[-1]
        for n in names.split(","):
            n = n.strip().split(" as ")[0].strip()
            if n:
                out[n] = leaf if n != leaf else leaf
                out.setdefault(n, leaf)
    return out


def _include_prefixes(texts: dict[Path, str], stems: dict[str, Path]) -> tuple[dict[str, set[str]], set[str]]:
    """module-stem -> include prefixes, plus prefixes bound to no module."""
    obj_prefix: dict[str, set[str]] = defaultdict(set)
    unbound: set[str] = set()
    for text in texts.values():
        for obj, prefix in _INCLUDE_RE.findall(text):
            stem = obj.split(".")[0] if "." in obj else obj
            resolved = stems.get(stem) or stems.get(obj.split(".")[-1])
            if resolved:
                obj_prefix[resolved.stem].add(prefix or "")
            elif prefix:
                unbound.add(prefix)
    return obj_prefix, unbound


def _add_routes(
    routes: dict[str, set[str]],
    path: str,
    methods: list[str],
    prefixes: set[str],
) -> None:
    for meth in methods:
        for pre in prefixes:
            routes[meth].add(_norm_route(pre + path))


def fastapi_routes(root: Path) -> dict[str, set[str]]:
    """method -> set of full path patterns for a FastAPI app directory.

    include_router prefixes bind to the module file they import from;
    prefixes that cannot be bound to a module are applied app-wide
    (over-approximation: notes in the table footer).
    """
    files = _py_files(root)
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    obj_prefix, unbound = _include_prefixes(texts, _module_files(root))
    routes: dict[str, set[str]] = defaultdict(set)
    for p, text in texts.items():
        prefixes = obj_prefix.get(p.stem, {""}) | (unbound or {""})
        local_prefix = dict(_ROUTER_DEF_RE.findall(text))
        for _recv, rs in _file_routes(text).items():
            for meth, local in rs:
                _add_routes(routes, local, [meth], prefixes)
        for m in re.finditer(r"@(\w+)\.api_route\(\s*['\"]([^'\"]+)['\"]", text):
            path = local_prefix.get(m.group(1), "") + m.group(2)
            _add_routes(routes, path, _api_route_methods(text, m.end()), prefixes)
    return routes


def _norm_route(path: str) -> str:
    path = re.sub(r"\{[^}]*\}", "*", path)
    return re.sub(r"/{2,}", "/", path)


def _route_block(text: str, name: str) -> str:
    """Body of `def name(...)` up to the next top-level def."""
    m = re.search(rf"\bdef {name}\b[^\n]*\n", text)
    if not m:
        return ""
    rest = text[m.end() :]
    nxt = re.search(r"\n    def |\n    @|\Z", rest)
    return rest[: nxt.start() if nxt else len(rest)]


def _constraints_to_patterns(body: str) -> list[str]:
    """Turn path ==/in/startswith(+endswith) checks into route patterns."""
    pats: list[str] = []
    for m in re.finditer(r'path\s*==\s*["\']([^"\']+)["\']', body):
        pats.append(m.group(1))
    for m in re.finditer(r"path\s+in\s*\(([^)]+)\)", body):
        pats.extend(re.findall(r'["\']([^"\']+)["\']', m.group(1)))
    for m in re.finditer(
        r'path\.startswith\(["\']([^"\']+)["\']\)'
        r"[^)\n]*?(?:and\s+path\.endswith\(['\"]([^'\"]+)['\"]\))?",
        body,
    ):
        pre, suf = m.group(1), m.group(2)
        pats.append(pre + "*" + suf if suf else pre + "*")
    return pats


def exchange_routes() -> dict[str, set[str]]:
    """Hand-dispatched routes of ExchangeAPIHandler (apps/exchange)."""
    init = (REPO / "apps/exchange/simple_exchange/handlers/__init__.py").read_text()
    helpers = {name: _route_block(init, name) for name in re.findall(r"def (_(?:get|post)_[\w]+)\(", init)}
    routes: dict[str, set[str]] = defaultdict(set)
    for method, fname in (("GET", "do_GET"), ("POST", "do_POST"), ("DELETE", "do_DELETE")):
        body = _route_block(init, fname)
        blocks = [body]
        blocks.extend(helpers[h] for h in helpers if f"self.{h}(" in body)
        for b in blocks:
            for pat in _constraints_to_patterns(b):
                routes[method].add(_norm_route(pat))
    return routes


_APP_ROUTES_CACHE: dict[str, dict[str, set[str]]] = {}


def app_routes(upstream: str) -> dict[str, set[str]] | None:
    if upstream not in UPSTREAM_APP:
        return None
    if upstream not in _APP_ROUTES_CACHE:
        rel, style = UPSTREAM_APP[upstream]
        if style == "exchange":
            _APP_ROUTES_CACHE[upstream] = exchange_routes()
        else:
            _APP_ROUTES_CACHE[upstream] = fastapi_routes(REPO / rel)
    return _APP_ROUTES_CACHE[upstream]


def _methods(call_method: str) -> set[str]:
    return set(call_method.split("|"))


def app_has_route(upstream: str, method: str, pattern: str) -> bool:
    routes = app_routes(upstream)
    if routes is None:
        return False
    known: set[str] = set()
    for m in _methods(method):
        known |= routes.get(m, set())
    if "HEAD" in _methods(method):
        known |= routes.get("GET", set())
    return any(_glob_match(r, pattern) for r in known)


def _seg_re(seg: str) -> str:
    """'*' inside a segment = any chars (incl. none), never '/'."""
    return re.escape(seg).replace(r"\*", "[^/]*")


def _glob_match(route_pattern: str, path_pattern: str) -> bool:
    """Route accepts the call pattern: per-segment wildcard regex match.
    A trailing '*' route segment also accepts deeper call paths."""
    rp = route_pattern.rstrip("/").split("/")
    pp = path_pattern.rstrip("/").split("/")
    if len(rp) != len(pp):
        if rp and rp[-1] == "*" and len(pp) >= len(rp):
            pp = pp[: len(rp)]
        else:
            return False
    return all(re.fullmatch(_seg_re(r), p) or p == "*" for r, p in zip(rp, pp, strict=True))


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


@dataclass
class AllowEntry:
    pattern: str
    method: str
    upstream: str
    reason: str


def load_allowlist() -> list[AllowEntry]:
    entries: list[AllowEntry] = []
    if not ALLOWLIST.is_file():
        return entries
    for line in ALLOWLIST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        while len(parts) < 4:
            parts.append("*" if len(parts) < 3 else "no reason given")
        entries.append(AllowEntry(parts[0], parts[1].upper(), parts[2], parts[3]))
    return entries


def _allowlisted(call: Call, upstream: str | None, entries: list[AllowEntry]) -> AllowEntry | None:
    for e in entries:
        if call.pattern.startswith(e.pattern.rstrip("*")) and (e.method == "*" or e.method in _methods(call.method)):
            if e.upstream in ("*", upstream or ""):
                return e
    return None


# ---------------------------------------------------------------------------
# Analysis core (shared by tests and the __main__ table dump)
# ---------------------------------------------------------------------------


@dataclass
class Row:
    call: Call
    location: Location | None
    upstream: str | None
    app_path: str | None
    verdict: str  # ok | static | not-exposed | denied | not-implemented | unchecked-app | allowlisted
    detail: str = ""


def analyze() -> list[Row]:
    locs, _root = parse_nginx(NGINX_CONF.read_text(encoding="utf-8"))
    allow = load_allowlist()
    rows: list[Row] = []
    for c in sorted(dedupe(extract_all_calls()).values(), key=lambda g: g[0].pattern):
        call = c[0]
        call.file = ", ".join(sorted({x.file for x in c}))
        loc = nginx_match(call.pattern, locs)
        row = Row(call, loc, None, None, "")
        if loc is None:
            row.verdict = "not-exposed"
        elif loc.denied or (loc.return_code and loc.return_code >= 400):
            row.verdict = "denied"
        elif loc.return_code and loc.return_code < 400:
            row.verdict, row.detail = "denied", f"returns {loc.return_code}"
        elif loc.static_root or (loc.is_prefix and loc.pattern == "/" and not loc.proxy_upstream):
            row.verdict, row.app_path, row.detail = _static_check(call.pattern)
        elif loc.proxy_upstream:
            _proxy_row(row, call, loc, allow)
        else:
            row.verdict, row.detail = "unchecked-app", "location has no proxy_pass"
        rows.append(row)
    return rows


def _static_check(pattern: str) -> tuple[str, str, str]:
    rel = pattern.lstrip("/")
    if "*" in rel:
        return "ok", rel, "static wildcard — assumed served"
    return ("ok", rel, "static file") if (WEBSITE / rel).is_file() else ("not-exposed", rel, "no file under website/")


def _proxy_row(row: Row, call: Call, loc: Location, allow: list[AllowEntry]) -> None:
    row.upstream = loc.proxy_upstream
    if loc.allowed_methods and not (_methods(call.method) - {"OPTIONS"}) & loc.allowed_methods:
        row.verdict, row.detail = "not-implemented", f"limit_except allows {sorted(loc.allowed_methods)}"
        return
    row.app_path = upstream_path(loc, call.pattern)
    if loc.proxy_upstream not in UPSTREAM_APP:
        entry = _allowlisted(call, loc.proxy_upstream, allow)
        row.verdict = "allowlisted" if entry else "unchecked-app"
        row.detail = entry.reason if entry else "upstream not inspectable"
        return
    if app_has_route(loc.proxy_upstream, call.method, row.app_path):
        row.verdict = "ok"
    else:
        entry = _allowlisted(call, loc.proxy_upstream, allow)
        if entry:
            row.verdict, row.detail = "allowlisted", entry.reason
        else:
            row.verdict, row.detail = "not-implemented", f"no {call.method} route for {row.app_path}"


def _fmt(rows: list[Row]) -> str:
    lines = [f"{'PATH PATTERN':52} {'METHOD':6} {'VERDICT':16} {'UPSTREAM':22} APP-PATH -> DETAIL"]
    for r in rows:
        lines.append(
            f"{r.call.pattern:52} {r.call.method:6} {r.verdict:16} {r.upstream or '-':22} "
            f"{r.app_path or '-'} -> {r.detail or r.call.file}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWebsiteApiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = analyze()
        cls.allow = load_allowlist()

    def _dump(self, rows: list[Row]) -> str:
        return "\n" + _fmt(rows)

    def test_extractor_found_paths(self) -> None:
        pats = {r.call.pattern for r in self.rows}
        self.assertIn("/explorer-api/api/chain/head", pats)
        self.assertIn("/rpc/network-info", pats)
        self.assertGreater(len(self.rows), 15, "suspiciously few paths — extractor broken?")

    def test_every_path_exposed_by_nginx(self) -> None:
        bad = [r for r in self.rows if r.verdict in ("not-exposed", "denied")]
        self.assertEqual([], bad, f"website calls paths nginx does not serve:{self._dump(bad)}")

    def test_methods_allowed_by_nginx(self) -> None:
        bad = [
            r
            for r in self.rows
            if r.location
            and r.location.allowed_methods
            and not (_methods(r.call.method) - {"OPTIONS"}) & r.location.allowed_methods
        ]
        self.assertEqual([], bad, f"method blocked by limit_except:{self._dump(bad)}")

    def test_paths_implemented_by_apps(self) -> None:
        bad = [r for r in self.rows if r.verdict == "not-implemented"]
        self.assertEqual([], bad, f"proxied but no app route:{self._dump(bad)}")

    def test_no_unchecked_app_without_allowlist(self) -> None:
        bad = [r for r in self.rows if r.verdict == "unchecked-app"]
        self.assertEqual([], bad, f"upstream not statically inspectable, needs allowlist:{self._dump(bad)}")

    def test_no_query_delimiter_missing_in_path(self) -> None:
        # "&" inside a path segment means a template glued a query param to
        # the path (missing "?") — the param silently becomes part of the
        # route argument instead of a query string.
        bad = [r for r in self.rows if "&" in r.call.pattern]
        self.assertEqual([], bad, f"query glued into path (missing '?'):{self._dump(bad)}")

    def test_allowlist_entries_used_and_match_upstream(self) -> None:
        stale = []
        for e in self.allow:
            matched = [
                r
                for r in self.rows
                if r.call.pattern.startswith(e.pattern.rstrip("*"))
                and (e.method == "*" or e.method in _methods(r.call.method))
            ]
            if not matched:
                stale.append(f"{e.pattern}\t{e.method}\t{e.upstream}\t# matches no extracted call")
                continue
            if e.upstream != "*" and all(r.upstream not in (None, e.upstream) for r in matched):
                stale.append(f"{e.pattern}\t{e.method}\t{e.upstream}\t# upstream no longer matches")
        self.assertEqual([], stale, "stale allowlist entries:\n" + "\n".join(stale))


class TestNginxSecurityHeaders(unittest.TestCase):
    """WEB-FIX-3: the deployed server-level security headers must survive a
    config sync, and static-page locations must not shadow them."""

    @classmethod
    def setUpClass(cls) -> None:
        text = NGINX_CONF.read_text(encoding="utf-8")
        cls.server_text = _server_level_text(text)
        cls.locs, _ = parse_nginx(text)

    def test_server_level_headers_present_verbatim(self) -> None:
        missing = [h for h in EXPECTED_SERVER_HEADERS if f"add_header {h};" not in self.server_text]
        self.assertEqual(
            [],
            missing,
            "server-level security headers missing or reworded in "
            f"{NGINX_CONF.name} — drift from the deployed hub config:\n" + "\n".join(missing),
        )

    def test_weak_referrer_policy_removed(self) -> None:
        self.assertNotIn("no-referrer-when-downgrade", self.server_text)

    def test_static_locations_do_not_shadow(self) -> None:
        bad = []
        for pattern in STATIC_LOCATIONS_NO_ADD_HEADER:
            loc = next((lc for lc in self.locs if lc.modifier == "" and lc.pattern == pattern), None)
            self.assertIsNotNone(loc, f"expected static location not found: {pattern!r}")
            if loc and re.search(r"\badd_header\b", loc.body):
                bad.append(pattern)
        self.assertEqual(
            [],
            bad,
            "static-page location defines its own add_header — nginx drops all server-level headers for it: " + ", ".join(bad),
        )

    def test_self_headered_locations_carry_full_set(self) -> None:
        """add_header is not inherited — a location with its own add_header
        must repeat every security header verbatim or silently drop the rest.
        /dashboard/ and /shop/ were fixed on hub 15 Oct (WEB-FIX-3 follow-up);
        the fixture is the tripwire for drift or a new partial set."""
        full_set = EXPECTED_SERVER_HEADERS + [
            'X-Frame-Options "SAMEORIGIN" always',
            'X-Content-Type-Options "nosniff" always',
        ]
        bad = []
        for pattern in SELF_HEADERED_STATIC_LOCATIONS:
            loc = next((lc for lc in self.locs if lc.modifier == "=" and lc.pattern == pattern), None)
            self.assertIsNotNone(loc, f"expected self-headered location not found: {pattern!r}")
            if loc:
                for h in full_set:
                    if f"add_header {h};" not in loc.body:
                        bad.append(f"{pattern} missing `add_header {h}`")
        self.assertEqual([], bad, "self-headered location missing headers:\n" + "\n".join(bad))


class TestMessagingRateLimit(unittest.TestCase):
    """NGINX-MSG-1: the hub's messaging_rpc zone (applied 16 Oct 2026 as
    /etc/nginx/conf.d/aitbc-messaging-limits.conf) is mirrored here so a
    config sync that drops the limit fails loudly — same drift class as
    WEB-FIX-3's shadowed-headers regression."""

    # The five live locations drawing on the shared messaging_rpc bucket.
    MESSAGING_LOCATIONS = (
        "/rpc/messaging/",
        "/rpc/contracts/messaging/",
        "/explorer-api/api/messages",
        "/explorer-api/api/messages/topics",
        "/explorer-api/api/messages/state",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = NGINX_CONF.read_text(encoding="utf-8")
        cls.locs, _ = parse_nginx(cls.raw)

    def test_messaging_zone_is_declared(self) -> None:
        # The zone line is commented in the example (it ships as a conf.d
        # file on the deploy) — match the raw text, not the parsed model.
        self.assertRegex(
            self.raw,
            r"limit_req_zone\s+\$binary_remote_addr\s+zone=messaging_rpc:10m\s+rate=5r/s",
            "messaging_rpc limit_req_zone declaration missing or changed",
        )

    def test_every_messaging_location_is_limited(self) -> None:
        bad = []
        for pattern in self.MESSAGING_LOCATIONS:
            loc = next(
                (lc for lc in self.locs if lc.pattern == pattern),
                None,
            )
            if loc is None:
                bad.append(f"{pattern}: location missing")
                continue
            if "limit_req zone=messaging_rpc burst=20 nodelay;" not in loc.body:
                bad.append(f"{pattern}: missing `limit_req zone=messaging_rpc burst=20 nodelay`")
            if "limit_req_status 429;" not in loc.body:
                bad.append(f"{pattern}: missing `limit_req_status 429`")
        self.assertEqual([], bad, "messaging location without the shared rate limit:\n" + "\n".join(bad))

    def test_no_messaging_location_without_limit(self) -> None:
        # Any *new* location whose pattern serves a messaging path must also
        # be limited — guards against adding a variant that bypasses the zone.
        bad = [lc.pattern for lc in self.locs if "messaging" in lc.pattern and "limit_req zone=messaging_rpc" not in lc.body]
        self.assertEqual([], bad, "messaging location bypasses messaging_rpc zone:\n" + "\n".join(bad))


if __name__ == "__main__":
    print(_fmt(analyze()))
    print(f"\nconfig: {NGINX_CONF}")
