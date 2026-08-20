"""Closed behavioral-call failure taxonomy and safe-retry predicate."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import StrictBool

from constraint_forge_formation_v0.models import StrictModel


class FailureClass(StrEnum):
    LOCAL_PRE_DISPATCH = "local_pre_dispatch"
    PROVIDER_REJECTED_PRE_INFERENCE = "provider_rejected_pre_inference"
    DELIVERY_AMBIGUOUS = "delivery_ambiguous"
    TIMEOUT_AMBIGUOUS = "timeout_ambiguous"
    PARTIAL_RESPONSE = "partial_response"
    PROVIDER_FAILURE_AMBIGUOUS = "provider_failure_ambiguous"


class FailureEvidence(StrictModel):
    failure_class: FailureClass
    request_dispatched: StrictBool
    behavioral_sample_produced: StrictBool | None
    provider_status: str | None = None
    provider_request_id: str | None = None
    detail: str = ""


class BehavioralCallFailure(RuntimeError):
    """An actor call failed with explicit evidence about inference delivery."""

    def __init__(self, evidence: FailureEvidence) -> None:
        super().__init__(evidence.detail or evidence.failure_class.value)
        self.evidence = evidence


def safe_to_retry(evidence: FailureEvidence) -> bool:
    """Return true only for a mechanically proven no-sample failure."""

    return bool(
        evidence.failure_class
        in {
            FailureClass.LOCAL_PRE_DISPATCH,
            FailureClass.PROVIDER_REJECTED_PRE_INFERENCE,
        }
        and evidence.request_dispatched is False
        and evidence.behavioral_sample_produced is False
    )


def ambiguous_failure(detail: str, *, timeout: bool = False) -> BehavioralCallFailure:
    failure_class = FailureClass.TIMEOUT_AMBIGUOUS if timeout else FailureClass.DELIVERY_AMBIGUOUS
    return BehavioralCallFailure(
        FailureEvidence(
            failure_class=failure_class,
            request_dispatched=True,
            behavioral_sample_produced=None,
            detail=detail,
        )
    )


__all__ = [
    "BehavioralCallFailure",
    "FailureClass",
    "FailureEvidence",
    "ambiguous_failure",
    "safe_to_retry",
]
