"""Pin: tasks/_source/issue_check.py must exist — issue.py `queue` imports it.

#2642: the module was never committed, so `issue.py queue` died with
ModuleNotFoundError before printing anything. Read-only checks only; the
Gitea/git calls inside check_issues/report are exercised by `queue` itself.
"""

import unittest


class TestIssueCheckModule(unittest.TestCase):
    def test_module_imports_with_queue_contract(self):
        import issue_check

        self.assertTrue(callable(issue_check.report))
        self.assertTrue(callable(issue_check.check_issues))
        self.assertIsInstance(issue_check.PACE, float)

    def test_queue_source_imports_issue_check(self):
        import inspect

        import issue

        src = inspect.getsource(issue.do_queue)
        self.assertIn("import issue_check", src)


if __name__ == "__main__":
    unittest.main()
