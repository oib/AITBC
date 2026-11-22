"""#2521: `aitbc market sync-ratings` must POST a bare JSON list to
/v1/market/ratings/mark-synced — the route's body is `list[str]`, so the
old ``{"rating_ids": [...]}`` object wrapper 422'd and ratings were never
marked synced.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.market import ratings as ratings_mod


@pytest.fixture
def calls(monkeypatch):
    recorded: dict[str, list] = {"get": [], "post": []}

    class _FakeClient:
        def __init__(self, base_url, timeout, api_key=None):
            self.base_url = base_url

        def get(self, path, params=None):
            recorded["get"].append((self.base_url, path, params))
            return {"ratings": [{"id": "r1"}, {"id": "r2"}]}

        def post(self, path, json=None):
            recorded["post"].append((self.base_url, path, json))
            if path.endswith("/ratings/sync"):
                return {"status": "success", "synced": 2, "updated": 0}
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
