"""Retention policy helpers for regulated data (v0.15.1 §A3).

Provides ``RetentionSchedule`` and ``RetentionEngine`` for evaluating a set of
retention policies across classifications. These complement the core
``RetentionPolicy`` dataclass in ``aitbc.compliance.audit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .audit import RetentionAction, RetentionPolicy, retention_expired
from .policies import DataClassification, normalize_classification


@dataclass
class RetentionSchedule:
    """A mapping of data classifications to retention policies."""

    rules: dict[DataClassification, RetentionPolicy] = field(default_factory=dict)
    default_action: RetentionAction | str = RetentionAction.REVIEW
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.default_action, str):
            self.default_action = RetentionAction(self.default_action)
        normalized: dict[DataClassification, RetentionPolicy] = {}
        for classification, policy in self.rules.items():
            key = normalize_classification(classification)
            normalized[key] = policy
        self.rules = normalized

    def get_policy(
        self,
        classification: DataClassification | str,
    ) -> RetentionPolicy | None:
        """Return the retention policy for a classification, or None."""
        key = normalize_classification(classification)
        return self.rules.get(key)


@dataclass
class RetentionEngine:
    """Evaluate retention state and recommend actions for records."""

    schedule: RetentionSchedule
    grace_days: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def evaluate(
        self,
        classification: DataClassification | str,
        created_at: datetime,
        now: datetime | None = None,
    ) -> RetentionAction:
        """Return the action to take for a record of ``classification``."""
        if now is None:
            now = datetime.now(UTC)
        policy = self.schedule.get_policy(classification)
        if policy is None:
            action = self.schedule.default_action
            if isinstance(action, RetentionAction):
                return action
            return RetentionAction(action)
        effective_created = created_at + timedelta(days=self.grace_days)
        if retention_expired(policy, effective_created, now):
            action = policy.action
            if isinstance(action, RetentionAction):
                return action
            return RetentionAction(action)
        return RetentionAction.ARCHIVE

    def batch_evaluate(
        self,
        records: list[tuple[str, datetime, DataClassification | str]],
        now: datetime | None = None,
    ) -> dict[str, RetentionAction]:
        """Evaluate a batch of ``(record_id, created_at, classification)`` tuples."""
        results: dict[str, RetentionAction] = {}
        for record_id, created_at, classification in records:
            results[record_id] = self.evaluate(classification, created_at, now)
        return results


def apply_retention(
    policy: RetentionPolicy,
    created_at: datetime,
    now: datetime | None = None,
    default_action: RetentionAction = RetentionAction.ARCHIVE,
) -> RetentionAction:
    """Return the action to apply for a single record under ``policy``.

    If the retention period has not expired, returns ``default_action``.
    """
    if now is None:
        now = datetime.now(UTC)
    if retention_expired(policy, created_at, now):
        action = policy.action
        if isinstance(action, RetentionAction):
            return action
        return RetentionAction(action)
    return default_action
