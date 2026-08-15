import pytest

from h1_model_free_apparatus_v1.canonical import stable_hash
from h1_model_free_apparatus_v1.lifecycle import LifecycleRegistry
from h1_model_free_apparatus_v1.models import (
    ArtifactRecord,
    CarrierKind,
    EventKind,
    Position,
    StateVariant,
)
from h1_model_free_apparatus_v1.provenance import ProvenanceError, ProvenanceLedger


def valid_ledger():
    registry = LifecycleRegistry("p")
    ledger = ProvenanceLedger("p")
    actor = registry.spawn(lineage_id="l", generation=0, position="encoder")
    ledger.emit(
        EventKind.SPAWN,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        authority=actor.write_authority_id,
    )
    payload_hash = stable_hash({"x": 1})
    ledger.emit(
        EventKind.WRITE,
        actor=actor,
        carrier=CarrierKind.DECLARED,
        artifact_id="a",
        content_hash=payload_hash,
        component=Position.ENCODER,
        authority=actor.write_authority_id,
        action="write",
    )
    ledger.emit(
        EventKind.READ,
        actor=actor,
        carrier=CarrierKind.DECLARED,
        artifact_id="a",
        content_hash=payload_hash,
        component=Position.ENCODER,
        action="read",
    )
    return ledger


def test_valid_graph_has_complete_inventory():
    result = valid_ledger().validate(strict=True)
    assert result.valid
    assert result.inventory_complete
    assert result.observed_writes == ("a",)
    assert result.observed_reads == ("a",)


def test_hash_tamper_fails():
    ledger = valid_ledger()
    ledger.replace_event_for_test(1, content_hash="f" * 64)
    result = ledger.validate()
    assert not result.valid
    assert any("invalid event hash" in error for error in result.errors)


def test_missing_event_fails_closed():
    ledger = valid_ledger()
    ledger.drop_event_for_test(1)
    result = ledger.validate()
    assert not result.valid
    assert any("read before known write" in error for error in result.errors)


def test_required_event_missing_is_invalid():
    result = valid_ledger().validate(required_events=(EventKind.TERMINATE,))
    assert not result.valid
    assert "missing required event terminate" in result.errors


def test_strict_validation_raises():
    ledger = valid_ledger()
    ledger.drop_event_for_test(1)
    with pytest.raises(ProvenanceError):
        ledger.validate(strict=True)


def test_read_hash_mismatch_fails():
    ledger = valid_ledger()
    ledger.replace_event_for_test(2, content_hash="1" * 64)
    result = ledger.validate()
    assert not result.valid
    assert any("read content hash mismatch" in error for error in result.errors)


def test_expected_predecessor_termination_and_revocation_are_required():
    ledger = valid_ledger()
    result = ledger.validate(
        expected_terminated_lifecycles=("life-p-g0-encoder-1",),
        expected_revoked_authorities=("write-p-g0-encoder-1",),
    )
    assert not result.valid
    assert any("still active" in error for error in result.errors)
    assert any("missing predecessor termination" in error for error in result.errors)
    assert any(
        "missing predecessor authority revocation" in error for error in result.errors
    )


def test_artifact_attribution_is_checked_against_actual_writer_edge():
    ledger = valid_ledger()
    record = ArtifactRecord(
        artifact_id="a",
        carrier=CarrierKind.DECLARED,
        component=Position.ENCODER,
        variant=StateVariant.A,
        payload={"x": 1},
        content_hash=stable_hash({"x": 1}),
        authors=("wrong-actor",),
        lineage_ids=("l",),
    )
    result = ledger.validate(artifact_records=(record,))
    assert not result.valid
    assert any("attribution disagrees" in error for error in result.errors)


def test_duplicate_artifact_write_is_invalid():
    registry = LifecycleRegistry("duplicate")
    actor = registry.spawn(lineage_id="l", generation=0, position="encoder")
    ledger = ProvenanceLedger("duplicate")
    ledger.emit(
        EventKind.SPAWN,
        actor=actor,
        carrier=CarrierKind.LOCAL,
        authority=actor.write_authority_id,
    )
    for _ in range(2):
        ledger.emit(
            EventKind.WRITE,
            actor=actor,
            carrier=CarrierKind.DECLARED,
            artifact_id="same",
            content_hash=stable_hash({"x": 1}),
            component=Position.ENCODER,
            authority=actor.write_authority_id,
            action="duplicate write",
        )
    result = ledger.validate()
    assert not result.valid
    assert any("duplicate artifact write" in error for error in result.errors)
