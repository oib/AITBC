# Company ADRs

Organization-level decisions that apply to every project in the company: GDPR/data-handling
rules, the company design system, company-wide engineering constraints, procurement policies.

- **Not copied by default in v1.** This directory starts empty; reference or add company ADRs
  manually (`config.adrs.company_reference_mode: manual`).
- Use the shared [ADR format](../agentic/README.md) with `scope: company`, ids `ADR-C-nnnn`.
- Agents may *propose* company ADRs; only humans accept them.
- In the authority order they sit between project and agentic ADRs: an accepted project ADR may
  override a company ADR only explicitly (`overrides:` field, human-accepted).
- A company design system is typically anchored here and referenced from
  `config.design_system.company_adr`.
