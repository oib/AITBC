"""CLI-7: ``main()`` renders ``click.ClickException`` as clean output.

60+ ``raise click.ClickException`` sites exist across the command tree; with
``standalone_mode=False`` click re-raises them, so ``main()`` must catch and
``e.show()`` them. ``system logs --grep x --severity-pattern`` raises one
inside pure option validation — no filesystem or journal access needed.
"""

from __future__ import annotations

from aitbc_cli.core.main import main


def test_click_exception_prints_message_and_exit_code(capsys):
    rc = main(["system", "logs", "--service", "aitbc-market", "--grep", "a", "--severity-pattern"])
    captured = capsys.readouterr()
    assert rc == 1
    combined = captured.out + captured.err
    assert "mutually exclusive" in combined
    assert "Traceback" not in combined
    assert "ClickException" not in combined


def test_usage_error_still_exit_2(capsys):
    """The ClickException handler must not swallow the UsageError contract."""
    rc = main(["system", "logs"])  # --service is required
    captured = capsys.readouterr()
    assert rc == 2
    assert "Traceback" not in (captured.out + captured.err)


def test_success_path_unchanged(capsys):
    """main() returns the command's own value — None for most commands —
    so a clean run must not raise and must not print a traceback."""
    rc = main(["version"])
    captured = capsys.readouterr()
    assert rc in (0, None)
    assert "Traceback" not in (captured.out + captured.err)
