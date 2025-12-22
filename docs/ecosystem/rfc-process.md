# AITBC Request for Comments (RFC) Process

## Overview

The RFC (Request for Comments) process is the primary mechanism for proposing and discussing major changes to the AITBC protocol, ecosystem, and governance. This process ensures transparency, community involvement, and thorough technical review before significant changes are implemented.

## Process Stages

### 1. Idea Discussion (Pre-RFC)
- Open issue on GitHub with `idea:` prefix
- Community discussion in GitHub issue
- No formal process required
- Purpose: Gauge interest and gather early feedback

### 2. RFC Draft
- Create RFC document using template
- Submit Pull Request to `rfcs` repository
- PR labeled `rfc-draft`
- Community review period: 2 weeks minimum

### 3. RFC Review
- Core team assigns reviewers
- Technical review by subject matter experts
- Community feedback incorporated
- PR labeled `rfc-review`

### 4. Final Comment Period (FCP)
- RFC marked as `final-comment-period`
- 10 day waiting period for final objections
- All substantive objections must be addressed
- PR labeled `fcp`

### 5. Acceptance or Rejection
- After FCP, RFC is either:
  - **Accepted**: Implementation begins
  - **Rejected**: Document archived with reasoning
  - **Deferred**: Returned to draft for revisions

### 6. Implementation
- Accepted RFCs enter implementation queue
- Implementation tracked in project board
- Progress updates in RFC comments
- Completion marked in RFC status

## RFC Categories

### Protocol (P)
- Core protocol changes
- Consensus modifications
- Cryptographic updates
- Cross-chain improvements

### API (A)
- REST API changes
- SDK specifications
- WebSocket protocols
- Integration interfaces

### Ecosystem (E)
- Marketplace standards
- Connector specifications
- Certification requirements
- Developer tools

### Governance (G)
- Process changes
- Election procedures
- Foundation policies
- Community guidelines

### Network (N)
- Node operations
- Staking requirements
- Validator specifications
- Network parameters

## RFC Template

```markdown
# RFC XXX: [Title]

- **Start Date**: YYYY-MM-DD
- **RFC PR**: [link to PR]
- **Authors**: [@username1, @username2]
- **Status**: Draft | Review | FCP | Accepted | Rejected | Deferred
- **Category**: [P|A|E|G|N]

## Summary

[One-paragraph summary of the proposal]

## Motivation

[Why is this change needed? What problem does it solve?]

## Detailed Design

[Technical specifications, implementation details]

## Rationale and Alternatives

[Why this approach over alternatives?]

## Impact

[Effects on existing systems, migration requirements]

## Security Considerations

[Security implications and mitigations]

## Testing Strategy

[How will this be tested?]

## Unresolved Questions

[Open issues to be resolved]

## Implementation Plan

[Timeline and milestones]
```

## Submission Guidelines

### Before Submitting
1. Search existing RFCs to avoid duplicates
2. Discuss idea in GitHub issue first
3. Get feedback from community
4. Address obvious concerns early

### Required Elements
- Complete RFC template
- Clear problem statement
- Detailed technical specification
- Security analysis
- Implementation plan

### Formatting
- Use Markdown with proper headings
- Include diagrams where helpful
- Link to relevant issues/PRs
- Keep RFC focused and concise

## Review Process

### Reviewer Roles
- **Technical Reviewer**: Validates technical correctness
- **Security Reviewer**: Assesses security implications
- **Community Reviewer**: Ensures ecosystem impact considered
- **Core Team**: Final decision authority

### Review Criteria
- Technical soundness
- Security implications
- Ecosystem impact
- Implementation feasibility
- Community consensus

### Timeline
- Initial review: 2 weeks
- Address feedback: 1-2 weeks
- FCP: 10 days
- Total: 3-5 weeks typical

## Decision Making

### Benevolent Dictator Model (Current)
- AITBC Foundation has final say
- Veto power for critical decisions
- Explicit veto reasons required
- Community feedback strongly considered

### Transition Plan
- After 100 RFCs or 2 years: Review governance model
- Consider delegate voting system
- Gradual decentralization
- Community vote on transition

### Appeal Process
- RFC authors can appeal rejection
- Appeal reviewed by expanded committee
- Final decision documented
- Process improvement considered

## RFC Repository Structure

```
rfcs/
├── 0000-template.md
├── 0001-example.md
├── text/
│   ├── 0000-template.md
│   ├── 0001-example.md
│   └── ...
├── accepted/
│   ├── 0001-example.md
│   └── ...
├── rejected/
│   └── ...
└── README.md
```

## RFC Status Tracking

### Status Labels
- `rfc-draft`: Initial submission
- `rfc-review`: Under review
- `rfc-fcp`: Final comment period
- `rfc-accepted`: Approved for implementation
- `rfc-rejected`: Not approved
- `rfc-implemented`: Complete
- `rfc-deferred`: Returned to draft

### RFC Numbers
- Sequential numbering from 0001
- Reserved ranges for special cases
- PR numbers may differ from RFC numbers

## Community Participation

### How to Participate
1. Review draft RFCs
2. Comment with constructive feedback
3. Submit implementation proposals
4. Join community discussions
5. Vote in governance decisions

### Expectations
- Professional and respectful discourse
- Technical arguments over opinions
- Consider ecosystem impact
- Help newcomers understand

### Recognition
- Contributors acknowledged in RFC
- Implementation credit in releases
- Community appreciation in governance

## Implementation Tracking

### Implementation Board
- GitHub Project board tracks RFCs
- Columns: Proposed, In Review, FCP, Accepted, In Progress, Complete
- Assignees and timelines visible
- Dependencies and blockers noted

### Progress Updates
- Weekly updates in RFC comments
- Milestone completion notifications
- Blocker escalation process
- Completion celebration

## Special Cases

### Emergency RFCs
- Security vulnerabilities
- Critical bugs
- Network threats
- Accelerated process: 48-hour review

### Informational RFCs
- Design documents
- Best practices
- Architecture decisions
- No implementation required

### Withdrawn RFCs
- Author may withdraw anytime
- Reason documented
- Learning preserved
- Resubmission allowed

## Tools and Automation

### GitHub Automation
- PR templates for RFCs
- Label management
- Reviewer assignment
- Status tracking

### CI/CD Integration
- RFC format validation
- Link checking
- Diagram rendering
- PDF generation

### Analytics
- RFC submission rate
- Review time metrics
- Community participation
- Implementation success

## Historical Context

### Inspiration
- Rust RFC process
- Ethereum EIP process
- IETF standards process
- Apache governance

### Evolution
- Process improvements via RFCs
- Community feedback incorporation
- Governance transitions
- Lessons learned

## Contact Information

- **RFC Repository**: https://github.com/aitbc/rfcs
- **Discussions**: https://github.com/aitbc/rfcs/discussions
- **Governance**: governance@aitbc.io
- **Process Issues**: Use GitHub issues in rfcs repo

## FAQ

### Q: Who can submit an RFC?
A: Anyone in the community can submit RFCs.

### Q: How long does the process take?
A: Typically 3-5 weeks from draft to decision.

### Q: Can RFCs be rejected?
A: Yes, RFCs can be rejected with clear reasoning.

### Q: What happens after acceptance?
A: RFC enters implementation queue with timeline.

### Q: How is governance decided?
A: Currently benevolent dictator model, transitioning to community governance.

### Q: Can I implement before acceptance?
A: No, wait for RFC acceptance to avoid wasted effort.

### Q: How are conflicts resolved?
A: Through discussion, mediation, and Foundation decision if needed.

### Q: Where can I ask questions?
A: GitHub discussions, Discord, or governance email.
