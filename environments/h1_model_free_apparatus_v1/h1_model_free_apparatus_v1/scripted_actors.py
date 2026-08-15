"""Explicit model-free actor programs with hash-linked action outputs."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import stable_hash
from .lifecycle import ActorHandle
from .models import CarrierKind, EventKind, Position
from .provenance import ProvenanceLedger
from .routine import checker_stage, encoder_finalize, encoder_stage


@dataclass(frozen=True)
class StageOutput:
    artifact_id: str
    value: tuple[int, int, int] | int
    content_hash: str
    source_content_hash: str | None = None


class ScriptedActor:
    """A capability-scoped actor; the engine cannot mint actor action edges."""

    def __init__(
        self, handle: ActorHandle, ledger: ProvenanceLedger, case_id: str
    ) -> None:
        self.handle = handle
        self.ledger = ledger
        self.case_id = case_id

    def _emit(
        self,
        *,
        stage: int,
        component: Position,
        value: tuple[int, int, int] | int,
        parent_ids: tuple[str, ...],
        source_content_hash: str | None = None,
    ) -> StageOutput:
        self.handle.assert_active()
        artifact_id = f"{self.case_id}-stage-{stage}"
        content_hash = stable_hash({"stage": stage, "value": value})
        attestation = self.handle.attest_action(
            stage=stage,
            artifact_id=artifact_id,
            content_hash=content_hash,
            component=component.value,
            parent_ids=parent_ids,
        )
        self.ledger.emit(
            EventKind.ACT,
            actor=self.handle,
            carrier=CarrierKind.LOCAL,
            artifact_id=artifact_id,
            content_hash=content_hash,
            component=component,
            dependency_stage=stage,
            parent_ids=parent_ids,
            action=f"actor-produced relay stage {stage}",
            endpoint="held-out-relay",
            action_attestation=attestation,
        )
        return StageOutput(artifact_id, value, content_hash, source_content_hash)

    def encode(self, left: dict, *, left_artifact_id: str) -> StageOutput:
        if "encoder" not in self.handle.position:
            raise ValueError("encode requires the harness-assigned encoder position")
        return self._emit(
            stage=0,
            component=Position.ENCODER,
            value=encoder_stage(left),
            parent_ids=(left_artifact_id,),
            source_content_hash=stable_hash(left),
        )

    def check(
        self,
        right: dict,
        intermediate: StageOutput,
        *,
        right_artifact_id: str,
    ) -> StageOutput:
        if "checker" not in self.handle.position:
            raise ValueError("check requires the harness-assigned checker position")
        if right.get("left_digest") != intermediate.source_content_hash:
            raise ValueError("checker artifact is not bound to encoder source state")
        return self._emit(
            stage=1,
            component=Position.CHECKER,
            value=checker_stage(right, intermediate.value),
            parent_ids=(right_artifact_id, intermediate.artifact_id),
        )

    def finalize(
        self, intermediate: StageOutput, acknowledgment: StageOutput
    ) -> StageOutput:
        if "encoder" not in self.handle.position:
            raise ValueError("finalize requires the harness-assigned encoder position")
        return self._emit(
            stage=2,
            component=Position.ENCODER,
            value=encoder_finalize(intermediate.value, acknowledgment.value),
            parent_ids=(intermediate.artifact_id, acknowledgment.artifact_id),
        )
