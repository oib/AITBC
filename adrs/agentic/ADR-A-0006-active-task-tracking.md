---
id: ADR-A-0006
title: Task tracking is active — status changes trigger agents
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

A passive tracker documents work; an active tracker drives it. If agents must be manually
poked, the human becomes the orchestrator — the opposite of the goal.

## Decision

We will treat ticket status changes as workflow triggers: every canonical status maps to a
workflow (`profiles/neutral/adapters/statuses.yaml`) and adapters must surface status-change events
(webhooks or polling). The canonical v1 statuses are: Backlog, Ready for Development,
In Progress, In Review, In Test, Ready for Human Acceptance, Ready for Merge, Done, Blocked
(plus the epic hand-off status Ready for PO). The boilerplate stays tracker-agnostic behind
`.agentic/adapters/task-tracking/INTERFACE.md`, with Jira Cloud and GitLab CE as prepared v1
adapters and a functional mock adapter as conformance reference.

## Consequences

Humans steer by moving tickets — the same gesture they already know — and the machine does the
rest. Every agent action is anchored to a ticket event, which makes the audit trail automatic.
Adapters carry the mapping burden so agents never see provider APIs.
