"""WEB-BC2-CUTDAY-1 — pin the website render's bc-2 cut and the keep-region.

``scripts/ops/render-website.sh`` rewrites the committed chain-id literal in
place on cut day (``WEBSITE_CHAIN_ID=bc-2``). These tests run the real script
on a tmp copy of ``website/`` driven by the script's own env overrides
(``AITBC_ROOT`` / ``WEBSITE_ENV_FILE`` / ``NODE_ENV_FILE`` / ``STATE_FILE``) —
nothing outside the tmpdir is touched, no ``/etc`` path is read.

``aitbc-keep:start``/``end`` markers exempt dated historical statements (the
announcement's publication note) from every rewrite while the file stays in
the render list for its URL rewrites.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "render-website.sh"
WEBSITE = REPO / "website"

OLD_ID = "ait-hub.aitbc.bubuit.net"
NEW_ID = "bc-2"
DOMAIN = "hub.aitbc.bubuit.net"
DATED_LINE = "Published: 2026-08-15"


def _committed_contact() -> str:
    m = re.search(r"mailto:([^\"]+)", (WEBSITE / "messages.html").read_text())
    return m.group(1) if m else "operator@example.net"


CONTACT = _committed_contact()


def _tree_files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _without_keep_regions(text: str) -> str:
    return re.sub(r"<!-- aitbc-keep:start -->.*?<!-- aitbc-keep:end -->", "", text, flags=re.S)


class TestRenderWebsite(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="render-website-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.site = self.tmp / "site"
        (self.site / "scripts" / "ops").mkdir(parents=True)
        shutil.copytree(WEBSITE, self.site / "website")
        shutil.copy2(SCRIPT, self.site / "scripts" / "ops" / "render-website.sh")
        # The committed tree already ships bc-2; transition tests need the
        # pre-migration start state, so seed the old id back into the two
        # files a render would have rewritten at cutover.
        for name in ("config.js", "dashboard.js"):
            p = self.site / "website" / name
            p.write_text(p.read_text().replace(NEW_ID, OLD_ID))
        self.env_file = self.tmp / "website.env"
        self.state_file = self.tmp / "state.env"
        # A prior old-id render would have left the old id in the state file;
        # that anchor is what lets the next render migrate the tokens.
        self.state_file.write_text(f"WEBSITE_DOMAIN={DOMAIN}\nWEBSITE_CHAIN_ID={OLD_ID}\n")

    def _write_env(self, chain_id: str, contact: str | None = CONTACT) -> None:
        lines = [f"WEBSITE_DOMAIN={DOMAIN}", f"WEBSITE_CHAIN_ID={chain_id}"]
        if contact is not None:
            lines.append(f"CONTACT_EMAIL={contact}")
        self.env_file.write_text("\n".join(lines) + "\n")

    def _render(self, state: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(
            os.environ,
            AITBC_ROOT=str(self.site),
            WEBSITE_ENV_FILE=str(self.env_file),
            NODE_ENV_FILE="/dev/null",
            STATE_FILE=str(state or self.state_file),
        )
        return subprocess.run(
            ["bash", str(self.site / "scripts" / "ops" / "render-website.sh")],
            capture_output=True,
            text=True,
            env=env,
        )

    def _render_to_new(self) -> None:
        self._write_env(NEW_ID)
        r = self._render()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_render_to_bc2_changes_expected_files(self) -> None:
        before = _tree_files(self.site / "website")
        self._render_to_new()
        after = _tree_files(self.site / "website")
        changed = {k for k in before if before[k] != after[k]}
        # Only the two chain-id files move: the announcement's one old-id
        # occurrence sits inside aitbc-keep markers, and every domain/URL
        # token already equals the target under this env.
        self.assertEqual(changed, {"config.js", "dashboard.js"})
        self.assertIn(f"chainId: '{NEW_ID}'", (self.site / "website/config.js").read_text())
        self.assertIn(f"'{NEW_ID}'", (self.site / "website/dashboard.js").read_text())

    def test_dated_line_is_kept_verbatim(self) -> None:
        self._render_to_new()
        text = (self.site / "website/follower-api-key-announcement.html").read_text()
        self.assertIn(f"{DATED_LINE} · Hub: <code>{OLD_ID}</code>", text)
        self.assertIn("aitbc-keep:start", text)

    def test_no_old_id_outside_keep_regions(self) -> None:
        self._render_to_new()
        for p in (self.site / "website").rglob("*"):
            if not p.is_file():
                continue
            stripped = _without_keep_regions(p.read_text(errors="replace"))
            self.assertNotIn(OLD_ID, stripped, p)

    def test_render_trigger_after_64k_of_input(self) -> None:
        # WEB-RIDERS-2 / #320: the trigger scan used to be
        # ``sed | grep -q`` — grep exits on the first match and sed dies on
        # SIGPIPE once >64KB is queued, which pipefail turns into a false
        # "no trigger" and the file is silently skipped. A file whose
        # renderable literal sits past the pipe buffer must still render.
        target = self.site / "website" / "dashboard.js"
        target.write_text(target.read_text() + "\n/*" + "x" * (80 * 1024) + "*/\n")
        self.assertGreater(target.stat().st_size, 64 * 1024, "fixture must exceed the pipe buffer")
        self._render_to_new()
        self.assertIn(f"'{NEW_ID}'", target.read_text(), "render skipped on a >64KB input")

    def test_second_render_is_idempotent(self) -> None:
        self._render_to_new()
        before = _tree_files(self.site / "website")
        r = self._render()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(before, _tree_files(self.site / "website"))
        self.assertTrue(
            "0 files updated" in r.stdout or "already up to date" in r.stdout,
            r.stdout,
        )

    def test_rollback_is_byte_identical(self) -> None:
        original = _tree_files(self.site / "website")
        self._render_to_new()
        self._write_env(OLD_ID)
        r = self._render()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(original, _tree_files(self.site / "website"))

    def test_partial_state_re_renders_to_new(self) -> None:
        self._render_to_new()
        # A pull reverted one file to the committed copy (bc-2 since
        # CHAINID-DEFAULT-1 — reverting can no longer reintroduce the old id).
        shutil.copy2(WEBSITE / "dashboard.js", self.site / "website" / "dashboard.js")
        r = self._render()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn(f"'{NEW_ID}'", (self.site / "website/dashboard.js").read_text())
        for p in (self.site / "website").rglob("*"):
            if p.is_file():
                self.assertNotIn(OLD_ID, _without_keep_regions(p.read_text(errors="replace")), p)

    def test_bad_chain_id_refused_before_touching_files(self) -> None:
        before = _tree_files(self.site / "website")
        self._write_env("bc 2")
        r = self._render()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Invalid WEBSITE_CHAIN_ID", r.stderr)
        self.assertEqual(before, _tree_files(self.site / "website"))

    def test_committed_tree_already_carries_bc2(self) -> None:
        """CHAINID-DEFAULT-1 pin: the committed website source is the bc-2
        render — re-introducing the old chain id outside a keep region or
        drifting the committed chainId fails here."""
        for p in WEBSITE.rglob("*"):
            if not p.is_file():
                continue
            stripped = _without_keep_regions(p.read_text(errors="replace"))
            self.assertNotIn(OLD_ID, stripped, p)
        self.assertIn(f"chainId: '{NEW_ID}'", (WEBSITE / "config.js").read_text())

    def test_unset_contact_empties_the_marked_region(self) -> None:
        """Documented design: unset CONTACT_EMAIL empties the aitbc-contact
        region rather than leaving stale content."""
        self._write_env(NEW_ID, contact=None)
        r = self._render()
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        text = (self.site / "website/messages.html").read_text()
        m = re.search(r"<!-- aitbc-contact:start -->(.*?)<!-- aitbc-contact:end -->", text, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("mailto:", m.group(1))


if __name__ == "__main__":
    unittest.main()
