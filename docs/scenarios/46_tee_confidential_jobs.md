# Scenario 46: Confidential AI job with TEE attestation

**Level**: Intermediate
**Prerequisites**: Scenario 47 ZK Proofs for High-Value Jobs
**Estimated Time**: 10 minutes
**Last Updated**: 2026-11-21
**Version**: 2.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Confidential AI job with TEE attestation

---

## See Also

- **Previous Scenario**: [Contract Deploy & Call](./73_contract_deploy_call.md)
- **Next Scenario**: [43 Compliance, Plugins and White-Label](./43_compliance_plugins_white_label.md)
- **Related**: [74 Confidential Payments](./74_confidential_payments.md) (non-enclave Pedersen commitments — still live), [47 ZK High-Value Jobs](./47_zk_high_value_jobs.md) (the surviving high-value gate), [44 Refund a Failed TEE Job Escrow](./44_stuck_tee_refund.md) (also obsolete)

---

> **Descoped — TEE support removed (#2375, 21 Nov 2026).**
>
> Operator ruling: no enclave hardware (SGX/SEV/TPM) will ever exist on the
> fleet, so the entire TEE surface was deleted: the `aitbc tee` CLI group,
> the coordinator attestation API (`/v1/tee/attestations/...`), miner TEE
> quote generation, the `tee_attestation_required`/`tee_enclave_id`/
> `enclave_measurement` job constraints, the `tee_quote`/`tee_attestation_id`
> submit fields, and the ≥10 AIT TEE high-value settlement gate. High-value
> jobs are now governed by the ZK receipt gate alone (Scenario 47).
>
> Confidential *payments* (Pedersen amount commitments, `aitbc confidential`)
> are unrelated to enclaves and remain — see Scenario 74. The `--confidential`
> flag on job submission still sets `constraints.confidential` but no longer
> implies any attestation requirement.
>
> This scenario is retained for history only. The original playbook
> (enclave registration → confidential job submit → verified-attestation
> escrow release, v1.0) exercised a simulated attestation path even before
> removal — no live node ever had a hardware root of trust — and every
> command it documented (`aitbc tee register/status/verify/keygen/launch/
> attest`, `ai submit --enclave-measurement`) no longer resolves. The
> runnable steps are removed rather than left as false documentation.

## What the scenario covered (historical)

A confidential inference job marked `confidential` +
`tee_attestation_required`, pinned to an enclave measurement, whose escrow
released only after the coordinator verified a registered-enclave TEE
attestation on the job receipt (`tee_status: verified`). Without a verified
registered attestation the escrow refunded (`tee_quote_missing` /
`unregistered_enclave`). Live evidence existed only for the simulated
self-consistency path; hardware-backed attestation was always deferred.

## Notes

- Refunds for failed jobs remain available through the generic escrow
  paths (see Scenario 44's successor notes and `market escrow release` as
  the manual recovery path).
- If confidential *payment* semantics are what you need, use Scenario 74 —
  it exercises the Pedersen commitment path that survived the excision.
