# Vorschläge für konkrete Korrekturaufgaben (Codebasis-Review)

## 1) Aufgabe: Tippfehler in Dokumentations-Links korrigieren

**Problem:** In der Datei `docs/8_development/1_overview.md` zeigen mehrere „Next Steps“-Links auf Dateinamen ohne den numerischen Präfix und laufen dadurch ins Leere (z. B. `setup.md`, `api-authentication.md`, `contributing.md`).

**Vorschlag:** Alle betroffenen relativen Links auf die tatsächlichen Dateien mit Präfix umstellen (z. B. `2_setup.md`, `6_api-authentication.md`, `3_contributing.md`).

**Akzeptanzkriterien:**
- Kein 404/Dead-Link mehr aus `1_overview.md` auf interne Entwicklungsdokumente.
- Link-Check (`markdown-link-check` oder vergleichbar) für `docs/8_development/1_overview.md` läuft ohne Fehler.

---

## 2) Aufgabe: Programmierfehler in `config export` beheben

**Problem:** In `cli/aitbc_cli/commands/config.py` wird bei `export` das YAML geladen und anschließend direkt `if 'api_key' in config_data:` geprüft. Ist die Datei leer, liefert `yaml.safe_load` den Wert `None`; die Membership-Prüfung wirft dann einen `TypeError`.

**Vorschlag:** Nach dem Laden defensiv normalisieren, z. B. `config_data = yaml.safe_load(f) or {}`.

**Akzeptanzkriterien:**
- `aitbc config export` mit leerer Config-Datei bricht nicht mit Exception ab.
- Rückgabe bleibt valide (leere Struktur in YAML/JSON statt Traceback).

---

## 3) Aufgabe: Dokumentations-Unstimmigkeit zu Python-Version bereinigen

**Problem:** `docs/1_project/3_infrastructure.md` nennt „Python 3.11+“ als Laufzeitannahme, während das Root-`pyproject.toml` `requires-python = ">=3.8"` definiert. Das ist widersprüchlich für Contributor und CI.

**Vorschlag:** Versionsstrategie vereinheitlichen:
- Entweder Doku auf den tatsächlich unterstützten Bereich anpassen,
- oder Projektmetadaten/Tooling auf 3.11+ anheben (inkl. CI-Matrix).

**Akzeptanzkriterien:**
- Doku und Projektmetadaten nennen dieselbe minimale Python-Version.
- CI/Tests dokumentieren und nutzen diese Zielversion konsistent.

---

## 4) Aufgabe: Testabdeckung verbessern (doppelte Testfunktion in `test_config.py`)

**Problem:** In `tests/cli/test_config.py` existiert die Testfunktion `test_environments` zweimal. In Python überschreibt die zweite Definition die erste, wodurch ein Testfall effektiv verloren geht.

**Vorschlag:**
- Eindeutige Testnamen vergeben (z. B. `test_environments_table_output` und `test_environments_json_output`).
- Optional parametrisierte Tests nutzen, um Dopplungen robust abzudecken.

**Akzeptanzkriterien:**
- Keine doppelten Testfunktionsnamen mehr in der Datei.
- Beide bislang beabsichtigten Szenarien werden tatsächlich ausgeführt und sind im Testreport sichtbar.
