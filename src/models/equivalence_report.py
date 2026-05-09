"""Behavioral Equivalence Report (BER) — output of Equivalence Validator Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TestStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a single equivalence test case."""

    test_id: str
    description: str
    status: TestStatus
    bsg_node_id: str
    business_rule_ids: list[str] = field(default_factory=list)
    expected: str | None = None
    actual: str | None = None
    error_message: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS


@dataclass
class BehavioralEquivalenceReport:
    """Aggregated equivalence report across all test cases."""

    scenario_id: str
    results: list[TestResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def passed_tests(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_tests(self) -> int:
        return self.total_tests - self.passed_tests

    @property
    def behavioral_equivalence_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed_tests / self.total_tests) * 100.0

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def failed_rule_ids(self) -> set[str]:
        """Business rule IDs that were not preserved."""
        ids: set[str] = set()
        for r in self.results:
            if not r.passed:
                ids.update(r.business_rule_ids)
        return ids

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "behavioral_equivalence_rate": round(self.behavioral_equivalence_rate, 2),
            "total_tests": self.total_tests,
            "passed": self.passed_tests,
            "failed": self.failed_tests,
            "results": [
                {
                    "test_id": r.test_id,
                    "description": r.description,
                    "status": r.status.value,
                    "node": r.bsg_node_id,
                    "rules": r.business_rule_ids,
                    "error": r.error_message,
                }
                for r in self.results
            ],
            "recommendations": self.recommendations,
        }
