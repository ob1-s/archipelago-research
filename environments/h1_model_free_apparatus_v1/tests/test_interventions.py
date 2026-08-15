import pytest

from h1_model_free_apparatus_v1.interventions import recovery_matrix, run_recovery
from h1_model_free_apparatus_v1.models import InterventionKind, RecoveryMode


@pytest.mark.parametrize(
    "intervention",
    [
        InterventionKind.FULL_DELETION,
        InterventionKind.PARTIAL_DELETION,
        InterventionKind.CORRUPTION,
        InterventionKind.RANDOM_REPLACEMENT,
    ],
)
def test_destructive_controls_fail_without_recovery(intervention):
    outcome = run_recovery(intervention)
    assert not outcome.success
    assert outcome.recovery is RecoveryMode.FAILED
    assert outcome.routine_fidelity == 0.0


def test_frozen_backup_restore_is_not_endogenous_reconstruction():
    outcome = run_recovery(InterventionKind.BACKUP_RESTORE)
    assert outcome.success
    assert outcome.recovery is RecoveryMode.BACKUP_RESTORE
    assert outcome.backup_used
    assert "frozen backup" in outcome.artifact_provenance


def test_endogenous_reconstruction_has_new_provenance_and_steps():
    outcome = run_recovery(InterventionKind.ENDOGENOUS_RECONSTRUCTION)
    assert outcome.success
    assert outcome.recovery is RecoveryMode.ENDOGENOUS_RECONSTRUCTION
    assert not outcome.backup_used
    assert outcome.recovery_steps == 2
    assert "successor-authored" in outcome.artifact_provenance


def test_recovery_matrix_is_complete_and_deterministic():
    first = recovery_matrix()
    second = recovery_matrix()
    assert first == second
    assert {item.intervention for item in first} == set(InterventionKind)
