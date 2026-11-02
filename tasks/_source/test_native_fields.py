"""Tests for the Gitea-native fields sync (GITEA-NATIVE-FIELDS-1, #822).

Run: python3 -m pytest test_native_fields.py -q   (or python3 test_native_fields.py)
Uses a fake `tea` client — no network, no Gitea.
"""

import types
import unittest
from unittest.mock import patch

import sync
from issue import do_close


class FakeGitea:
    """In-memory Gitea: issue dicts keyed by number, records writes."""

    def __init__(self, issues):
        self.issues = issues
        self.calls = []

    def __call__(self, path, method=None, data=None):
        self.calls.append((method or "GET", path, data))
        if path.startswith("/issues/") and "/dependencies" in path:
            n, m = int(path.split("/")[2]), (path.split("/")[4] if len(path.split("/")) > 4 else None)
            if method == "POST":
                self.issues[n].setdefault("dependencies", []).append({"number": data["index"], "state": "open"})
            elif method == "DELETE":
                self.issues[n]["dependencies"] = [d for d in self.issues[n]["dependencies"] if d["number"] != int(m)]
            elif method is None and m:
                raise AssertionError("unexpected")
            return self.issues[n].get("dependencies", [])
        if path.startswith("/issues/") and method == "PATCH":
            self.issues[int(path.split("/")[2])].update(data)
            return self.issues[int(path.split("/")[2])]
        if path.startswith("/issues/") and method is None:
            return self.issues[int(path.split("/")[2])]
        if "/labels/" in path or path.endswith("/labels"):
            return []
        if "/comments" in path:
            return {"id": 1}
        if path == "/labels?limit=50&page=1":
            return []
        raise AssertionError(f"unexpected tea call {method} {path}")


def _row(**kw):
    r = {"id": "R-1", "title": "t", "owner": "B", "status": "open", "ready": True, "issue": 10}
    r.update(kw)
    return r


class TestNativePlan(unittest.TestCase):
    def setUp(self):
        self.by_id = {"R-1": {"id": "R-1", "issue": 10}, "R-2": {"id": "R-2", "issue": 20}}

    def test_adds_missing_dependency(self):
        iss = {"number": 10, "dependencies": [], "labels": []}
        add, rem, due = sync.native_plan(_row(blocked_by=["R-2"]), iss, self.by_id)
        self.assertEqual(add, [20])
        self.assertEqual(rem, [])
        self.assertIsNone(due)

    def test_removes_dropped_dependency(self):
        iss = {"number": 10, "dependencies": [{"number": 20, "state": "open"}], "labels": []}
        add, rem, _ = sync.native_plan(_row(), iss, self.by_id)
        self.assertEqual(add, [])
        self.assertEqual(rem, [20])

    def test_due_date_written_and_cleared(self):
        iss = {"number": 10, "dependencies": [], "labels": []}
        _, _, due = sync.native_plan(_row(wait_until="2026-11-06"), iss, self.by_id)
        self.assertTrue(due.startswith("2026-11-06T23:59:59"))
        iss["due_date"] = "2026-11-07T00:00:00Z"
        _, _, due = sync.native_plan(_row(), iss, self.by_id)
        self.assertIsNone(due)  # not cleared: a hand-set due is not ours to erase
        _, _, due = sync.native_plan(_row(), iss, self.by_id, base_due="2026-11-07")
        self.assertEqual(due, "")  # cleared: the base recorded the due we pushed
        iss["due_date"] = "2026-11-06T23:59:59+01:00"
        _, _, due = sync.native_plan(_row(wait_until="2026-11-06"), iss, self.by_id)
        self.assertIsNone(due)  # already the right day

    def test_unknown_blocked_row_ignored(self):
        iss = {"number": 10, "dependencies": [], "labels": []}
        add, rem, _ = sync.native_plan(_row(blocked_by=["NOPE"]), iss, self.by_id)
        self.assertEqual((add, rem), ([], []))


class TestApplyAndClose(unittest.TestCase):
    def test_apply_native_writes_and_verifies(self):
        gitea = FakeGitea({10: {"number": 10, "dependencies": [{"number": 30, "state": "open"}], "labels": []}})
        with patch.object(sync, "tea", gitea):
            sync._apply_native(10, [20], [30], "2026-11-06T23:59:59+01:00")
        iss = gitea.issues[10]
        self.assertEqual([d["number"] for d in iss["dependencies"]], [20])
        self.assertTrue(iss["due_date"].startswith("2026-11-06"))

    def test_close_aborts_on_open_dependency(self):
        gitea = FakeGitea({10: {"number": 10, "dependencies": [{"number": 20, "state": "open"}], "labels": []}})
        args = types.SimpleNamespace(row="10", comment=None, result=None, ledger=None, dry_run=False, rider=None, area=None)
        with (
            patch("issue.tea", gitea),
            patch("issue.load", return_value=(None, None, [])),
            patch("issue.row_of_ref", return_value=({"issue": 10, "status": "closed", "close_result": "verified"}, True)),
            patch("issue.subprocess.run") as git_log,
            self.assertRaises(SystemExit) as cm,
        ):
            git_log.return_value.stdout = ""
            do_close(args)
        self.assertIn("waits for open #20", str(cm.exception))
        self.assertFalse(any(c[0] == "POST" and c[1].endswith("/comments") for c in gitea.calls))

    def test_close_passes_when_dependencies_closed(self):
        gitea = FakeGitea(
            {10: {"number": 10, "dependencies": [{"number": 20, "state": "closed"}], "labels": [], "state": "open"}}
        )
        args = types.SimpleNamespace(row="10", comment=None, result="r", ledger=None, dry_run=False, rider=None, area=None)
        with (
            patch("issue.tea", gitea),
            patch("issue.load", return_value=(None, None, [])),
            patch("issue.row_of_ref", return_value=({"issue": 10, "status": "closed", "close_result": "verified"}, True)),
            patch("issue.subprocess.run") as git_log,
            patch("issue.read_back", return_value=("closed", set(), None, None)),
        ):
            git_log.return_value.stdout = ""
            with self.assertRaises(SystemExit) as cm:
                do_close(args)
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
