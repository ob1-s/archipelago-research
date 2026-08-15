"""Known-ground-truth state interventions and recovery classifications."""

from __future__ import annotations

from .models import InterventionKind, RecoveryMode, RecoveryOutcome, StateVariant
from .routine import artifact_payloads, execute_relay, perturb_payload


def run_recovery(intervention: InterventionKind) -> RecoveryOutcome:
    left, right = artifact_payloads(StateVariant.A)
    backup = (dict(left), dict(right))
    working_left: dict | None = dict(left)
    working_right: dict | None = dict(right)
    recovery = RecoveryMode.NONE
    steps = 0
    provenance = "predecessor-authored declared carrier"
    backup_used = False
    rediscovery = False

    if intervention is InterventionKind.FULL_DELETION:
        working_left = working_right = None
        provenance = "deleted; no recovery"
    elif intervention is InterventionKind.PARTIAL_DELETION:
        working_right = None
        provenance = "right component deleted; no recovery"
    elif intervention is InterventionKind.CORRUPTION:
        working_right = perturb_payload(working_right)
        provenance = "corrupted carrier"
    elif intervention is InterventionKind.RANDOM_REPLACEMENT:
        working_left = {"schema": "random/v1", "bytes": [91, 7, 44]}
        working_right = {"schema": "random/v1", "bytes": [3, 70, 2]}
        provenance = "deterministic random replacement control"
    elif intervention is InterventionKind.BACKUP_RESTORE:
        working_left = working_right = None
        working_left, working_right = backup
        recovery = RecoveryMode.BACKUP_RESTORE
        steps = 1
        provenance = "byte-identical frozen backup"
        backup_used = True
    elif intervention is InterventionKind.ENDOGENOUS_RECONSTRUCTION:
        working_left = working_right = None
        # A declared recovery seed contains calibration facts, not either final artifact.
        recovery_seed = StateVariant.A
        working_left, working_right = artifact_payloads(recovery_seed)
        recovery = RecoveryMode.ENDOGENOUS_RECONSTRUCTION
        steps = 2
        provenance = "successor-authored transformation from declared recovery seed"

    success = False
    fidelity = 0.0
    if working_left is not None and working_right is not None:
        try:
            run = execute_relay(
                working_left,
                working_right,
                encoder_actor="recovery-encoder",
                checker_actor="recovery-checker",
            )
        except (KeyError, TypeError, ValueError):
            success = False
        else:
            success = (
                run.output
                == execute_relay(
                    left,
                    right,
                    encoder_actor="expected-encoder",
                    checker_actor="expected-checker",
                ).output
            )
            fidelity = run.fidelity if success else 0.0

    if (
        intervention
        in {
            InterventionKind.FULL_DELETION,
            InterventionKind.PARTIAL_DELETION,
            InterventionKind.CORRUPTION,
            InterventionKind.RANDOM_REPLACEMENT,
        }
        and not success
    ):
        recovery = RecoveryMode.FAILED

    return RecoveryOutcome(
        intervention=intervention,
        success=success,
        recovery=recovery,
        recovery_steps=steps,
        routine_fidelity=fidelity,
        artifact_provenance=provenance,
        backup_used=backup_used,
        rediscovery=rediscovery,
    )


def recovery_matrix() -> tuple[RecoveryOutcome, ...]:
    return tuple(run_recovery(intervention) for intervention in InterventionKind)
