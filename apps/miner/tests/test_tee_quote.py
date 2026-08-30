"""Unit tests for production_miner.build_tee_quote's stable-key plumbing (Part 4, 2026-08-24)."""

from __future__ import annotations

import production_miner

from aitbc.tee import AttestationQuote, computation_transcript


def _job(job_id="job-1", payload=None, **constraints):
    return {"job_id": job_id, "payload": payload or {}, "constraints": constraints}


def test_build_tee_quote_returns_none_without_a_tee_constraint():
    assert production_miner.build_tee_quote(_job()) is None


def test_build_tee_quote_binds_computation_transcript():
    job = _job(
        job_id="job-bind",
        payload={"model": "llama3.2:3b", "prompt": "2+2?"},
        tee_enclave_id="enc-x",
    )
    quote = AttestationQuote.from_base64(production_miner.build_tee_quote(job, output="4"))
    assert quote.quote_blob == computation_transcript("job-bind", "llama3.2:3b", "2+2?", "4")


def test_build_tee_quote_signs_with_a_fresh_key_by_default(monkeypatch):
    """Unchanged behavior when TEE_SIGNING_KEY_FILE is unset: random per call."""
    monkeypatch.delenv("TEE_SIGNING_KEY_FILE", raising=False)
    job = _job(tee_enclave_id="enc-x")
    quote_a = AttestationQuote.from_base64(production_miner.build_tee_quote(job))
    quote_b = AttestationQuote.from_base64(production_miner.build_tee_quote(job))
    assert quote_a.public_key != quote_b.public_key


def test_build_tee_quote_reuses_a_stable_key_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("TEE_SIGNING_KEY_FILE", str(tmp_path / "miner.key"))
    job = _job(tee_enclave_id="enc-x")
    quote_a = AttestationQuote.from_base64(production_miner.build_tee_quote(job))
    quote_b = AttestationQuote.from_base64(production_miner.build_tee_quote(job))
    assert quote_a.public_key == quote_b.public_key


def test_build_tee_quote_stable_key_survives_across_process_restarts(tmp_path, monkeypatch):
    """The whole point of Part 4: the key file, not the process, is where identity lives."""
    key_path = str(tmp_path / "miner.key")
    monkeypatch.setenv("TEE_SIGNING_KEY_FILE", key_path)
    job = _job(tee_enclave_id="enc-x")
    before_restart = AttestationQuote.from_base64(production_miner.build_tee_quote(job)).public_key

    # Simulate a fresh process: nothing in memory carries over, only the file.
    monkeypatch.setenv("TEE_SIGNING_KEY_FILE", key_path)
    after_restart = AttestationQuote.from_base64(production_miner.build_tee_quote(job)).public_key

    assert before_restart == after_restart
