---
id: ADR-A-0007
title: All external systems live behind neutral adapter interfaces
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

The boilerplate must be technology-neutral across trackers, git hosts, design tools, and secret
stores — and must ship v1 without productive integrations while remaining fully exercisable.

## Decision

We will confine every tool-specific behavior behind the interfaces in `.agentic/adapters/`
(task tracking, git, notifications, design system, secrets). Agents speak only canonical
operations; providers are selected in config; the mock task-tracking adapter is a fully
functional reference and the conformance baseline for real adapters. v1 ships interfaces and
reference manifests (Jira Cloud, GitLab CE, Figma-backed design system) — no productive
integration code.

## Consequences

Provider swaps are config changes. New providers implement a documented, conformance-testable
interface. The entire SDLC is dry-runnable locally against mocks, which also makes the
boilerplate itself testable without external accounts.
