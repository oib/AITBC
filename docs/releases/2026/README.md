# Release notes — 2026 topic-organized index

**Level**: All Levels
**Last Updated**: November 26, 2026

This directory is the post-#2974 layout of `docs/releases/`. Release notes
are organized **by topic** (each subsystem's running history, versions as
sections, newest first) instead of by version directory. The pre-reorg
version-organized tree is preserved in git history; the machine-readable
accounting of every moved/split file is `MANIFEST.csv` (verify with
`python3 scripts/docs/reorg-release-logs.py --verify`).

## Topic logs

| File | Covers |
|------|--------|
| [consensus_release.log](consensus_release.log) | consensus, attestation, finality, forks, mempool, validators, governance |
| [bridge_release.log](bridge_release.log) | bridge, cross-chain, atomic settlement, trading, exchange, order books |
| [market_release.log](market_release.log) | market, offers, listings, discovery, shop/storefront, IPFS hosting |
| [escrow_release.log](escrow_release.log) | escrow, payments, refunds, locks, disputes, payouts, billing |
| [agent_release.log](agent_release.log) | agent coordinator, agent spend/staking, bounty, autonomous tasks, TEE |
| [wallet_release.log](wallet_release.log) | wallet, custody, seed/mnemonic, keys |
| [cli_release.log](cli_release.log) | CLI commands, exit codes, argparse surface |
| [deploy_ops_release.log](deploy_ops_release.log) | deployment, systemd, fleet/hosts, backup/restore, failover, monitoring, infra |
| [security_release.log](security_release.log) | auth, secrets/credentials, encryption, audits, hardening, compliance |
| [website_release.log](website_release.log) | website, web UI, explorer frontend, CSS/HTML/pages |
| [testing_release.log](testing_release.log) | tests, coverage, CI, pytest/lint/mypy gates, scenarios, ratchets |
| [performance_release.log](performance_release.log) | performance, latency, memory/footprint, caching, benchmarks |
| [docs_meta_release.log](docs_meta_release.log) | documentation, release process, agent harness/skills, repo split, changelog |
| [general_release.log](general_release.log) | version overviews, verification summaries, breaking changes, migration guides — plus every split log's preamble |

## Supporting artifacts

Non-log artifacts (per-version `_AGENTS.md`, `_suggestions.md`,
`_overview.md`, bug-hunt reports, plans, audits, unsectioned logs) moved
to [`versions/<version>/`](versions/) — same directory names as the old
tree (`versions/v0.10/`, `versions/v1.0/`, ...), so relative links between
them still resolve.

## Historical note

The retired `docs/releases/archive/` README described the v0.0.x–v0.4.x
series: early prototypes and proof-of-concept work (v0.0.x–v0.3.x) and the
pre-marketplace foundation releases (v0.4.x — blockchain primitives,
wallet basics, agent identity experiments). Those files now live under
`versions/v0.3/` … `versions/v0.4/` like every other supporting artifact.

## Version index

Each version's notes are distributed across the topic files above; every split release log also contributes its overview/preamble to `general_release.log`.

### v1.0.0

- [Deploy & Ops](deploy_ops_release.log#v100)
- [General](general_release.log#v100)
- [Security](security_release.log#v100)
- [Testing](testing_release.log#v100)

### v0.29.0

- [Agent](agent_release.log#v0290)
- [Consensus](consensus_release.log#v0290)
- [Deploy & Ops](deploy_ops_release.log#v0290)
- [General](general_release.log#v0290)
- [Security](security_release.log#v0290)

### v0.28.0

- [CLI](cli_release.log#v0280)
- [Consensus](consensus_release.log#v0280)
- [Deploy & Ops](deploy_ops_release.log#v0280)
- [General](general_release.log#v0280)
- [Market](market_release.log#v0280)
- [Testing](testing_release.log#v0280)

### v0.27.0

- [Agent](agent_release.log#v0270)
- [Deploy & Ops](deploy_ops_release.log#v0270)
- [General](general_release.log#v0270)
- [Performance](performance_release.log#v0270)

### v0.26.0

- [Agent](agent_release.log#v0260)
- [Bridge & Trading](bridge_release.log#v0260)
- [CLI](cli_release.log#v0260)
- [Consensus](consensus_release.log#v0260)
- [Deploy & Ops](deploy_ops_release.log#v0260)
- [Docs & Meta](docs_meta_release.log#v0260)
- [Escrow & Payments](escrow_release.log#v0260)
- [General](general_release.log#v0260)
- [Market](market_release.log#v0260)
- [Security](security_release.log#v0260)
- [Testing](testing_release.log#v0260)

### v0.25.13

- [Bridge & Trading](bridge_release.log#v02513)
- [CLI](cli_release.log#v02513)
- [Deploy & Ops](deploy_ops_release.log#v02513)
- [Docs & Meta](docs_meta_release.log#v02513)
- [Escrow & Payments](escrow_release.log#v02513)
- [General](general_release.log#v02513)

### v0.25.12

- [Agent](agent_release.log#v02512)
- [Bridge & Trading](bridge_release.log#v02512)
- [CLI](cli_release.log#v02512)
- [Consensus](consensus_release.log#v02512)
- [Deploy & Ops](deploy_ops_release.log#v02512)
- [Docs & Meta](docs_meta_release.log#v02512)
- [Escrow & Payments](escrow_release.log#v02512)
- [General](general_release.log#v02512)
- [Market](market_release.log#v02512)
- [Testing](testing_release.log#v02512)
- [Wallet](wallet_release.log#v02512)
- [Website](website_release.log#v02512)

### v0.25.11

- [Agent](agent_release.log#v02511)
- [Bridge & Trading](bridge_release.log#v02511)
- [CLI](cli_release.log#v02511)
- [Deploy & Ops](deploy_ops_release.log#v02511)
- [Escrow & Payments](escrow_release.log#v02511)
- [General](general_release.log#v02511)
- [Market](market_release.log#v02511)
- [Performance](performance_release.log#v02511)
- [Security](security_release.log#v02511)
- [Testing](testing_release.log#v02511)
- [Wallet](wallet_release.log#v02511)
- [Website](website_release.log#v02511)

### v0.25.10

- [Bridge & Trading](bridge_release.log#v02510)
- [Consensus](consensus_release.log#v02510)
- [Deploy & Ops](deploy_ops_release.log#v02510)
- [General](general_release.log#v02510)
- [Wallet](wallet_release.log#v02510)

### v0.25.9

- [Agent](agent_release.log#v0259)
- [Bridge & Trading](bridge_release.log#v0259)
- [Consensus](consensus_release.log#v0259)
- [Deploy & Ops](deploy_ops_release.log#v0259)
- [Docs & Meta](docs_meta_release.log#v0259)
- [Escrow & Payments](escrow_release.log#v0259)
- [General](general_release.log#v0259)
- [Market](market_release.log#v0259)
- [Security](security_release.log#v0259)
- [Testing](testing_release.log#v0259)
- [Wallet](wallet_release.log#v0259)
- [Website](website_release.log#v0259)

### v0.25.8

- [Agent](agent_release.log#v0258)
- [Consensus](consensus_release.log#v0258)
- [Deploy & Ops](deploy_ops_release.log#v0258)
- [Docs & Meta](docs_meta_release.log#v0258)
- [General](general_release.log#v0258)
- [Security](security_release.log#v0258)

### v0.25.7

- [Bridge & Trading](bridge_release.log#v0257)
- [General](general_release.log#v0257)
- [Security](security_release.log#v0257)

### v0.25.6

- [Agent](agent_release.log#v0256)
- [Bridge & Trading](bridge_release.log#v0256)
- [CLI](cli_release.log#v0256)
- [Consensus](consensus_release.log#v0256)
- [Deploy & Ops](deploy_ops_release.log#v0256)
- [Docs & Meta](docs_meta_release.log#v0256)
- [Escrow & Payments](escrow_release.log#v0256)
- [General](general_release.log#v0256)
- [Testing](testing_release.log#v0256)
- [Wallet](wallet_release.log#v0256)

### v0.25.5

- [CLI](cli_release.log#v0255)
- [Consensus](consensus_release.log#v0255)
- [Deploy & Ops](deploy_ops_release.log#v0255)
- [Escrow & Payments](escrow_release.log#v0255)
- [General](general_release.log#v0255)
- [Market](market_release.log#v0255)
- [Security](security_release.log#v0255)
- [Testing](testing_release.log#v0255)

### v0.25.4

- [General](general_release.log#v0254)

### v0.25.3

- [Agent](agent_release.log#v0253)
- [Bridge & Trading](bridge_release.log#v0253)
- [Consensus](consensus_release.log#v0253)
- [Escrow & Payments](escrow_release.log#v0253)
- [General](general_release.log#v0253)
- [Market](market_release.log#v0253)

### v0.25.2

- [Deploy & Ops](deploy_ops_release.log#v0252)
- [General](general_release.log#v0252)

### v0.25.1

- [General](general_release.log#v0251)

### v0.25.0

- [Docs & Meta](docs_meta_release.log#v0250)
- [Escrow & Payments](escrow_release.log#v0250)
- [General](general_release.log#v0250)

### v0.24.18

- [Deploy & Ops](deploy_ops_release.log#v02418)
- [Escrow & Payments](escrow_release.log#v02418)
- [General](general_release.log#v02418)
- [Market](market_release.log#v02418)

### v0.24.17

- [General](general_release.log#v02417)

### v0.24.16

- [Deploy & Ops](deploy_ops_release.log#v02416)
- [General](general_release.log#v02416)
- [Market](market_release.log#v02416)

### v0.24.15

- [Agent](agent_release.log#v02415)
- [Consensus](consensus_release.log#v02415)
- [General](general_release.log#v02415)

### v0.24.14

- [Consensus](consensus_release.log#v02414)
- [Docs & Meta](docs_meta_release.log#v02414)
- [Escrow & Payments](escrow_release.log#v02414)
- [General](general_release.log#v02414)

### v0.24.13

- [Consensus](consensus_release.log#v02413)
- [General](general_release.log#v02413)

### v0.24.12

- [Bridge & Trading](bridge_release.log#v02412)
- [Consensus](consensus_release.log#v02412)
- [General](general_release.log#v02412)

### v0.24.11

- [General](general_release.log#v02411)
- [Performance](performance_release.log#v02411)

### v0.24.10

- [Bridge & Trading](bridge_release.log#v02410)
- [General](general_release.log#v02410)

### v0.24.9

- [General](general_release.log#v0249)
- [Wallet](wallet_release.log#v0249)

### v0.24.8

- [Consensus](consensus_release.log#v0248)
- [Docs & Meta](docs_meta_release.log#v0248)
- [Escrow & Payments](escrow_release.log#v0248)
- [General](general_release.log#v0248)

### v0.24.7

- [General](general_release.log#v0247)

### v0.24.6

- [Escrow & Payments](escrow_release.log#v0246)
- [General](general_release.log#v0246)
- [Market](market_release.log#v0246)

### v0.24.5

- [Bridge & Trading](bridge_release.log#v0245)
- [Consensus](consensus_release.log#v0245)
- [General](general_release.log#v0245)
- [Market](market_release.log#v0245)
- [Security](security_release.log#v0245)

### v0.24.4

- [Escrow & Payments](escrow_release.log#v0244)
- [General](general_release.log#v0244)

### v0.24.3

- [Consensus](consensus_release.log#v0243)
- [Escrow & Payments](escrow_release.log#v0243)
- [General](general_release.log#v0243)
- [Market](market_release.log#v0243)

### v0.24.2

- [Deploy & Ops](deploy_ops_release.log#v0242)
- [Docs & Meta](docs_meta_release.log#v0242)
- [General](general_release.log#v0242)
- [Security](security_release.log#v0242)

### v0.24.1

- [Agent](agent_release.log#v0241)
- [CLI](cli_release.log#v0241)
- [Consensus](consensus_release.log#v0241)
- [Escrow & Payments](escrow_release.log#v0241)
- [General](general_release.log#v0241)
- [Market](market_release.log#v0241)
- [Testing](testing_release.log#v0241)

### v0.23.34

- [Agent](agent_release.log#v02334)
- [Bridge & Trading](bridge_release.log#v02334)
- [Consensus](consensus_release.log#v02334)
- [Deploy & Ops](deploy_ops_release.log#v02334)
- [Escrow & Payments](escrow_release.log#v02334)
- [General](general_release.log#v02334)
- [Market](market_release.log#v02334)
- [Security](security_release.log#v02334)
- [Testing](testing_release.log#v02334)

### v0.23.33

- [General](general_release.log#v02333)

### v0.23.32

- [General](general_release.log#v02332)
- [Testing](testing_release.log#v02332)

### v0.23.31

- [Deploy & Ops](deploy_ops_release.log#v02331)
- [General](general_release.log#v02331)

### v0.23.30

- [Bridge & Trading](bridge_release.log#v02330)
- [Escrow & Payments](escrow_release.log#v02330)
- [General](general_release.log#v02330)

### v0.23.29

- [General](general_release.log#v02329)

### v0.23.28

- [General](general_release.log#v02328)
- [Testing](testing_release.log#v02328)

### v0.23.27

- [General](general_release.log#v02327)
- [Testing](testing_release.log#v02327)

### v0.23.26

- [General](general_release.log#v02326)

### v0.23.25

- [General](general_release.log#v02325)
- [Testing](testing_release.log#v02325)
- [Wallet](wallet_release.log#v02325)

### v0.23.24

- [CLI](cli_release.log#v02324)
- [General](general_release.log#v02324)

### v0.23.23

- [Deploy & Ops](deploy_ops_release.log#v02323)
- [General](general_release.log#v02323)

### v0.23.22

- [Agent](agent_release.log#v02322)
- [General](general_release.log#v02322)
- [Testing](testing_release.log#v02322)

### v0.23.21

- [General](general_release.log#v02321)

### v0.23.20

- [General](general_release.log#v02320)

### v0.23.19

- [General](general_release.log#v02319)
- [Security](security_release.log#v02319)

### v0.23.18

- [General](general_release.log#v02318)
- [Security](security_release.log#v02318)

### v0.23.17

- [General](general_release.log#v02317)
- [Security](security_release.log#v02317)
- [Testing](testing_release.log#v02317)

### v0.23.16

- [Consensus](consensus_release.log#v02316)
- [General](general_release.log#v02316)
- [Testing](testing_release.log#v02316)

### v0.23.15

- [General](general_release.log#v02315)

### v0.23.14

- [Escrow & Payments](escrow_release.log#v02314)
- [General](general_release.log#v02314)
- [Testing](testing_release.log#v02314)

### v0.23.13

- [General](general_release.log#v02313)

### v0.23.12

- [General](general_release.log#v02312)

### v0.23.11

- [Deploy & Ops](deploy_ops_release.log#v02311)
- [General](general_release.log#v02311)

### v0.23.10

- [General](general_release.log#v02310)
- [Security](security_release.log#v02310)

### v0.23.9

- [General](general_release.log#v0239)

### v0.23.8

- [Deploy & Ops](deploy_ops_release.log#v0238)
- [General](general_release.log#v0238)

### v0.23.7

- [General](general_release.log#v0237)

### v0.23.6

- [General](general_release.log#v0236)
- [Market](market_release.log#v0236)

### v0.23.5

- [General](general_release.log#v0235)
- [Market](market_release.log#v0235)

### v0.23.4

- [General](general_release.log#v0234)
- [Testing](testing_release.log#v0234)

### v0.23.3

- [General](general_release.log#v0233)
- [Security](security_release.log#v0233)

### v0.23.2

- [General](general_release.log#v0232)
- [Wallet](wallet_release.log#v0232)

### v0.23.1

- [General](general_release.log#v0231)

### v0.23

- [CLI](cli_release.log#v023)
- [Consensus](consensus_release.log#v023)
- [Deploy & Ops](deploy_ops_release.log#v023)
- [General](general_release.log#v023)
- [Security](security_release.log#v023)

### v0.22

- [CLI](cli_release.log#v022)
- [Docs & Meta](docs_meta_release.log#v022)
- [General](general_release.log#v022)
- [Security](security_release.log#v022)
- [Testing](testing_release.log#v022)

### v0.20.4

- [General](general_release.log#v0204)

### v0.20.0

- [General](general_release.log#v0200)

### v0.19.0

- [Docs & Meta](docs_meta_release.log#v0190)
- [General](general_release.log#v0190)
- [Security](security_release.log#v0190)

### v0.18.0

- [General](general_release.log#v0180)

### v0.17.0

- [General](general_release.log#v0170)

### v0.16.2

- [General](general_release.log#v0162)

### v0.16.1

- [General](general_release.log#v0161)

### v0.15.2

- [General](general_release.log#v0152)

### v0.15.1

- [General](general_release.log#v0151)

### v0.14.2

- [General](general_release.log#v0142)

### v0.14.1

- [General](general_release.log#v0141)

### v0.13.0

- [General](general_release.log#v0130)

### v0.12.0

- [General](general_release.log#v0120)

### v0.11.0

- [General](general_release.log#v0110)

### v0.10.18

- [General](general_release.log#v01018)

### v0.10.17

- [General](general_release.log#v01017)

### v0.10.16

- [General](general_release.log#v01016)

### v0.10.15

- [General](general_release.log#v01015)

### v0.10.14

- [General](general_release.log#v01014)
- [Testing](testing_release.log#v01014)

### v0.10.13

- [General](general_release.log#v01013)
- [Testing](testing_release.log#v01013)

### v0.10.12

- [General](general_release.log#v01012)
- [Testing](testing_release.log#v01012)

### v0.10.11

- [General](general_release.log#v01011)
- [Security](security_release.log#v01011)
- [Testing](testing_release.log#v01011)

### v0.10.10

- [General](general_release.log#v01010)
- [Testing](testing_release.log#v01010)

### v0.10.9

- [General](general_release.log#v0109)
- [Testing](testing_release.log#v0109)

### v0.10.8

- [General](general_release.log#v0108)
- [Testing](testing_release.log#v0108)

### v0.10.7

- [General](general_release.log#v0107)
- [Testing](testing_release.log#v0107)

### v0.10.6

- [General](general_release.log#v0106)
- [Testing](testing_release.log#v0106)

### v0.10.5

- [General](general_release.log#v0105)

### v0.10.4

- [General](general_release.log#v0104)
- [Testing](testing_release.log#v0104)

### v0.10.3

- [Bridge & Trading](bridge_release.log#v0103)
- [Deploy & Ops](deploy_ops_release.log#v0103)
- [General](general_release.log#v0103)
- [Testing](testing_release.log#v0103)

### v0.10.2

- [General](general_release.log#v0102)
- [Testing](testing_release.log#v0102)

### v0.10.1

- [Docs & Meta](docs_meta_release.log#v0101)
- [General](general_release.log#v0101)

### v0.10.0

- [Deploy & Ops](deploy_ops_release.log#v0100)
- [General](general_release.log#v0100)

### v0.9.0

- [CLI](cli_release.log#v090)
- [Docs & Meta](docs_meta_release.log#v090)
- [General](general_release.log#v090)
- [Performance](performance_release.log#v090)
- [Security](security_release.log#v090)
- [Testing](testing_release.log#v090)

### v0.8.2

- [CLI](cli_release.log#v082)
- [Docs & Meta](docs_meta_release.log#v082)
- [General](general_release.log#v082)
- [Performance](performance_release.log#v082)
- [Security](security_release.log#v082)
- [Testing](testing_release.log#v082)

### v0.8.1

- [CLI](cli_release.log#v081)
- [Docs & Meta](docs_meta_release.log#v081)
- [General](general_release.log#v081)
- [Performance](performance_release.log#v081)
- [Security](security_release.log#v081)
- [Testing](testing_release.log#v081)

### v0.8.0

- [CLI](cli_release.log#v080)
- [Docs & Meta](docs_meta_release.log#v080)
- [General](general_release.log#v080)
- [Performance](performance_release.log#v080)
- [Security](security_release.log#v080)
- [Testing](testing_release.log#v080)

### v0.7.5

- [General](general_release.log#v075)
- [Security](security_release.log#v075)

### v0.7.4

- [CLI](cli_release.log#v074)
- [Docs & Meta](docs_meta_release.log#v074)
- [General](general_release.log#v074)
- [Performance](performance_release.log#v074)
- [Security](security_release.log#v074)
- [Testing](testing_release.log#v074)

### v0.7.3

- [Docs & Meta](docs_meta_release.log#v073)
- [General](general_release.log#v073)
- [Performance](performance_release.log#v073)
- [Security](security_release.log#v073)
- [Testing](testing_release.log#v073)

### v0.7.2

- [CLI](cli_release.log#v072)
- [Docs & Meta](docs_meta_release.log#v072)
- [General](general_release.log#v072)
- [Security](security_release.log#v072)
- [Testing](testing_release.log#v072)

### v0.7.1

- [CLI](cli_release.log#v071)
- [Docs & Meta](docs_meta_release.log#v071)
- [General](general_release.log#v071)
- [Security](security_release.log#v071)
- [Testing](testing_release.log#v071)

### v0.7.0

- [Docs & Meta](docs_meta_release.log#v070)
- [General](general_release.log#v070)
- [Performance](performance_release.log#v070)
- [Security](security_release.log#v070)
- [Testing](testing_release.log#v070)

### v0.6.7

- [Docs & Meta](docs_meta_release.log#v067)
- [General](general_release.log#v067)
- [Performance](performance_release.log#v067)
- [Security](security_release.log#v067)
- [Testing](testing_release.log#v067)

### v0.6.6

- [Docs & Meta](docs_meta_release.log#v066)
- [General](general_release.log#v066)
- [Performance](performance_release.log#v066)
- [Security](security_release.log#v066)
- [Testing](testing_release.log#v066)

### v0.6.5

- [Docs & Meta](docs_meta_release.log#v065)
- [General](general_release.log#v065)
- [Performance](performance_release.log#v065)
- [Security](security_release.log#v065)
- [Testing](testing_release.log#v065)

### v0.6.4

- [CLI](cli_release.log#v064)
- [Docs & Meta](docs_meta_release.log#v064)
- [General](general_release.log#v064)
- [Performance](performance_release.log#v064)
- [Security](security_release.log#v064)
- [Testing](testing_release.log#v064)

### v0.6.3

- [CLI](cli_release.log#v063)
- [Docs & Meta](docs_meta_release.log#v063)
- [General](general_release.log#v063)
- [Performance](performance_release.log#v063)
- [Security](security_release.log#v063)
- [Testing](testing_release.log#v063)

### v0.6.2

- [CLI](cli_release.log#v062)
- [Docs & Meta](docs_meta_release.log#v062)
- [General](general_release.log#v062)
- [Performance](performance_release.log#v062)
- [Security](security_release.log#v062)
- [Testing](testing_release.log#v062)

### v0.6.1

- [Docs & Meta](docs_meta_release.log#v061)
- [General](general_release.log#v061)
- [Performance](performance_release.log#v061)
- [Security](security_release.log#v061)
- [Testing](testing_release.log#v061)

### v0.6.0

- [General](general_release.log#v060)
- [Performance](performance_release.log#v060)
- [Security](security_release.log#v060)
- [Testing](testing_release.log#v060)

### v0.5.19

- [General](general_release.log#v0519)
- [Testing](testing_release.log#v0519)

### v0.5.18

- [General](general_release.log#v0518)
- [Testing](testing_release.log#v0518)

### v0.5.17

- [Docs & Meta](docs_meta_release.log#v0517)
- [General](general_release.log#v0517)
- [Performance](performance_release.log#v0517)
- [Security](security_release.log#v0517)
- [Testing](testing_release.log#v0517)

### v0.5.16

- [Docs & Meta](docs_meta_release.log#v0516)
- [General](general_release.log#v0516)
- [Performance](performance_release.log#v0516)
- [Security](security_release.log#v0516)
- [Testing](testing_release.log#v0516)

### v0.5.15

- [Agent](agent_release.log#v0515)
- [Deploy & Ops](deploy_ops_release.log#v0515)
- [Docs & Meta](docs_meta_release.log#v0515)
- [General](general_release.log#v0515)
- [Market](market_release.log#v0515)
- [Testing](testing_release.log#v0515)

### v0.5.14

- [General](general_release.log#v0514)

### v0.5.13

- [General](general_release.log#v0513)

### v0.5.12

- [Agent](agent_release.log#v0512)
- [General](general_release.log#v0512)

### v0.5.11

- [Agent](agent_release.log#v0511)
- [General](general_release.log#v0511)

### v0.5.10

- [General](general_release.log#v0510)

### v0.5.9

- [General](general_release.log#v059)

### v0.5.8

- [General](general_release.log#v058)

### v0.5.7

- [Deploy & Ops](deploy_ops_release.log#v057)
- [General](general_release.log#v057)

### v0.5.6

- [General](general_release.log#v056)

### v0.5.5

- [General](general_release.log#v055)

### v0.5.4

- [Deploy & Ops](deploy_ops_release.log#v054)
- [General](general_release.log#v054)
- [Market](market_release.log#v054)

### v0.5.3

- [Agent](agent_release.log#v053)
- [General](general_release.log#v053)

### v0.5.2

- [Docs & Meta](docs_meta_release.log#v052)
- [General](general_release.log#v052)
- [Testing](testing_release.log#v052)

### v0.5.1

- [General](general_release.log#v051)

### v0.5.0

- [Deploy & Ops](deploy_ops_release.log#v050)
- [Docs & Meta](docs_meta_release.log#v050)
- [General](general_release.log#v050)
- [Performance](performance_release.log#v050)
- [Security](security_release.log#v050)

### v0.4.27

- [Deploy & Ops](deploy_ops_release.log#v0427)
- [General](general_release.log#v0427)

### v0.4.26

- [General](general_release.log#v0426)

### v0.4.25

- [Agent](agent_release.log#v0425)
- [General](general_release.log#v0425)
- [Market](market_release.log#v0425)
- [Security](security_release.log#v0425)
- [Testing](testing_release.log#v0425)

### v0.4.24

- [Agent](agent_release.log#v0424)
- [General](general_release.log#v0424)

### v0.4.21

- [General](general_release.log#v0421)

### v0.4.20

- [Agent](agent_release.log#v0420)
- [General](general_release.log#v0420)
- [Testing](testing_release.log#v0420)

### v0.4.19

- [Agent](agent_release.log#v0419)
- [General](general_release.log#v0419)

### v0.4.18

- [General](general_release.log#v0418)
- [Testing](testing_release.log#v0418)

### v0.4.17

- [General](general_release.log#v0417)
- [Performance](performance_release.log#v0417)
- [Testing](testing_release.log#v0417)

### v0.4.15

- [Docs & Meta](docs_meta_release.log#v0415)
- [General](general_release.log#v0415)
- [Performance](performance_release.log#v0415)
- [Security](security_release.log#v0415)
- [Testing](testing_release.log#v0415)

### v0.4.14

- [Docs & Meta](docs_meta_release.log#v0414)
- [General](general_release.log#v0414)
- [Performance](performance_release.log#v0414)
- [Security](security_release.log#v0414)
- [Testing](testing_release.log#v0414)

### v0.4.13

- [Docs & Meta](docs_meta_release.log#v0413)
- [General](general_release.log#v0413)
- [Performance](performance_release.log#v0413)
- [Security](security_release.log#v0413)
- [Testing](testing_release.log#v0413)

### v0.4.11

- [Docs & Meta](docs_meta_release.log#v0411)
- [General](general_release.log#v0411)
- [Performance](performance_release.log#v0411)
- [Testing](testing_release.log#v0411)

### v0.4.10

- [Docs & Meta](docs_meta_release.log#v0410)
- [General](general_release.log#v0410)
- [Performance](performance_release.log#v0410)
- [Security](security_release.log#v0410)
- [Testing](testing_release.log#v0410)

### v0.4.9

- [Docs & Meta](docs_meta_release.log#v049)
- [General](general_release.log#v049)
- [Performance](performance_release.log#v049)
- [Security](security_release.log#v049)
- [Testing](testing_release.log#v049)

### v0.4.8

- [Docs & Meta](docs_meta_release.log#v048)
- [General](general_release.log#v048)
- [Performance](performance_release.log#v048)
- [Security](security_release.log#v048)
- [Testing](testing_release.log#v048)

### v0.4.5

- [Docs & Meta](docs_meta_release.log#v045)
- [General](general_release.log#v045)
- [Performance](performance_release.log#v045)
- [Security](security_release.log#v045)
- [Testing](testing_release.log#v045)

### v0.4.3

- [Docs & Meta](docs_meta_release.log#v043)
- [General](general_release.log#v043)
- [Performance](performance_release.log#v043)
- [Security](security_release.log#v043)
- [Testing](testing_release.log#v043)

### v0.4.2

- [Agent](agent_release.log#v042)
- [Deploy & Ops](deploy_ops_release.log#v042)
- [Docs & Meta](docs_meta_release.log#v042)
- [General](general_release.log#v042)
- [Market](market_release.log#v042)
- [Security](security_release.log#v042)
- [Testing](testing_release.log#v042)
- [Website](website_release.log#v042)

### v0.4.1

- [CLI](cli_release.log#v041)
- [Deploy & Ops](deploy_ops_release.log#v041)
- [Docs & Meta](docs_meta_release.log#v041)
- [General](general_release.log#v041)
- [Security](security_release.log#v041)
- [Testing](testing_release.log#v041)

### v0.4.0

- [Deploy & Ops](deploy_ops_release.log#v040)
- [Docs & Meta](docs_meta_release.log#v040)
- [General](general_release.log#v040)
- [Security](security_release.log#v040)
- [Testing](testing_release.log#v040)

### v0.3.9

- [General](general_release.log#v039)
- [Market](market_release.log#v039)
- [Performance](performance_release.log#v039)

### v0.3.8

- [General](general_release.log#v038)
- [Performance](performance_release.log#v038)

### v0.3.7

- [General](general_release.log#v037)
- [Market](market_release.log#v037)
- [Performance](performance_release.log#v037)
