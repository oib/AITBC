"""#2521: `aitbc market sync-ratings` must POST a bare JSON list to
/v1/market/ratings/mark-synced — the route's body is `list[str]`, so the
old ``{"rating_ids": [...]}`` object wrapper 422'd and ratings were never
marked synced.
"""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.market import ratings as ratings_mod


@pytest.fixture
def calls(monkeypatch):
    recorded: dict[str, Any] = {"get": [], "post": []}
    recorded["sync_response"] = {"status": "success", "synced": 2, "updated": 0, "skipped": 0, "failed": 0}

    class _FakeClient:
        def __init__(self, base_url, timeout, api_key=None):
            self.base_url = base_url

        def get(self, path, params=None):
            recorded["get"].append((self.base_url, path, params))
            return {"ratings": [{"id": "r1"}, {"id": "r2"}]}

        def post(self, path, json=None):
            recorded["post"].append((self.base_url, path, json))
            if path.endswith("/ratings/sync"):
                return dict(recorded["sync_response"])
            if path.endswith("/ratings/mark-synced"):
                return {"status": "success", "marked_synced": 2}
            return {"status": "success"}

    monkeypatch.setattr(ratings_mod, "AITBCHTTPClient", _FakeClient)
    return recorded


def test_mark_synced_posts_bare_list(calls):
    r = CliRunner().invoke(ratings_mod.sync_ratings, ["--remote-url", "http://remote:8102"])
    assert r.exit_code == 0, r.output

    mark = [c for c in calls["post"] if c[1].endswith("/ratings/mark-synced")]
    assert len(mark) == 1
    base_url, _path, body = mark[0]
    assert base_url == "http://localhost:8102"
    assert body == ["r1", "r2"]
    assert isinstance(body, list)


def test_sync_still_posts_rating_objects(calls):
    r = CliRunner().invoke(ratings_mod.sync_ratings, ["--remote-url", "http://remote:8102"])
    assert r.exit_code == 0, r.output
    sync = [c for c in calls["post"] if c[1].endswith("/ratings/sync")]
    assert len(sync) == 1
    assert sync[0][2] == [{"id": "r1"}, {"id": "r2"}]


def _mark_calls(calls):
    return [c for c in calls["post"] if c[1].endswith("/ratings/mark-synced")]


def test_failed_rows_are_not_marked_synced(calls):
    """#2522: remote reports failed>0 -> nothing is marked synced."""
    calls["sync_response"] = {"status": "success", "synced": 1, "updated": 0, "skipped": 0, "failed": 1}
    r = CliRunner().invoke(ratings_mod.sync_ratings, ["--remote-url", "http://remote:8102"])
    assert r.exit_code == 0, r.output
    assert _mark_calls(calls) == []
    assert "failed" in r.output.lower() or "did not accept" in r.output


def test_count_shortfall_is_not_marked_synced(calls):
    """#2522: synced+skipped+updated < sent -> the batch isn't fully accepted."""
    calls["sync_response"] = {"status": "success", "synced": 1, "updated": 0, "skipped": 0, "failed": 0}
    r = CliRunner().invoke(ratings_mod.sync_ratings, ["--remote-url", "http://remote:8102"])
    assert r.exit_code == 0, r.output
    assert _mark_calls(calls) == []


def test_skipped_rows_still_count_as_accepted(calls):
    """#2522: already-present (skipped) ratings were delivered — they mark fine."""
    calls["sync_response"] = {"status": "success", "synced": 1, "updated": 0, "skipped": 1, "failed": 0}
    r = CliRunner().invoke(ratings_mod.sync_ratings, ["--remote-url", "http://remote:8102"])
    assert r.exit_code == 0, r.output
    mark = _mark_calls(calls)
    assert len(mark) == 1 and mark[0][2] == ["r1", "r2"]
