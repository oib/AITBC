# Hermes Agent Training Learning Prompt

This document is a structured learning prompt for Hermes to learn the AITBC agent training curriculum.

## Learning Objective

Hermes should master the complete AITBC agent training program, understanding all 9 stages of agent development from foundation to multi-chain architecture.

## Learning Process

### Phase 1: Document Analysis
1. **Read and analyze** all documentation in `/docs/agent-training/`:
   - `README.md` - Overview and structure
   - `training_schema.json` - Schema definition
   - `ENVIRONMENT_SETUP.md` - Environment configuration
   - `OPERATIONS_AUDIT.md` - Operations coverage
   - `SCENARIO_STAGE_MAPPING.md` - Practical applications
   - All stage JSON files (`stage1_*.json` through `stage9_*.json`)

2. **Identify key patterns** across all stages:
   - Command structure and parameters
   - Validation criteria
   - Expected outcomes
   - Prerequisites and dependencies

### Phase 2: Stage Mastery
For each of the 9 training stages, Hermes should:

1. **Understand the stage objectives**
2. **Analyze the command sequences**
3. **Identify validation criteria**
4. **Map to practical scenarios**
5. **Note potential failure points**

### Phase 3: Debugging and Feedback

After analyzing each stage, Hermes should provide:

#### Debug Messages
- **Missing information**: What data is incomplete or unclear?
- **Inconsistencies**: Are there contradictions between stages?
- **Ambiguities**: What needs clarification?
- **Gaps**: What's missing from the training curriculum?

#### Suggestions
- **Improvements**: How can the training be enhanced?
- **Optimizations**: What can be streamlined?
- **Additions**: What topics should be covered?
- **Restructuring**: How can the curriculum be better organized?

#### Issue Identification
- **Potential failures**: What might go wrong during execution?
- **Dependency issues**: Are there missing prerequisites?
- **Environment problems**: What setup issues might occur?
- **Validation gaps**: Are success criteria sufficient?

## Stage-by-Stage Learning Guide

### Stage 1: Foundation
**Focus:** Wallet creation, basic transactions, mining, balance verification
**Key Learning:** Core blockchain interaction patterns
**Debug Focus:** CLI command syntax, wallet naming conventions, transaction signing

### Stage 2: Operations Mastery
**Focus:** Advanced wallet operations, transaction monitoring, blockchain queries
**Key Learning:** State management and transaction tracking
**Debug Focus:** Query patterns, monitoring commands, multi-wallet coordination

### Stage 3: AI Operations
**Focus:** Job submission, task management, result retrieval
**Key Learning:** Agent coordination and AI task orchestration
**Debug Focus:** API interactions, task lifecycle management, result parsing

### Stage 4: Marketplace Economics
**Focus:** Marketplace interaction, resource trading, price discovery
**Key Learning:** Economic modeling and market operations
**Debug Focus:** Trading mechanics, price feeds, resource allocation

### Stage 5: Expert Operations
**Focus:** Advanced agent behaviors, autonomous decision making
**Key Learning:** Complex task orchestration and performance optimization
**Debug Focus:** Decision logic, performance metrics, optimization strategies

### Stage 6: Agent Identity SDK
**Focus:** Identity management, authentication, permissions
**Key Learning:** Security protocols and identity workflows
**Debug Focus:** Auth flows, permission checks, security edge cases

### Stage 7: Cross-Node Training
**Focus:** Multi-node coordination, distributed consensus
**Key Learning:** Network topology and failover handling
**Debug Focus:** Node communication, consensus mechanisms, network partitions

### Stage 8: Advanced Agent Specialization
**Focus:** Domain-specific capabilities, expert systems
**Key Learning:** Specialized knowledge bases and custom skills
**Debug Focus:** Knowledge integration, skill development, domain logic

### Stage 9: Multi-Chain Architecture
**Focus:** Cross-chain operations, bridge protocols, interoperability
**Key Learning:** Multi-chain asset management and bridge patterns
**Debug Focus:** Bridge mechanics, cross-chain transactions, asset mapping

## Output Format

For each stage, Hermes should provide:

```markdown
## Stage Analysis: [Stage Name]

### Understanding Summary
[Brief summary of what Hermes learned]

### Debug Messages
- **Issue**: [Description]
  - **Impact**: [Why it matters]
  - **Suggested Fix**: [How to resolve]

### Suggestions
- **Improvement**: [Description]
  - **Rationale**: [Why it helps]
  - **Implementation**: [How to implement]

### Potential Failures
- **Failure Scenario**: [Description]
  - **Detection**: [How to identify]
  - **Mitigation**: [How to prevent]
```

## Final Deliverable

After completing all 9 stages, Hermes should provide:

1. **Comprehensive Learning Summary**: What was learned across all stages
2. **Cross-Stage Analysis**: Patterns and relationships between stages
3. **Curriculum Assessment**: Overall quality and completeness
4. **Implementation Roadmap**: How to apply this knowledge in practice
5. **Testing Strategy**: How to validate agent training success

## Interactive Feedback Protocol

When Hermes encounters issues during learning:

1. **Stop and document** the specific issue
2. **Provide context** from the relevant documentation
3. **Suggest alternatives** or workarounds
4. **Request clarification** if information is missing
5. **Propose improvements** to the documentation

## Success Criteria

Hermes has successfully learned when it can:
- Explain each stage's objectives and methods
- Identify potential issues before they occur
- Suggest improvements to the training curriculum
- Debug training execution problems
- Provide actionable feedback for curriculum enhancement

---

**Instructions for Use:**
1. Submit this prompt to Hermes along with access to `/docs/agent-training/`
2. Request Hermes to follow the learning process systematically
3. Collect Hermes's stage-by-stage analysis and feedback
4. Use the feedback to improve the training curriculum
5. Iterate based on Hermes's suggestions

**Last Updated:** 2026-05-09
**Version:** 2.0
**Purpose:** Hermes AI agent learning prompt for AITBC agent training curriculum
**Changelog:**
- v2.0 (2026-05-09): Added concrete examples, templates, and detail level guidelines
- v1.0 (2026-05-07): Initial version with basic learning process structure
