#!/usr/bin/env python3
"""Cutover-Import Jira -> Agentic Backend (Operator-Tool, PILOT-45 / ABS-545).

Gegenstueck zu work/scratch/end-of-run-jira-export.py: WAEHREND der Export den
Backend-Zustand einmalig nach Jira spiegelt, importiert DIESES Tool einmalig alle
OFFENEN Jira-ABS-Tickets (statusCategory != Done) in ein NEUES Backend-Projekt
'ABS' (getrennt von der PILOT-Pilothistorie). Nach dem Cutover ist das Backend
alleinige Ticket-Quelle; die Jira-Seite bleibt lesbares Archiv (2 Releases).

Ablauf (Default = Dry-Run, schreibt NICHTS):
  1. Jira: alle offenen ABS-Issues lesen (Titel, Beschreibung, Labels, Typ,
     Status, Prioritaet, Parent, Issue-Links).
  2. Backend: pro Issue per Label 'jira:ABS-N' auf Duplikat pruefen
     (Idempotenz-Schluessel). Treffer -> uebernehmen, NICHT neu anlegen.
  3. CREATE (Epics zuerst, dann Tickets/Subtasks) in Projekt ABS:
       - Titel <- summary, Body <- geflaechte ADF-Beschreibung + Provenienz
       - Labels: role:/lane:/flag:-Ableitung in die Backend-Felder,
         Rest als Label; immer 'jira:ABS-N' (Rueckreferenz) + 'cutover-import'
       - Prioritaet gemappt (Hotfix wird NIE gesetzt, ABS-261 -> hoechstens high)
       - Parent: in-scope Jira-Parent -> Backend-Twin des Parents (--parent)
       - KEIN Statusmapping: alles landet per Default auf Backlog (analog Intake)
       - Marker-Kommentar '[cutover-import <- ABS-N]' am Backend-Item
  4. Links (depends-on/relates) verdrahten, wenn BEIDE Enden importiert wurden.
  5. Jira-Seite markieren: Kommentar '[cutover-import] -> <BACKEND-KEY>' +
     Label 'migrated-to-backend' (marker-guarded, idempotent).

Idempotenz: ein zweiter --execute-Lauf legt nichts doppelt an (Label-Dedup) und
setzt keinen zweiten Marker (Kommentar-Marker-Guard auf beiden Seiten).

Env: BACKEND_URL (default http://localhost:8420), BACKEND_TOKEN (sonst Keychain
BACKEND_BOOTSTRAP_TOKEN), JIRA_API_TOKEN (Keychain). Das Zielprojekt im Backend
ist IMMER 'ABS' (ererbtes TRACKER_PROJECT wird bewusst ueberschrieben, damit ein
versehentliches Schreiben nach PILOT unmoeglich ist). Das Backend-Projekt 'ABS'
muss vor --execute existieren (Anlage = Operator-Schritt, nicht Teil dieses Tools).

Exit codes: 0 = ok (Dry-Run, oder alle Writes ok); 1 = usage/env; 2 = Backend
nicht erreichbar / Zielprojekt fehlt; 3 = ein oder mehr Writes/Reads fehlgeschlagen.
"""
import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER = os.path.join(REPO, "scripts", "backend-tracker.sh")

JIRA_SITE = "https://lovebytecodes.atlassian.net"
JBASE = JIRA_SITE + "/rest/api/3"
JIRA_USER = "mhmnn9@gmail.com"
JIRA_SOURCE_PROJECT = "ABS"       # Quelle in Jira
BACKEND_TARGET_PROJECT = "ABS"    # NEUES Ziel-Projekt im Backend (nicht PILOT)

# Idempotenz-/Marker-Konventionen
JIRA_LABEL_FMT = "jira:{key}"              # Backend-Label = Rueckreferenz + Dedup-Key
IMPORT_LABEL = "cutover-import"            # Backend-Label: aus dem Cutover geboren
BACKEND_MARKER_FMT = "[cutover-import <- {key}]"   # Backend-Kommentar-Marker
JIRA_MARKER = "[cutover-import]"           # Jira-Kommentar-Marker (guard)
JIRA_MIGRATED_LABEL = "migrated-to-backend"

# Jira-Prioritaet -> Backend-Prioritaet. ABS-261: hotfix wird NIE automatisch
# gesetzt (das ist eine Human/PO-Board-Aktion) -> Highest wird auf high geklemmt.
PRIORITY_MAP = {
    "highest": "high", "high": "high", "medium": "normal",
    "low": "low", "lowest": "low",
}
VALID_ROLES = {"be-developer", "fe-developer", "data-engineer"}
VALID_LANES = {"normal", "fastlane"}
# Geschlossene v3-Flag-Menge (Adapter validiert dagegen). Ein Jira-Label
# 'flag:<x>' mit unbekanntem <x> wird NICHT zum --flag (das braeche create),
# sondern bleibt als Plain-Label erhalten -> keine Info verloren, kein Abbruch.
VALID_FLAGS = {"design", "security", "data", "skip-review", "skip-test"}
LABEL_CHARSET = re.compile(r"^[A-Za-z0-9._:-]+$")


def die(code, msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(code)


def keychain(service):
    p = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                       capture_output=True, text=True)
    tok = p.stdout.strip()
    if p.returncode != 0 or not tok:
        die(1, f"Keychain-Service '{service}' nicht lesbar: {p.stderr.strip() or 'leer'}")
    return tok


# ---------------------------------------------------------------- backend

class Backend:
    """Duenne Huelle um scripts/backend-tracker.sh, hart auf Projekt ABS gepinnt."""

    def __init__(self):
        self.env = os.environ.copy()
        self.env.setdefault("BACKEND_URL", "http://localhost:8420")
        # Ziel IMMER ABS — ererbtes TRACKER_PROJECT (z.B. PILOT) bewusst ueberschreiben.
        self.env["TRACKER_PROJECT"] = BACKEND_TARGET_PROJECT
        self.env["BACKEND_TOKEN"] = (self.env.get("BACKEND_TOKEN")
                                     or keychain("BACKEND_BOOTSTRAP_TOKEN"))

    def _run(self, *args, check=True):
        p = subprocess.run([TRACKER, *args], capture_output=True, text=True,
                           env=self.env, cwd=REPO)
        if check and p.returncode != 0:
            die(3, f"Backend-Adapter-Fehler bei '{os.path.basename(TRACKER)} {' '.join(args)}':\n"
                   f"{p.stderr.strip() or p.stdout.strip()}")
        return p.returncode, p.stdout, p.stderr

    def find_by_jira(self, jira_key):
        """Backend-Key eines bereits importierten Items (Label-Dedup) oder None.

        Weich: ein fehlendes Projekt / eine leere Trefferliste ist KEIN Fehler
        (Dry-Run vor Projektanlage moeglich); nur echte Ausgabe wird geparst."""
        rc, out, _ = self._run("search", "--label", JIRA_LABEL_FMT.format(key=jira_key),
                               check=False)
        if rc != 0:
            return None
        for line in out.splitlines():
            m = re.match(r"^([A-Z][A-Z0-9]*-\d+)\t", line)
            if m:
                return m.group(1)
        return None

    def project_reachable(self):
        rc, _, _ = self._run("search", "--type", "epic", check=False)
        return rc == 0

    def create(self, *, type_, title, body_file, parent, role, lane, priority, flags, labels):
        args = ["create", "--type", type_, "--title", title, "--prefix", BACKEND_TARGET_PROJECT,
                "--body-file", body_file]
        if parent:
            args += ["--parent", parent]
        if role:
            args += ["--role", role]
        if lane:
            args += ["--lane", lane]
        if priority:
            args += ["--priority", priority]
        for f in flags:
            args += ["--flag", f]
        for l in labels:
            args += ["--label", l]
        _, out, _ = self._run(*args)
        for line in reversed(out.splitlines()):
            m = re.match(r"^([A-Z][A-Z0-9]*-\d+)\s*$", line.strip())
            if m:
                return m.group(1)
        die(3, f"create lieferte keinen parsebaren Backend-Key:\n{out}")

    def comment(self, key, kind, actor, body_file):
        self._run("comment", key, "--kind", kind, "--actor", actor, "--body-file", body_file)

    def link(self, a, b, kind):
        self._run("link", a, b, kind)


# ---------------------------------------------------------------- jira

class JiraError(Exception):
    def __init__(self, method, path, code, body):
        super().__init__(f"Jira {method} {path} -> HTTP {code}: {body[:400]}")
        self.code = code


class Jira:
    def __init__(self):
        tok = keychain("JIRA_API_TOKEN")
        self.auth = base64.b64encode(f"{JIRA_USER}:{tok}".encode()).decode()

    def call(self, method, path, payload=None, params=None):
        url = JBASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Basic {self.auth}",
            "Content-Type": "application/json",
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
                return resp.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            raise JiraError(method, path, e.code, e.read().decode(errors="replace"))
        except urllib.error.URLError as e:
            die(3, f"Jira nicht erreichbar ({method} {path}): {e.reason}")

    def open_issues(self):
        """Alle offenen ABS-Issues (statusCategory != Done), seitenweise."""
        fields = "summary,description,issuetype,status,priority,labels,parent,issuelinks"
        jql = (f"project = {JIRA_SOURCE_PROJECT} AND statusCategory != Done "
               f"ORDER BY key ASC")
        issues, token = [], None
        while True:
            params = {"jql": jql, "fields": fields, "maxResults": 100}
            if token:
                params["nextPageToken"] = token
            _, res = self.call("GET", "/search/jql", params=params)
            issues += res.get("issues", [])
            token = res.get("nextPageToken")
            if res.get("isLast", True) or not token:
                break
        return issues


def adf_to_text(node):
    """Flacht einen ADF-Knoten grob in Klartext (fuer den Backend-Body)."""
    if not node:
        return ""
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t == "hardBreak":
        return "\n"
    inner = adf_to_text(node.get("content", []))
    if t in ("paragraph", "heading"):
        return inner + "\n\n"
    if t == "listItem":
        return "- " + inner.strip() + "\n"
    return inner


def adf(text):
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


# ---------------------------------------------------------------- mapping

def derive_fields(labels):
    """Jira-Labels -> (role, lane, flags, plain_labels). role:/lane:/flag:-Praefixe
    wandern in die Backend-Felder; unbekannte Werte bleiben Plain-Label."""
    role = lane = None
    flags, plain = [], []
    for raw in labels:
        prefix, _, val = raw.partition(":")
        pfx = prefix.lower()
        if pfx == "role" and val in VALID_ROLES:
            role = val
        elif pfx == "lane" and val in VALID_LANES:
            lane = val
        elif pfx == "flag" and val in VALID_FLAGS:
            flags.append(val)
        elif LABEL_CHARSET.match(raw):
            plain.append(raw)
        # sonst: Label mit ungueltigen Zeichen wird verworfen (Report vermerkt es nicht;
        # Backend akzeptiert es nicht)
    return role, lane, flags, plain


def map_priority(jira_priority):
    if not jira_priority:
        return ""  # kein Feld -> Backend-Default normal
    return PRIORITY_MAP.get(jira_priority.strip().lower(), "normal")


def backend_type(issuetype):
    it = issuetype.lower()
    if it == "epic":
        return "epic"
    if it in ("sub-task", "subtask"):
        return "subtask"
    return "ticket"


# ---------------------------------------------------------------- report

class Row:
    def __init__(self, jkey, action, detail):
        self.jkey, self.action, self.detail = jkey, action, detail
        self.result = "geplant (Dry-Run)"


def write_tmp(scratch, name, text):
    path = os.path.join(scratch, name)
    with open(path, "w") as f:
        f.write(text)
    return path


def build_body(iss, jkey, mapped_priority):
    f = iss["fields"]
    desc = adf_to_text(f.get("description")).strip() or "_(keine Beschreibung in Jira)_"
    today = datetime.date.today().isoformat()
    status = f.get("status", {}).get("name", "?")
    prio = (f.get("priority") or {}).get("name", "-")
    return (f"{desc}\n\n---\n"
            f"**Cutover-Provenienz.** Einmaliger Import aus Jira "
            f"[{jkey}]({JIRA_SITE}/browse/{jkey}) am {today} "
            f"(statusCategory != Done). Das Backend ist ab Cutover alleinige "
            f"Ticket-Quelle; die Jira-Seite bleibt Lese-Archiv.\n\n"
            f"- Rueckreferenz `jira_key`: {jkey}\n"
            f"- Jira-Status (NICHT gemappt, landet als Backlog): {status}\n"
            f"- Jira-Prioritaet: {prio} -> backend "
            f"`{mapped_priority or 'normal (default)'}`\n")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Cutover-Import Jira ABS -> Backend ABS (einmalig)")
    ap.add_argument("--execute", action="store_true",
                    help="Writes ausfuehren (Default: Dry-Run, nur planen/printen)")
    ap.add_argument("--only", default="",
                    help="Kommaliste: nur diese Jira-Keys importieren (Test/Teil-Cutover)")
    ap.add_argument("--scratch", default=os.path.join(REPO, "work", "scratch"),
                    help="Verzeichnis fuer temporaere Body-/Kommentar-Dateien")
    args = ap.parse_args()

    os.makedirs(args.scratch, exist_ok=True)
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    mode = "EXECUTE" if args.execute else "DRY-RUN"

    be = Backend()
    jira = Jira()

    if args.execute and not be.project_reachable():
        die(2, f"Backend-Projekt '{BACKEND_TARGET_PROJECT}' nicht erreichbar. "
               f"Vor --execute anlegen (Operator-Schritt).")

    issues = jira.open_issues()
    if only:
        issues = [i for i in issues if i["key"] in only]
    if not issues:
        die(1, "Kein offenes ABS-Issue im Scope.")

    # Epics zuerst, damit Kinder ihren Parent-Twin bekommen; sonst Jira-Key-Ordnung.
    rank = {"epic": 0, "ticket": 1, "subtask": 2}
    issues.sort(key=lambda i: (rank.get(backend_type(i["fields"]["issuetype"]["name"]), 1),
                               i["key"]))
    scope_keys = {i["key"] for i in issues}

    print(f"== Cutover-Import Jira {JIRA_SOURCE_PROJECT} -> Backend "
          f"{BACKEND_TARGET_PROJECT} [{mode}] — {len(issues)} offene Issues\n")

    jira2backend = {}     # ABS-N (Jira) -> ABS-M (Backend)
    rows = []
    read_failures, write_failures = [], []

    # ---- Pass 1: pruefen/erstellen (Epics -> Tickets -> Subtasks) -------------
    for iss in issues:
        jkey = iss["key"]
        f = iss["fields"]
        btype = backend_type(f["issuetype"]["name"])
        title = f.get("summary", "")

        existing = be.find_by_jira(jkey)
        if existing:
            jira2backend[jkey] = existing
            rows.append(Row(jkey, "SKIP-CREATE", f"bereits importiert als {existing} (Label-Dedup)"))
            continue

        role, lane, flags, plain = derive_fields(f.get("labels", []))
        plain = [IMPORT_LABEL, JIRA_LABEL_FMT.format(key=jkey)] + [p for p in plain
                 if p not in (IMPORT_LABEL,)]
        priority = map_priority((f.get("priority") or {}).get("name"))

        # Parent: nur wenn der Jira-Parent selbst im Cutover-Scope liegt (dann
        # existiert sein Twin — Epics werden zuerst angelegt) oder schon importiert war.
        parent_jkey = (f.get("parent") or {}).get("key")
        parent_in_scope = bool(parent_jkey) and (parent_jkey in scope_keys
                                                 or parent_jkey in jira2backend)
        parent_note = ""
        if parent_jkey and not parent_in_scope:
            parent_note = f", parent {parent_jkey} nicht im Scope -> ohne parent"

        detail = (f"CREATE {btype} \"{title[:60]}\" prio={priority or 'normal'} "
                  f"role={role or '-'} lane={lane or '-'} flags={flags or '-'} "
                  f"labels={plain}"
                  f"{(' parent=' + parent_jkey + ' (Twin)') if parent_in_scope else ''}{parent_note}")
        row = Row(jkey, "CREATE", detail)
        rows.append(row)

        if not args.execute:
            continue
        try:
            safe = jkey.replace("-", "_")
            body_file = write_tmp(args.scratch, f"import-body-{safe}.md",
                                  build_body(iss, jkey, priority))
            # Twin des Parents ist jetzt bekannt (Epics zuerst angelegt); None -> ohne parent.
            parent_bkey = jira2backend.get(parent_jkey) if parent_in_scope else None
            bkey = be.create(type_=btype, title=title, body_file=body_file,
                             parent=parent_bkey, role=role, lane=lane,
                             priority=priority, flags=flags, labels=plain)
            jira2backend[jkey] = bkey
            row.result = f"angelegt {bkey}"
            marker_file = write_tmp(args.scratch, f"import-marker-{safe}.md",
                                    f"{BACKEND_MARKER_FMT.format(key=jkey)} Cutover-Import "
                                    f"aus Jira {jkey} ({JIRA_SITE}/browse/{jkey}). "
                                    f"jira_key={jkey}.")
            be.comment(bkey, "notification", "operator", marker_file)
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001 — Report statt Abbruch
            row.result = f"FEHLER: {e}"
            write_failures.append(f"{jkey}: {e}")

    # ---- Pass 2: Links (depends-on / relates), beide Enden importiert ---------
    planned_links = set()   # (kind, a, b) — Duplikat-Guard
    for iss in issues:
        jkey = iss["key"]
        a = jira2backend.get(jkey)
        if not a:
            continue
        for lk in iss["fields"].get("issuelinks", []) or []:
            name = lk.get("type", {}).get("name", "")
            if "outwardIssue" in lk:
                other_j, this_blocks = lk["outwardIssue"]["key"], True
            elif "inwardIssue" in lk:
                other_j, this_blocks = lk["inwardIssue"]["key"], False
            else:
                continue
            b = jira2backend.get(other_j)
            if not b:
                rows.append(Row(jkey, "LINK-SKIP",
                                f"{name} -> {other_j} nicht in scope importiert"))
                continue
            if name == "Blocks":
                # blockiertes Item depends-on Blocker
                src, dst = (b, a) if this_blocks else (a, b)
                key = ("depends-on", src, dst)
                kind, detail = "depends-on", f"{src} depends-on {dst} (Jira {name})"
            else:
                lo, hi = sorted((a, b))
                key = ("relates", lo, hi)
                kind, detail = "relates", f"{lo} relates {hi} (Jira {name})"
                src, dst = lo, hi
            if key in planned_links:
                continue
            planned_links.add(key)
            row = Row(jkey, "LINK", detail)
            rows.append(row)
            if not args.execute:
                continue
            try:
                be.link(src, dst, kind)
                row.result = "verlinkt"
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001
                row.result = f"FEHLER: {e}"
                write_failures.append(f"{jkey} link: {e}")

    # ---- Pass 3: Jira-Seite markieren (Kommentar + Label), idempotent --------
    for iss in issues:
        jkey = iss["key"]
        bkey = jira2backend.get(jkey)
        if not bkey:
            continue
        # Kommentar-Marker-Guard
        try:
            _, cres = jira.call("GET", f"/issue/{jkey}/comment", params={"maxResults": 200})
            has_marker = JIRA_MARKER in json.dumps(cres.get("comments", []), ensure_ascii=False)
            cur_labels = iss["fields"].get("labels", [])
            need_label = JIRA_MIGRATED_LABEL not in cur_labels
        except JiraError as e:
            read_failures.append(f"{jkey}: Jira-Read fehlgeschlagen: {e}")
            continue

        if has_marker and not need_label:
            rows.append(Row(jkey, "JIRA-SKIP", "Marker + Label bereits vorhanden"))
            continue
        detail = "Jira-Seite: " + " + ".join(
            ([f"Kommentar '{JIRA_MARKER} -> {bkey}'"] if not has_marker else [])
            + ([f"Label '{JIRA_MIGRATED_LABEL}'"] if need_label else []))
        row = Row(jkey, "JIRA-MARK", detail)
        rows.append(row)
        if not args.execute:
            continue
        try:
            if not has_marker:
                jira.call("POST", f"/issue/{jkey}/comment",
                          {"body": adf(f"{JIRA_MARKER} -> {bkey}. Cutover: ab jetzt wird "
                                       f"dieses Ticket im Agentic Backend ({bkey}) gepflegt; "
                                       f"die Jira-Seite bleibt Lese-Archiv.")})
            if need_label:
                jira.call("PUT", f"/issue/{jkey}",
                          {"update": {"labels": [{"add": JIRA_MIGRATED_LABEL}]}})
            row.result = "markiert"
        except JiraError as e:
            row.result = f"FEHLER: {e}"
            write_failures.append(f"{jkey} jira-mark: {e}")

    # ---- Report --------------------------------------------------------------
    print(f"{'Jira':<10} {'Aktion':<12} Detail / Ergebnis")
    print("-" * 100)
    for r in rows:
        tail = f"  => {r.result}" if (args.execute and not r.action.endswith("SKIP")) else ""
        print(f"{r.jkey:<10} {r.action:<12} {r.detail}{tail}")

    created = sum(1 for r in rows if r.action == "CREATE")
    print(f"\n{len(jira2backend)} Jira->Backend-Twins gesamt, {created} neu geplant/angelegt.")
    if read_failures:
        print("\nREAD-FEHLER:")
        for x in read_failures:
            print(f"  - {x}")
    if write_failures:
        print("\nWRITE-FEHLER:")
        for x in write_failures:
            print(f"  - {x}")
    if read_failures or write_failures:
        sys.exit(3)
    if not args.execute:
        print("\nDry-Run — NICHTS geschrieben. Mit --execute ausfuehren.")
    sys.exit(0)


if __name__ == "__main__":
    main()
