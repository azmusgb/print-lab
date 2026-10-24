"""A finding from a check or rule: what, where, why it matters and the fix that has worked before."""
from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["blocking", "warning", "info"]
_ORDER = {"blocking": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    rule: str
    severity: Severity
    where: str
    why: str
    fix: str
    data: dict = field(default_factory=dict)


def worst(findings: list[Finding]) -> str | None:
    return min((f.severity for f in findings), key=_ORDER.__getitem__, default=None)
