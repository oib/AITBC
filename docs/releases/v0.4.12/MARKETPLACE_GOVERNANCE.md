# Software Marketplace Governance - v0.4.12

**Release**: v0.4.12
**Date**: June 7, 2026
**Status**: ✅ Implementation Complete

## Overview

AITBC v0.4.12 integrates governance with the software marketplace, enabling community governance of marketplace rules, fees, service approvals, and dispute resolution.

## Service Approval

### Propose New Service Type

```bash
# Propose new service type
aitbc governance propose --type service_approval --title "Add image generation service" --description "Add Stable Diffusion as supported service type"
```

### Features
- **Community approval**: Service types require community vote
- **Quality control**: Ensures service quality standards
- **Flexibility**: Easy to add new service types

## Fee Governance

### Propose Fee Change

```bash
# Propose fee change
aitbc governance propose --type fee_structure --title "Reduce escrow fee" --value 0.005
```

### Features
- **Transparent**: All fee changes require community vote
- **Flexible**: Easy to adjust fees based on market conditions
- **Accountable**: Fee changes are publicly recorded

## Dispute Resolution

### Propose Dispute Resolution

```bash
# Propose dispute resolution
aitbc governance propose --type dispute_resolution --title "Resolve dispute job_123" --description "Provider claims job completed, buyer disputes"
```

### Features
- **Fair resolution**: Community-based dispute resolution
- **Transparent**: All disputes and resolutions are public
- **Binding**: DAO decisions are binding

## CLI Commands

### Marketplace Governance

```bash
# Propose service approval
aitbc governance propose --type service_approval --title "Add image generation service" --description "Add Stable Diffusion as supported service type"

# Propose fee change
aitbc governance propose --type fee_structure --title "Reduce escrow fee" --value 0.005

# Propose dispute resolution
aitbc governance propose --type dispute_resolution --title "Resolve dispute job_123" --description "Provider claims job completed, buyer disputes"
```

---

*Last Updated: 2026-06-07*
