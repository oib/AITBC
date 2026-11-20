"""Claim-reconcile pins for #2315 (Refs #2315).

``/v1/miners/poll`` delivers a claimed job only inside the claim
response; a lost response strands the row RUNNING coordinator-side.
``fetch_running_jobs`` + ``_reconcile_running_jobs`` re-dispatch any
RUNNING job the coordinator reports for this miner that is not already
in ``ACTIVE_JOB_IDS``. These tests pin the fetch shape, the dedup, the
capacity guard, and the poll-path refactor.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import pytest

import production_miner


def _resp(jobs):
    return Mock(status_code=200, json=lambda: {"jobs": jobs, "miner_id": production_miner.MINER_ID})


@pytest.mark.unit
@patch("production_miner.requests.get")
def test_fetch_running_jobs_returns_dispatch_shape(mock_get):
    mock_get.return_value = _resp(
        [
            {"job_id": "job-1", "payload": {"type": "inference"}, "constraints": {}, "expires_at": 1.0},
            {"job_id": "job-2", "payload": {"type": "transcribe"}},
        ]
    )

    jobs = production_miner.fetch_running_jobs()

    assert [j["job_id"] for j in jobs] == ["job-1", "job-2"]
    url = mock_get.call_args.args[0]
    assert url.endswith(f"/v1/miners/{production_miner.MINER_ID}/running-jobs")
    assert mock_get.call_args.kwargs["headers"]["X-Miner-ID"] == production_miner.MINER_ID
    assert mock_get.call_args.kwargs["headers"]["X-Api-Key"] == production_miner.AUTH_TOKEN


@pytest.mark.unit
@patch("production_miner.requests.get")
def test_fetch_running_jobs_error_returns_empty(mock_get):
    mock_get.side_effect = production_miner.requests.exceptions.ConnectionError("down")
    assert production_miner.fetch_running_jobs() == []

    import requests as _rq

    err = _rq.exceptions.HTTPError("err")
    err.response = Mock(status_code=500)
    mock_get.side_effect = None
    mock_get.return_value = Mock(status_code=500, raise_for_status=Mock(side_effect=err))
    assert production_miner.fetch_running_jobs() == []


@pytest.mark.unit
@patch("production_miner.fetch_running_jobs")
@patch("production_miner.execute_job")
def test_reconcile_dedups_held_job_via_claim_slot(mock_execute, mock_fetch):
    """The real _dispatch_job path: a job already in ACTIVE_JOB_IDS must
    not be re-dispatched."""
    production_miner.ACTIVE_JOB_IDS.add("held")
    try:
        mock_fetch.return_value = [
            {"job_id": "held", "payload": {}},
            {"job_id": "lost-1", "payload": {}},
        ]

        async def _run():
            production_miner._reconcile_running_jobs(models=[], max_concurrent_jobs=5)
            await asyncio.sleep(0.05)

        asyncio.run(_run())
        dispatched = [c.args[0]["job_id"] for c in mock_execute.call_args_list]
        assert dispatched == ["lost-1"]
    finally:
        production_miner.ACTIVE_JOB_IDS.discard("held")
        production_miner.ACTIVE_JOB_IDS.discard("lost-1")


@pytest.mark.unit
@patch("production_miner.fetch_running_jobs")
@patch("production_miner.execute_job")
def test_reconcile_respects_capacity(mock_execute, mock_fetch):
    production_miner.ACTIVE_JOB_IDS.add("held")
    try:
        mock_fetch.return_value = [
            {"job_id": "lost-1", "payload": {}},
            {"job_id": "lost-2", "payload": {}},
        ]

        async def _run():
            production_miner._reconcile_running_jobs(models=[], max_concurrent_jobs=2)
            await asyncio.sleep(0.05)

        asyncio.run(_run())
        dispatched = [c.args[0]["job_id"] for c in mock_execute.call_args_list]
        assert dispatched == ["lost-1"]
    finally:
        for jid in ("held", "lost-1", "lost-2"):
            production_miner.ACTIVE_JOB_IDS.discard(jid)


@pytest.mark.unit
@patch("production_miner.poll_for_jobs")
@patch("production_miner.fetch_running_jobs")
@patch("production_miner.execute_job")
def test_poll_cycle_skips_poll_when_reconcile_fills_capacity(mock_execute, mock_fetch, mock_poll):
    """If reconcile fills every slot, the cycle must not poll — a claimed
    job could not be dispatched locally until next cycle anyway."""
    production_miner.ACTIVE_JOB_IDS.add("held")
    try:
        mock_fetch.return_value = [{"job_id": "lost-1", "payload": {}}]
        mock_poll.return_value = {"job_id": "fresh", "payload": {}}

        async def _run():
            production_miner._poll_and_dispatch(models=[], max_concurrent_jobs=2)
            await asyncio.sleep(0.05)

        asyncio.run(_run())
        mock_poll.assert_not_called()
        dispatched = [c.args[0]["job_id"] for c in mock_execute.call_args_list]
        assert dispatched == ["lost-1"]
    finally:
        for jid in ("held", "lost-1", "fresh"):
            production_miner.ACTIVE_JOB_IDS.discard(jid)


@pytest.mark.unit
@patch("production_miner.poll_for_jobs")
@patch("production_miner.fetch_running_jobs")
@patch("production_miner.execute_job")
def test_poll_cycle_dispatches_fresh_job_after_empty_reconcile(mock_execute, mock_fetch, mock_poll):
    mock_fetch.return_value = []
    mock_poll.return_value = {"job_id": "fresh", "payload": {"type": "inference"}}

    async def _run():
        production_miner._poll_and_dispatch(models=[], max_concurrent_jobs=2)
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    dispatched = [c.args[0]["job_id"] for c in mock_execute.call_args_list]
    assert dispatched == ["fresh"]
    production_miner.ACTIVE_JOB_IDS.discard("fresh")
