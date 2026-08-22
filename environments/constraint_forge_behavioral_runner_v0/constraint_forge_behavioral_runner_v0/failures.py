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
    INFRASTRUCTURE_UNDELIVERED = "infrastructure_undelivered"


# Explicit gateway/transport statuses that carry no delivered response body for
# the behavioral boundary. Declared prospectively for cohort v1: stateless
# inference means an unseen generation changed no world state, so replacing the
# missing observation with an identical re-request is not selection bias.
RETRYABLE_INFRA_STATUSES = frozenset({429, 500, 502, 503, 504})


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


def infrastructure_failure(status_code: int) -> BehavioralCallFailure:
    """An explicit infrastructure status arrived with no delivered response.

    Mechanically provable from the native call: the provider returned an
    explicit error status and no completion (finish_reason is None), so no
    behavioral content was received. The identical request may be re-dispatched
    under the declared cohort retry budget.
    """

    return BehavioralCallFailure(
        FailureEvidence(
            failure_class=FailureClass.INFRASTRUCTURE_UNDELIVERED,
            request_dispatched=True,
            behavioral_sample_produced=False,
            provider_status=str(status_code),
            detail=f"provider returned explicit infrastructure status {status_code}",
        )
    )


def native_error_status(call) -> int | None:
    """The explicit HTTP status carried by a failed native provider call."""

    error = getattr(call, "error", None)
    if error is None:
        return None
    payload = (
        error.model_dump(mode="json", exclude_none=True)
        if hasattr(error, "model_dump")
        else {}
    )
    status = payload.get("status_code")
    return int(status) if isinstance(status, int) else None


def retryable_infrastructure(evidence: FailureEvidence) -> bool:
    """True only for an explicit infra status with provably no sample."""

    return bool(
        evidence.failure_class is FailureClass.INFRASTRUCTURE_UNDELIVERED
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
    "RETRYABLE_INFRA_STATUSES",
    "ambiguous_failure",
    "infrastructure_failure",
    "native_error_status",
    "retryable_infrastructure",
    "safe_to_retry",
]
