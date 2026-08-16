import json
from pathlib import Path

import pytest

from h1_live_runtime_adapter_v1.canonical import sha256_bytes, stable_hash
from h1_live_runtime_adapter_v1.models import (
    EvidenceClass,
    ProviderPolicy,
    StateClass,
    StateLayer,
)
from h1_live_runtime_adapter_v1.state_manifest import (
    STATE_LAYER_MANIFEST,
    STATE_LAYER_NAMES,
    common_prior_hashes,
    common_prior_records,
    state_manifest_document,
    validate_state_manifest,
    validate_state_manifest_document,
)


def test_manifest_has_complete_unique_canonical_inventory() -> None:
    assert len(STATE_LAYER_MANIFEST) == 47
    assert len(set(STATE_LAYER_NAMES)) == len(STATE_LAYER_NAMES)
    assert tuple(item.name for item in STATE_LAYER_MANIFEST) == STATE_LAYER_NAMES
    validate_state_manifest()


@pytest.mark.parametrize("layer", STATE_LAYER_MANIFEST, ids=STATE_LAYER_NAMES)
def test_every_layer_is_fully_populated_and_round_trips(layer: StateLayer) -> None:
    data = layer.model_dump(mode="json")
    assert all(value is not None for value in data.values())
    assert all(value != "" for value in data.values() if isinstance(value, str))
    assert StateLayer.model_validate_json(layer.model_dump_json()) == layer


@pytest.mark.parametrize("layer", STATE_LAYER_MANIFEST, ids=STATE_LAYER_NAMES)
def test_any_canonical_layer_semantic_mutation_is_rejected(layer: StateLayer) -> None:
    changed = layer.model_copy(update={"owner": f"mutated:{layer.owner}"})
    layers = tuple(changed if item.name == layer.name else item for item in STATE_LAYER_MANIFEST)
    with pytest.raises(ValueError, match="canonical classification"):
        validate_state_manifest(layers)


def test_manifest_rejects_order_omission_and_duplicates() -> None:
    with pytest.raises(ValueError, match="canonical order"):
        validate_state_manifest(STATE_LAYER_MANIFEST[::-1])
    with pytest.raises(ValueError, match="canonical order"):
        validate_state_manifest(STATE_LAYER_MANIFEST[:-1])
    with pytest.raises(ValueError, match="canonical order"):
        validate_state_manifest((*STATE_LAYER_MANIFEST[:-1], STATE_LAYER_MANIFEST[0]))


def test_provider_opaque_layers_never_enter_common_priors() -> None:
    opaque = {
        item.name
        for item in STATE_LAYER_MANIFEST
        if item.classification is StateClass.PROVIDER_OPAQUE
    }
    assert "model_weights_and_tokenizer" in opaque
    assert "provider_prompt_and_prefix_cache" in opaque
    assert opaque.isdisjoint(common_prior_records())
    assert all(
        item.model_visible in {"unknown", "no"}
        and item.evidence_class
        in {EvidenceClass.OPAQUE_UNVERIFIED, EvidenceClass.DOCUMENTATION_SUPPORTED}
        for item in STATE_LAYER_MANIFEST
        if item.classification is StateClass.PROVIDER_OPAQUE
    )


def test_only_declared_carrier_classes_have_cross_generation_write_read_edges() -> None:
    edges = {
        item.classification
        for item in STATE_LAYER_MANIFEST
        if item.predecessor_write and item.successor_read
    }
    assert edges == {
        StateClass.DECLARED_LINEAGE_CARRIER,
        StateClass.DECLARED_BACKUP,
    }


def test_assignment_is_frozen_but_not_a_common_prior() -> None:
    assignment = next(item for item in STATE_LAYER_MANIFEST if item.name == "current_assignment")
    assert assignment.classification is StateClass.DECLARED_ASSIGNMENT
    assert not assignment.mutable
    assert not assignment.predecessor_write
    assert assignment.successor_read
    assert "current_assignment" not in common_prior_records()


def test_gateway_receipt_key_split_is_explicit() -> None:
    layer = next(
        item
        for item in STATE_LAYER_MANIFEST
        if item.name == "provider_gateway_receipt_private_key"
    )
    assert layer.classification is StateClass.ORCHESTRATOR_ONLY
    assert layer.model_visible == "no"
    assert layer.predecessor_write is False
    assert layer.successor_read is False
    public_pin = next(
        item
        for item in STATE_LAYER_MANIFEST
        if item.name == "gateway_receipt_public_key_pin"
    )
    assert public_pin.classification is StateClass.DECLARED_ASSIGNMENT
    assert public_pin.model_visible == "no"
    assert public_pin.successor_read is True


def test_schedule_receipt_and_plaintext_ledgers_are_explicit() -> None:
    expected = {
        "frozen_schedule_actor_request_and_capability_pins",
        "provider_gateway_receipts",
        "orchestrator_plaintext_response_ledger",
    }
    layers = {item.name: item for item in STATE_LAYER_MANIFEST if item.name in expected}
    assert set(layers) == expected
    assert all(
        item.classification is StateClass.ORCHESTRATOR_ONLY
        and item.model_visible == "no"
        and not item.predecessor_write
        and not item.successor_read
        for item in layers.values()
    )


def test_common_prior_records_hash_exact_sources() -> None:
    records = common_prior_records()
    package = Path(__file__).resolve().parents[1] / "h1_live_runtime_adapter_v1"
    for record in records.values():
        source = record["source"]
        assert record["version"]
        assert len(record["hash"]) == 64
        if not source.startswith(("inline:", "strict:")):
            assert record["hash"] == sha256_bytes((package / source).read_bytes())
    assert common_prior_hashes() == {
        name: record["hash"] for name, record in records.items()
    }


def test_exact_provider_policy_changes_only_policy_common_prior_hash() -> None:
    first = ProviderPolicy(base_url="https://a.invalid/v1", model="model-a")
    second = ProviderPolicy(base_url="https://b.invalid/v1", model="model-b")
    a = common_prior_hashes(first)
    b = common_prior_hashes(second)
    differing = {key for key in a if a[key] != b[key]}
    assert differing == {"provider_policy"}


def test_document_json_round_trip_and_self_hash() -> None:
    policy = ProviderPolicy(base_url="https://provider.invalid/v1", model="pinned")
    document = state_manifest_document(policy)
    restored = json.loads(json.dumps(document))
    validate_state_manifest_document(restored, policy)
    unsigned = {key: value for key, value in restored.items() if key != "manifest_hash"}
    assert restored["manifest_hash"] == stable_hash(unsigned)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(layer_count=0),
        lambda d: d.update(manifest_version="wrong"),
        lambda d: d.update(common_prior_version="wrong"),
        lambda d: d.update(manifest_hash="0" * 64),
        lambda d: d["common_priors"].pop("provider_policy"),
        lambda d: d["layers"].pop(),
        lambda d: d.update(extra="forbidden"),
    ],
)
def test_document_tampering_fails_closed(mutation) -> None:
    document = json.loads(json.dumps(state_manifest_document()))
    mutation(document)
    with pytest.raises(ValueError):
        validate_state_manifest_document(document)
