"""Mechanical qualification of the narrow declared-carrier API.

The carrier is the one intentional cross-generation surface in this package.
These tests deliberately create signed actions with a test-only Ed25519 key;
the production actor keeps its private key inside the isolated process and
the controller's :class:`ActionRegistry` stores public identities only.
No provider or model call is made here.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import os
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import HealthCheck, given, settings, strategies as st

from h1_live_runtime_adapter_v1.attribution import ActionRegistry
from h1_live_runtime_adapter_v1.canonical import canonical_bytes, sha256_bytes
from h1_live_runtime_adapter_v1.carrier import (
    ALLOWED_CARRIER_CLASSES,
    CarrierCapability,
    DeclaredCarrierStore,
    carrier_read_binding,
    carrier_write_binding,
)
from h1_live_runtime_adapter_v1.models import ActorIdentity, SignedAction, StateClass


ACTION_DOMAIN = b"h1-live-runtime-action/v1\0"


def _unbound_store(*args, **kwargs) -> DeclaredCarrierStore:
    """Explicitly opt unit tests into the non-schedule actor-provenance store."""

    return DeclaredCarrierStore(
        *args,
        **kwargs,
        capabilities=None,
        allow_unbound_for_testing=True,
    )


@dataclass
class _Actor:
    """Small test-only actor signer with a public registry entry."""

    registry: ActionRegistry
    actor_id: str
    lifecycle_id: str
    session_id: str
    lineage_id: str
    generation: int
    private_key: Ed25519PrivateKey
    sequence: int = 0
    identity: ActorIdentity = field(init=False)

    def __post_init__(self) -> None:
        public_key_b64 = base64.b64encode(
            self.private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode()
        identity = ActorIdentity(
            actor_id=self.actor_id,
            lifecycle_id=self.lifecycle_id,
            generation=self.generation,
            lineage_id=self.lineage_id,
            position="carrier-test",
            session_id=self.session_id,
            public_key_b64=public_key_b64,
            registration_signature_b64="",
            namespace_pid=1,
            namespace_process_start_ticks=1,
            environment_fingerprint="test-environment",
            environment_names=(),
            namespace_ids={},
            effective_capabilities_hex="0",
            no_new_privileges=True,
            open_extra_fd_count=0,
            open_extra_fd_targets={},
        )
        registration = identity.model_dump(
            exclude={"registration_signature_b64"}, mode="json"
        )
        self.identity = identity.model_copy(
            update={
                "registration_signature_b64": base64.b64encode(
                    self.private_key.sign(
                        b"h1-live-runtime-registration/v1\0"
                        + canonical_bytes(registration)
                    )
                ).decode()
            }
        )
        self.registry.register(self.identity)

    @property
    def public_key_b64(self) -> str:
        return self.identity.public_key_b64

    def sign(
        self,
        action: str,
        payload_hash: str,
        *,
        parent_hashes: tuple[str, ...] = (),
        generation: int | None = None,
        lineage_id: str | None = None,
    ) -> SignedAction:
        self.sequence += 1
        unsigned = {
            "actor_id": self.actor_id,
            "lifecycle_id": self.lifecycle_id,
            "session_id": self.session_id,
            "generation": self.generation if generation is None else generation,
            "lineage_id": self.lineage_id if lineage_id is None else lineage_id,
            "public_key_b64": self.public_key_b64,
            "sequence": self.sequence,
            "action_id": f"{self.lifecycle_id}:{self.sequence}",
            "action": action,
            "payload_hash": payload_hash,
            "parent_hashes": list(parent_hashes),
        }
        signature = base64.b64encode(
            self.private_key.sign(ACTION_DOMAIN + canonical_bytes(unsigned))
        ).decode()
        return SignedAction(**unsigned, signature_b64=signature)


def _actor(
    registry: ActionRegistry | None = None,
    *,
    lineage_id: str = "lineage-a",
    generation: int = 0,
) -> _Actor:
    registry = registry or ActionRegistry()
    suffix = uuid4().hex
    return _Actor(
        registry=registry,
        actor_id=f"actor-{suffix}",
        lifecycle_id=f"lifecycle-{suffix}",
        session_id=f"session-{suffix}",
        lineage_id=lineage_id,
        generation=generation,
        private_key=Ed25519PrivateKey.generate(),
    )


def _write_action(
    actor: _Actor,
    content: bytes,
    *,
    carrier_id: str = "carrier-a",
    carrier_class: StateClass = StateClass.DECLARED_LINEAGE_CARRIER,
    parent_hashes: tuple[str, ...] = (),
    action: str = "carrier_write",
) -> SignedAction:
    signed_parents = parent_hashes
    if action == "carrier_write":
        binding = carrier_write_binding(
            carrier_id=carrier_id,
            carrier_class=carrier_class,
            lineage_id=actor.lineage_id,
            generation=actor.generation,
            content_hash=sha256_bytes(content),
            parent_hashes=parent_hashes,
        )
        signed_parents = (*parent_hashes, binding)
    return actor.sign(
        action,
        sha256_bytes(content),
        parent_hashes=signed_parents,
    )


def _store_and_draft(
    tmp_path: Path,
    *,
    carrier_id: str = "carrier-a",
    content: bytes = b"declared-carrier-content",
    actor: _Actor | None = None,
    carrier_class: StateClass = StateClass.DECLARED_LINEAGE_CARRIER,
    parent_hashes: tuple[str, ...] = (),
) -> tuple[DeclaredCarrierStore, _Actor, SignedAction, bytes]:
    actor = actor or _actor()
    store = _unbound_store(actor.registry, root=tmp_path / "carrier-root")
    action = _write_action(
        actor,
        content,
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        parent_hashes=parent_hashes,
    )
    store.write(
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        content=content,
        writer=action,
        parent_hashes=parent_hashes,
    )
    return store, actor, action, content


@pytest.mark.parametrize(
    "carrier_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "nested/child",
        "/absolute",
        "C:\\escape",
        "a%2Fsecret",
        "a\\b",
        "a" * 129,
        "-leading",
        "_leading",
    ],
)
def test_carrier_id_is_opaque_and_cannot_escape_root(
    tmp_path: Path, carrier_id: str
) -> None:
    store, actor, _action, content = _store_and_draft(tmp_path)
    root = store.root
    with pytest.raises(ValueError, match="safe opaque identifier"):
        store.write(
            carrier_id=carrier_id,
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=_write_action(actor, content),
        )
    assert root.exists()
    assert not (tmp_path / "escape.carrier").exists()
    store.close()


def test_caller_root_symlink_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="real directory"):
        _unbound_store(ActionRegistry(), root=linked_root)
    assert tuple(real_root.iterdir()) == ()


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(
    left=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="-_",
        ),
        max_size=12,
    ),
    separator=st.sampled_from(("/", "\\")),
    right=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="-_",
        ),
        max_size=12,
    ),
)
def test_property_any_path_separator_is_rejected_without_root_escape(
    tmp_path: Path, left: str, separator: str, right: str
) -> None:
    actor = _actor()
    root = tmp_path / f"property-{uuid4().hex}"
    store = _unbound_store(actor.registry, root=root)
    content = b"property-content"
    carrier_id = f"{left}{separator}{right}"
    with pytest.raises(ValueError, match="safe opaque identifier"):
        store.write(
            carrier_id=carrier_id,
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=_write_action(actor, content),
        )
    assert tuple(root.iterdir()) == ()
    store.close()


@pytest.mark.parametrize(
    "carrier_class",
    [
        StateClass.DECLARED_LINEAGE_CARRIER,
        StateClass.DECLARED_BACKUP,
    ],
)
def test_only_declared_carrier_classes_are_accepted(
    tmp_path: Path, carrier_class: StateClass
) -> None:
    assert ALLOWED_CARRIER_CLASSES == frozenset(
        {StateClass.DECLARED_LINEAGE_CARRIER, StateClass.DECLARED_BACKUP}
    )
    store, actor, _action, content = _store_and_draft(
        tmp_path,
        carrier_id=f"allowed-{carrier_class.name.lower()}",
        carrier_class=carrier_class,
    )
    record = store.finalize_and_hash(next(iter(store._drafts)))
    assert record.carrier_class is carrier_class
    store.close()


@pytest.mark.parametrize(
    "carrier_class",
    [
        StateClass.TRANSIENT_ACTOR_STATE,
        StateClass.IMMUTABLE_COMMON_PRIOR,
        StateClass.DECLARED_ASSIGNMENT,
        StateClass.ORCHESTRATOR_ONLY,
        StateClass.PROVIDER_OPAQUE,
        StateClass.FORBIDDEN,
    ],
)
def test_undeclared_state_classes_cannot_be_carriers(
    tmp_path: Path, carrier_class: StateClass
) -> None:
    store, actor, _action, content = _store_and_draft(tmp_path)
    with pytest.raises(ValueError, match="carrier class"):
        store.write(
            carrier_id=f"forbidden-{carrier_class.name.lower()}",
            carrier_class=carrier_class,
            content=content,
            writer=_write_action(actor, content),
        )
    store.close()


def test_writer_signature_payload_and_registry_authority_are_required(
    tmp_path: Path,
) -> None:
    registry = ActionRegistry()
    writer = _actor(registry)
    other = _actor()
    content = b"signed-content"
    store = _unbound_store(registry, root=tmp_path / "root")

    forged_signature = _write_action(
        writer, content, carrier_id="forged-signature"
    ).model_copy(
        update={"signature_b64": base64.b64encode(b"forged").decode()}
    )
    with pytest.raises(ValueError, match="signature/authority"):
        store.write(
            carrier_id="forged-signature",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=forged_signature,
        )

    wrong_payload = _write_action(
        writer, content, carrier_id="wrong-payload"
    ).model_copy(
        update={"payload_hash": sha256_bytes(b"different")}
    )
    with pytest.raises(ValueError, match="action/hash"):
        store.write(
            carrier_id="wrong-payload",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=wrong_payload,
        )

    foreign_writer = _write_action(other, content, carrier_id="foreign-writer")
    with pytest.raises(ValueError, match="signature/authority"):
        store.write(
            carrier_id="foreign-writer",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=foreign_writer,
        )

    revoked = _actor(registry)
    registry.revoke(revoked.lifecycle_id)
    with pytest.raises(ValueError, match="signature/authority"):
        store.write(
            carrier_id="revoked-writer",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=_write_action(revoked, content, carrier_id="revoked-writer"),
        )
    store.close()


def test_reader_authority_lineage_generation_and_parentage_are_verified(
    tmp_path: Path,
) -> None:
    registry = ActionRegistry()
    writer = _actor(registry, lineage_id="lineage-a", generation=0)
    successor = _actor(registry, lineage_id="lineage-a", generation=1)
    bad_parent_reader = _actor(registry, lineage_id="lineage-a", generation=1)
    wrong_lineage = _actor(registry, lineage_id="lineage-b", generation=1)
    old_generation = _actor(registry, lineage_id="lineage-a", generation=0)
    content = b"lineage-bound"
    parent_hash = sha256_bytes(b"parent")
    store = _unbound_store(registry, root=tmp_path / "root")
    write_action = _write_action(
        writer,
        content,
        carrier_id="lineage-bound",
        parent_hashes=(parent_hash,),
    )
    store.write(
        carrier_id="lineage-bound",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=write_action,
        parent_hashes=(parent_hash,),
    )
    record = store.finalize_and_hash("lineage-bound")
    assert record.generation == 0
    assert record.parent_hashes == (parent_hash,)

    with pytest.raises(ValueError, match="cross-lineage"):
        store.read("lineage-bound", lineage_id="lineage-b")

    bad_parent = bad_parent_reader.sign(
        "carrier_read",
        record.content_hash,
        parent_hashes=(sha256_bytes(b"unrelated"),),
    )
    with pytest.raises(ValueError, match="provenance"):
        store.record_read("lineage-bound", bad_parent)

    wrong_lineage_reader = wrong_lineage.sign(
        "carrier_read",
        record.content_hash,
        parent_hashes=(record.content_hash, carrier_read_binding(record)),
    )
    with pytest.raises(ValueError, match="provenance"):
        store.record_read("lineage-bound", wrong_lineage_reader)

    old_reader = old_generation.sign(
        "carrier_read",
        record.content_hash,
        parent_hashes=(record.content_hash, carrier_read_binding(record)),
    )
    with pytest.raises(ValueError, match="provenance"):
        store.record_read("lineage-bound", old_reader)

    good_reader = successor.sign(
        "carrier_read",
        record.content_hash,
        parent_hashes=(record.content_hash, carrier_read_binding(record)),
    )
    updated = store.record_read("lineage-bound", good_reader)
    assert updated.read_by == (successor.actor_id,)
    store.close()


def test_finalize_hash_and_provenance_are_durable(tmp_path: Path) -> None:
    store, actor, action, content = _store_and_draft(
        tmp_path,
        carrier_id="durable-record",
        content=b"durable bytes",
        carrier_class=StateClass.DECLARED_BACKUP,
        parent_hashes=("a" * 64,),
    )
    record = store.finalize_and_hash("durable-record")
    assert record.finalized is True
    assert record.content_hash == sha256_bytes(content)
    assert record.writer == action
    assert record.logical_time == 1
    assert record.write_authority
    provenance = store.provenance("durable-record")
    assert provenance == {
        "who": actor.actor_id,
        "what": "durable-record",
        "when": 1,
        "generation": 0,
        "lineage": actor.lineage_id,
        "hash": sha256_bytes(content),
        "write_authority": record.write_authority,
        "read_by": [],
        "parentage": ["a" * 64],
        "carrier_class": StateClass.DECLARED_BACKUP,
    }
    store.close()


def test_same_hash_duplicate_write_is_idempotent_across_finalization(
    tmp_path: Path,
) -> None:
    actor = _actor()
    root = tmp_path / "root"
    store = _unbound_store(actor.registry, root=root)
    content = b"idempotent"
    first = _write_action(actor, content, carrier_id="same-content")
    draft = store.write(
        carrier_id="same-content",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=first,
    )
    # A transport retry may replay the exact same signed write after the
    # registry sequence was consumed; it must remain idempotent.
    assert (
        store.write(
            carrier_id="same-content",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=first,
        )
        is draft
    )
    duplicate_draft = store.write(
        carrier_id="same-content",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="same-content"),
    )
    assert duplicate_draft is draft
    record = store.finalize_and_hash("same-content")
    duplicate_record = store.write(
        carrier_id="same-content",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="same-content"),
    )
    assert duplicate_record == record
    assert store.finalize_and_hash("same-content") == record
    store.close()


def test_different_content_or_provenance_cannot_reuse_identifier(
    tmp_path: Path,
) -> None:
    actor = _actor()
    store = _unbound_store(actor.registry, root=tmp_path / "root")
    content = b"original"
    store.write(
        carrier_id="collision",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="collision"),
    )
    with pytest.raises(ValueError, match="before finalization"):
        store.write(
            carrier_id="collision",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=b"changed",
            writer=_write_action(actor, b"changed", carrier_id="collision"),
        )
    store.finalize_and_hash("collision")
    with pytest.raises(ValueError, match="different content/provenance"):
        store.write(
            carrier_id="collision",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=b"changed",
            writer=_write_action(actor, b"changed", carrier_id="collision"),
        )
    store.close()


def test_content_tamper_and_metadata_hash_tamper_fail_closed(tmp_path: Path) -> None:
    store, _actor_value, _action, content = _store_and_draft(
        tmp_path, carrier_id="tampered"
    )
    record = store.finalize_and_hash("tampered")
    content_path = store.root / "tampered.carrier"
    content_path.write_bytes(content + b"tampered")
    with pytest.raises(ValueError, match="durable hash"):
        store.read("tampered", lineage_id=record.lineage_id)
    store.close()

    # Restoring the content allows us to isolate the record metadata check.
    content_path.write_bytes(content)
    record_path = tmp_path / "carrier-root" / "tampered.record.json"
    record_path.write_text(record.model_copy(update={"content_hash": "0" * 64}).model_dump_json())
    with pytest.raises(ValueError, match="durable write provenance|hash mismatch"):
        _unbound_store(_actor().registry, root=tmp_path / "carrier-root")


def test_durable_reopen_and_orphan_crash_window_recovery(tmp_path: Path) -> None:
    root = tmp_path / "root"
    actor = _actor()
    content = b"crash-window-content"
    first = _unbound_store(actor.registry, root=root)
    first.write(
        carrier_id="recoverable",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="recoverable"),
    )
    # Simulate a crash after content fsync but before record publication.
    (root / "recoverable.carrier").write_bytes(content)
    first.close()

    recovered = _unbound_store(actor.registry, root=root)
    assert recovered.enumerate() == ()
    recovered.write(
        carrier_id="recoverable",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="recoverable"),
    )
    recovered_record = recovered.finalize_and_hash("recoverable")
    assert recovered_record.content_hash == sha256_bytes(content)
    recovered.close()

    reopened = _unbound_store(actor.registry, root=root)
    record, read_content = reopened.read("recoverable", lineage_id=actor.lineage_id)
    assert record == recovered_record
    assert read_content == content
    reopened.close()
    assert root.exists(), "caller-owned roots must never be removed by close()"
    assert (root / "recoverable.carrier").exists()


def test_orphan_carrier_with_conflicting_content_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    actor = _actor()
    store = _unbound_store(actor.registry, root=root)
    (root / "orphan.carrier").write_bytes(b"unexpected-existing-content")
    with pytest.raises(ValueError, match="orphan carrier identifier"):
        store.write(
            carrier_id="orphan",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=b"intended-content",
            writer=_write_action(actor, b"intended-content", carrier_id="orphan"),
        )
    store.close()


def test_write_binding_covers_identifier_class_and_parent_set(tmp_path: Path) -> None:
    actor = _actor()
    store = _unbound_store(actor.registry, root=tmp_path / "root")
    content = b"binding-contract"
    parent = sha256_bytes(b"declared-parent")
    action = _write_action(
        actor,
        content,
        carrier_id="bound",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        parent_hashes=(parent,),
    )
    with pytest.raises(ValueError, match="complete ID/provenance binding"):
        store.write(
            carrier_id="different-id",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=action,
            parent_hashes=(parent,),
        )

    with pytest.raises(ValueError, match="complete ID/provenance binding"):
        store.write(
            carrier_id="bound",
            carrier_class=StateClass.DECLARED_BACKUP,
            content=content,
            writer=action,
            parent_hashes=(parent,),
        )

    with pytest.raises(ValueError, match="complete ID/provenance binding"):
        store.write(
            carrier_id="bound",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=action,
            parent_hashes=(sha256_bytes(b"different-parent"),),
        )
    store.close()


def test_parent_hashes_require_lowercase_sha256_and_no_duplicates(
    tmp_path: Path,
) -> None:
    actor = _actor()
    store = _unbound_store(actor.registry, root=tmp_path / "root")
    content = b"canonical-parent-hashes"
    uppercase_parent = "A" * 64
    with pytest.raises(ValueError):
        store.write(
            carrier_id="uppercase-parent",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=actor.sign(
                "carrier_write",
                sha256_bytes(content),
                parent_hashes=(uppercase_parent,),
            ),
            parent_hashes=(uppercase_parent,),
        )

    parent = sha256_bytes(b"one-parent")
    with pytest.raises(ValueError, match="unique"):
        store.write(
            carrier_id="duplicate-parent",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=actor.sign(
                "carrier_write",
                sha256_bytes(content),
                parent_hashes=(parent, parent),
            ),
            parent_hashes=(parent, parent),
        )
    store.close()


@pytest.mark.parametrize("artifact_suffix", [".carrier", ".record.json"])
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_published_artifacts_reject_symlink_and_hardlink_aliases(
    tmp_path: Path, artifact_suffix: str, link_kind: str
) -> None:
    store, _actor_value, _action, content = _store_and_draft(
        tmp_path, carrier_id="link-checked"
    )
    record = store.finalize_and_hash("link-checked")
    source = store.root / f"link-checked{artifact_suffix}"
    alias = tmp_path / f"outside-{uuid4().hex}{artifact_suffix}"
    if link_kind == "symlink":
        alias.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(alias)
    else:
        # Replacing the published path with a hard link also exercises the
        # nlink check even when the bytes and metadata remain valid.
        backup = tmp_path / f"hardlink-source-{uuid4().hex}{artifact_suffix}"
        os.link(source, backup)
        source.unlink()
        os.link(backup, source)
    with pytest.raises(ValueError, match="symlink|hard link"):
        _unbound_store(_actor().registry, root=store.root)
    if link_kind == "hardlink":
        # The hard-link setup above intentionally needs a real source file;
        # keep the assertion explicit for readers of this adversarial test.
        assert source.exists()
    store.close()


def test_carrier_content_path_hardlink_is_rejected_on_read(tmp_path: Path) -> None:
    store, _actor_value, _action, content = _store_and_draft(
        tmp_path, carrier_id="content-hardlink"
    )
    record = store.finalize_and_hash("content-hardlink")
    alias = tmp_path / "content-outside"
    os.link(store.root / "content-hardlink.carrier", alias)
    with pytest.raises(ValueError, match="hard link"):
        store.read("content-hardlink", lineage_id=record.lineage_id)
    store.close()


def test_concurrent_finalization_is_single_writer_and_reopenable(tmp_path: Path) -> None:
    registry = ActionRegistry()
    actor = _actor(registry)
    root = tmp_path / "root"
    first = _unbound_store(registry, root=root)
    second = _unbound_store(registry, root=root)
    content = b"concurrent-finalization"
    first.write(
        carrier_id="concurrent",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="concurrent"),
    )
    # The second store has a distinct draft but the same actor-authored
    # contract.  Both finalizers must converge on one durable record.
    second.write(
        carrier_id="concurrent",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(actor, content, carrier_id="concurrent"),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(
            pool.map(
                lambda store_value: store_value.finalize_and_hash("concurrent"),
                (first, second),
            )
        )
    assert records[0] == records[1]
    reopened = _unbound_store(registry, root=root)
    assert reopened.enumerate() == (records[0],)
    reopened.close()
    first.close()
    second.close()


def test_concurrent_read_attribution_does_not_lose_actions(tmp_path: Path) -> None:
    registry = ActionRegistry()
    writer = _actor(registry, lineage_id="lineage-a", generation=0)
    reader_one = _actor(registry, lineage_id="lineage-a", generation=1)
    reader_two = _actor(registry, lineage_id="lineage-a", generation=1)
    root = tmp_path / "root"
    first = _unbound_store(registry, root=root)
    second = _unbound_store(registry, root=root)
    content = b"concurrent-read-attribution"
    first.write(
        carrier_id="read-race",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=_write_action(writer, content, carrier_id="read-race"),
    )
    record = first.finalize_and_hash("read-race")
    binding = carrier_read_binding(record)
    actions = (
        reader_one.sign(
            "carrier_read",
            record.content_hash,
            parent_hashes=(record.content_hash, binding),
        ),
        reader_two.sign(
            "carrier_read",
            record.content_hash,
            parent_hashes=(record.content_hash, binding),
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda args: args[0].record_read("read-race", args[1]),
                ((first, actions[0]), (second, actions[1])),
            )
        )
    reopened = _unbound_store(registry, root=root)
    persisted, _ = reopened.read("read-race", lineage_id="lineage-a")
    assert set(persisted.read_by) == {reader_one.actor_id, reader_two.actor_id}
    assert {action.actor_id for action in persisted.read_actions} == {
        reader_one.actor_id,
        reader_two.actor_id,
    }
    reopened.close()
    first.close()
    second.close()


def test_bound_capabilities_scope_every_carrier_path_and_recipient(
    tmp_path: Path,
) -> None:
    registry = ActionRegistry()
    writer = _actor(registry, lineage_id="lineage-cap", generation=0)
    reader = _actor(registry, lineage_id="lineage-cap", generation=1)
    foreign = _actor(registry, lineage_id="lineage-cap", generation=1)
    content = b"capability-scoped-bytes"
    writer_capability = CarrierCapability.from_fields(
        attempt_id="attempt-writer",
        actor_id=writer.actor_id,
        lifecycle_id=writer.lifecycle_id,
        lineage_id=writer.lineage_id,
        generation=writer.generation,
        carrier_id="capability-carrier",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        can_write=True,
    )
    reader_capability = CarrierCapability.from_fields(
        attempt_id="attempt-reader",
        actor_id=reader.actor_id,
        lifecycle_id=reader.lifecycle_id,
        lineage_id=reader.lineage_id,
        generation=reader.generation,
        carrier_id="capability-carrier",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        can_read=True,
    )
    foreign_capability = CarrierCapability.from_fields(
        attempt_id="attempt-foreign",
        actor_id=foreign.actor_id,
        lifecycle_id=foreign.lifecycle_id,
        lineage_id=foreign.lineage_id,
        generation=foreign.generation,
        carrier_id="capability-carrier",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        can_read=True,
    )
    store = DeclaredCarrierStore(
        registry,
        root=tmp_path / "strict-root",
        capabilities=(writer_capability, reader_capability),
    )
    write_action = _write_action(
        writer, content, carrier_id="capability-carrier"
    )
    with pytest.raises(ValueError, match="capability"):
        store.write(
            carrier_id="capability-carrier",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
            content=content,
            writer=write_action,
        )
    store.write(
        carrier_id="capability-carrier",
        carrier_class=StateClass.DECLARED_LINEAGE_CARRIER,
        content=content,
        writer=write_action,
        capability=writer_capability,
    )
    with pytest.raises(ValueError, match="capability"):
        store.finalize_and_hash("capability-carrier")
    record = store.finalize_and_hash(
        "capability-carrier", capability=writer_capability
    )
    with pytest.raises(ValueError, match="recipient"):
        store.read("capability-carrier", capability=reader_capability)
    with pytest.raises(ValueError, match="not in the frozen"):
        store.read(
            "capability-carrier",
            capability=foreign_capability,
            recipient=foreign.identity,
        )
    stored, returned = store.read(
        "capability-carrier",
        capability=reader_capability,
        recipient=reader.identity,
    )
    assert stored == record
    assert returned == content
    read_action = reader.sign(
        "carrier_read",
        record.content_hash,
        parent_hashes=(record.content_hash, carrier_read_binding(record)),
    )
    updated = store.record_read(
        "capability-carrier", read_action, capability=reader_capability
    )
    assert updated.read_by == (reader.actor_id,)
    assert record.write_capability_hash == writer_capability.capability_hash
    assert updated.read_capability_hashes == (reader_capability.capability_hash,)
    store.close()


def test_bound_reopen_rejects_carrier_from_unscheduled_writer_before_read(
    tmp_path: Path,
) -> None:
    registry = ActionRegistry()
    scheduled_writer = _actor(registry, lineage_id="lineage-cap", generation=0)
    persisted_writer = _actor(registry, lineage_id="lineage-cap", generation=0)
    reader = _actor(registry, lineage_id="lineage-cap", generation=1)
    carrier_id = "restart-authority"
    carrier_class = StateClass.DECLARED_LINEAGE_CARRIER
    persisted_writer_capability = CarrierCapability.from_fields(
        attempt_id="persisted-writer-attempt",
        actor_id=persisted_writer.actor_id,
        lifecycle_id=persisted_writer.lifecycle_id,
        lineage_id=persisted_writer.lineage_id,
        generation=persisted_writer.generation,
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        can_write=True,
    )
    scheduled_writer_capability = CarrierCapability.from_fields(
        attempt_id="scheduled-writer-attempt",
        actor_id=scheduled_writer.actor_id,
        lifecycle_id=scheduled_writer.lifecycle_id,
        lineage_id=scheduled_writer.lineage_id,
        generation=scheduled_writer.generation,
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        can_write=True,
    )
    reader_capability = CarrierCapability.from_fields(
        attempt_id="reader-attempt",
        actor_id=reader.actor_id,
        lifecycle_id=reader.lifecycle_id,
        lineage_id=reader.lineage_id,
        generation=reader.generation,
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        can_read=True,
    )
    root = tmp_path / "strict-restart-root"
    first = DeclaredCarrierStore(
        registry,
        root=root,
        capabilities=(persisted_writer_capability, reader_capability),
    )
    content = b"persisted-unscheduled-writer"
    first.write(
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        content=content,
        writer=_write_action(persisted_writer, content, carrier_id=carrier_id),
        capability=persisted_writer_capability,
    )
    first.finalize_and_hash(
        carrier_id, capability=persisted_writer_capability
    )
    first.close()

    with pytest.raises(ValueError, match="writer is not authorized"):
        DeclaredCarrierStore(
            registry,
            root=root,
            capabilities=(scheduled_writer_capability, reader_capability),
        )


def test_bound_reopen_rejects_stale_writer_from_reused_run(tmp_path: Path) -> None:
    carrier_id = "run-reuse-carrier"
    carrier_class = StateClass.DECLARED_LINEAGE_CARRIER
    lineage_id = "lineage-run-reuse"
    first_registry = ActionRegistry()
    first_writer = _Actor(
        registry=first_registry,
        actor_id="run-reuse-writer",
        lifecycle_id="run-reuse-writer-lifecycle",
        session_id="run-a-session",
        lineage_id=lineage_id,
        generation=0,
        private_key=Ed25519PrivateKey.generate(),
    )
    first_reader = _Actor(
        registry=first_registry,
        actor_id="run-reuse-reader",
        lifecycle_id="run-reuse-reader-lifecycle",
        session_id="run-a-session",
        lineage_id=lineage_id,
        generation=1,
        private_key=Ed25519PrivateKey.generate(),
    )
    writer_capability = CarrierCapability.from_fields(
        attempt_id="run-reuse-writer-attempt",
        actor_id=first_writer.actor_id,
        lifecycle_id=first_writer.lifecycle_id,
        lineage_id=lineage_id,
        generation=0,
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        can_write=True,
    )
    reader_capability = CarrierCapability.from_fields(
        attempt_id="run-reuse-reader-attempt",
        actor_id=first_reader.actor_id,
        lifecycle_id=first_reader.lifecycle_id,
        lineage_id=lineage_id,
        generation=1,
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        can_read=True,
    )
    root = tmp_path / "reused-run-root"
    first = DeclaredCarrierStore(
        first_registry,
        root=root,
        capabilities=(writer_capability, reader_capability),
    )
    content = b"stale-run-state"
    first.write(
        carrier_id=carrier_id,
        carrier_class=carrier_class,
        content=content,
        writer=_write_action(first_writer, content, carrier_id=carrier_id),
        capability=writer_capability,
    )
    first.finalize_and_hash(carrier_id, capability=writer_capability)
    first.close()

    second_registry = ActionRegistry()
    _Actor(
        registry=second_registry,
        actor_id=first_writer.actor_id,
        lifecycle_id=first_writer.lifecycle_id,
        session_id="run-b-session",
        lineage_id=lineage_id,
        generation=0,
        private_key=Ed25519PrivateKey.generate(),
    )
    _Actor(
        registry=second_registry,
        actor_id=first_reader.actor_id,
        lifecycle_id=first_reader.lifecycle_id,
        session_id="run-b-session",
        lineage_id=lineage_id,
        generation=1,
        private_key=Ed25519PrivateKey.generate(),
    )
    with pytest.raises(ValueError, match="writer identity"):
        DeclaredCarrierStore(
            second_registry,
            root=root,
            capabilities=(writer_capability, reader_capability),
        )
