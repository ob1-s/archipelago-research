"""Narrow, enumerated, hash-finalized cross-generation carrier store."""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import re
import shutil
import stat
import tempfile
from uuid import uuid4
from collections.abc import Iterator
from pathlib import Path

from .attribution import ActionRegistry
from .canonical import sha256_bytes, stable_hash
from .crypto import verify_action
from .models import (
    CarrierDraft,
    CarrierCapability,
    CarrierRecord,
    ActorIdentity,
    SignedAction,
    StateClass,
)


_CARRIER_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LOCK_NAME = ".carrier.lock"
ALLOWED_CARRIER_CLASSES = frozenset(
    {StateClass.DECLARED_LINEAGE_CARRIER, StateClass.DECLARED_BACKUP}
)


def _validate_carrier_id(carrier_id: str) -> None:
    if not _CARRIER_ID.fullmatch(carrier_id):
        raise ValueError("carrier_id is not a safe opaque identifier")


def _validate_digest(value: str, *, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _validate_parent_hashes(parent_hashes: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(parent_hashes)
    for value in normalized:
        _validate_digest(value, label="parent hash")
    if len(set(normalized)) != len(normalized):
        raise ValueError("parent hashes must be unique")
    return normalized


def carrier_write_binding(
    *,
    carrier_id: str,
    carrier_class: StateClass,
    lineage_id: str,
    generation: int,
    content_hash: str,
    parent_hashes: tuple[str, ...] = (),
) -> str:
    """Hash the complete actor-authored carrier-write contract.

    The actor must include this digest in the signed action's ``parent_hashes``.
    That makes the controller-supplied carrier identifier, class, lineage,
    generation, content digest, and declared parent set part of the actor's
    signature instead of controller-only metadata.
    """

    _validate_carrier_id(carrier_id)
    try:
        carrier_class = StateClass(carrier_class)
    except ValueError as exc:
        raise ValueError("carrier class is invalid") from exc
    if carrier_class not in ALLOWED_CARRIER_CLASSES:
        raise ValueError("undeclared or forbidden carrier class")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise ValueError("carrier generation is invalid")
    _validate_digest(content_hash, label="content hash")
    normalized = _validate_parent_hashes(parent_hashes)
    return stable_hash(
        {
            "carrier_id": carrier_id,
            "carrier_class": carrier_class.value,
            "lineage_id": lineage_id,
            "generation": generation,
            "content_hash": content_hash,
            "parent_hashes": list(normalized),
        }
    )


def carrier_read_binding(record: CarrierRecord) -> str:
    """Hash immutable carrier identity/provenance for an actor-signed read."""

    return stable_hash(
        {
            "carrier_id": record.carrier_id,
            "carrier_class": record.carrier_class.value,
            "lineage_id": record.lineage_id,
            "generation": record.generation,
            "content_hash": record.content_hash,
            "parent_hashes": list(record.parent_hashes),
            "write_authority": record.write_authority,
        }
    )


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


def _check_root(root: Path) -> None:
    try:
        metadata = os.lstat(root)
    except FileNotFoundError as exc:
        raise ValueError("carrier root disappeared") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("carrier root must be a real directory")


def _check_artifact(path: Path, *, kind: str, missing_ok: bool = True) -> os.stat_result | None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"{kind} must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{kind} must be a regular file")
    if metadata.st_nlink != 1:
        raise ValueError(f"{kind} must not be a hard link")
    return metadata


def _check_fd(fd: int, *, kind: str) -> os.stat_result:
    metadata = os.fstat(fd)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{kind} must be a regular file")
    if metadata.st_nlink != 1:
        raise ValueError(f"{kind} must not be a hard link")
    return metadata


def _read_artifact(path: Path, *, kind: str) -> bytes:
    flags = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f"{kind} must not be a symlink") from exc
        raise
    try:
        before = _check_fd(fd, kind=kind)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = _check_fd(fd, kind=kind)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError(f"{kind} changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_new_artifact(path: Path, content: bytes, *, kind: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC
    fd = os.open(path, flags, 0o600)
    try:
        _check_fd(fd, kind=kind)
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short artifact write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_directory(root: Path) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | _CLOEXEC
    fd = os.open(root, flags)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("carrier root must be a directory")
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish_new_artifact(
    destination: Path, content: bytes, *, kind: str, root: Path
) -> None:
    """Publish one durable regular file without exposing partial bytes."""

    _check_artifact(destination, kind=kind)
    temporary = root / f".{destination.name}.tmp-{os.getpid()}-{uuid4().hex}"
    _check_artifact(temporary, kind=f"{kind} temporary")
    _write_new_artifact(temporary, content, kind=f"{kind} temporary")
    _check_artifact(temporary, kind=f"{kind} temporary", missing_ok=False)
    os.replace(temporary, destination)
    _check_artifact(destination, kind=kind, missing_ok=False)
    _fsync_directory(root)


class DeclaredCarrierStore:
    def __init__(
        self,
        registry: ActionRegistry,
        root: Path | None = None,
        *,
        capabilities: tuple[CarrierCapability, ...] | None = (),
        allow_unbound_for_testing: bool = False,
    ) -> None:
        self.registry = registry
        self._owned_root = root is None
        if root is None:
            self.root = Path(tempfile.mkdtemp(prefix="h1-carriers-", dir="/tmp"))
        else:
            self.root = Path(root)
            if self.root.exists() or self.root.is_symlink():
                _check_root(self.root)
            else:
                self.root.mkdir(parents=True, exist_ok=True)
        _check_root(self.root)
        self._lock_path = self.root / _LOCK_NAME
        # A qualified store is always capability-bound, including an empty
        # tuple (which denies every carrier operation).  The unbound mode is
        # intentionally explicit and exists only for the low-level mechanical
        # unit tests that exercise actor-signature provenance without a frozen
        # assignment.
        self._capabilities: dict[str, CarrierCapability] | None = None
        if capabilities is None:
            if not allow_unbound_for_testing:
                raise ValueError(
                    "carrier capabilities are required; unbound mode is test-only"
                )
        else:
            self._capabilities = self._index_capabilities(capabilities)
        self._drafts: dict[str, tuple[CarrierDraft, bytes]] = {}
        self._records: dict[str, CarrierRecord] = {}
        self._clock = 0
        # Initial inspection is lock-free only when no lock exists yet.  A
        # pre-existing lock is taken so a reopened store cannot observe a
        # partially published metadata transaction.
        if self._lock_path.exists() or self._lock_path.is_symlink():
            with self._transaction(reload=False):
                self._load_records_unlocked()
        else:
            self._load_records_unlocked()

    @staticmethod
    def _index_capabilities(
        capabilities: tuple[CarrierCapability, ...],
    ) -> dict[str, CarrierCapability]:
        indexed: dict[str, CarrierCapability] = {}
        for capability in capabilities:
            parsed = CarrierCapability.model_validate(
                capability.model_dump(mode="python")
            )
            if parsed.capability_hash in indexed and indexed[parsed.capability_hash] != parsed:
                raise ValueError("carrier capability hash collision")
            indexed[parsed.capability_hash] = parsed
        return indexed

    def bind_capabilities(
        self, capabilities: tuple[CarrierCapability, ...]
    ) -> None:
        """Bind the immutable schedule capability set exactly once.

        This method exists for an externally constructed store passed into an
        :class:`Orchestrator`.  Rebinding after drafts/records exist would let
        a caller widen a previously authorized path, so it is forbidden.
        """

        if self._capabilities is not None:
            if self._capabilities != self._index_capabilities(capabilities):
                raise ValueError("carrier capabilities are already bound")
            return
        if self._drafts or self._records:
            raise ValueError("cannot bind carrier capabilities after carrier use")
        self._capabilities = self._index_capabilities(capabilities)

    @property
    def capabilities_bound(self) -> bool:
        return self._capabilities is not None

    def _require_capability(
        self,
        capability: CarrierCapability | None,
        *,
        operation: str,
        carrier_id: str,
        carrier_class: StateClass | None = None,
        actor: SignedAction | None = None,
        recipient: ActorIdentity | None = None,
        record: CarrierRecord | None = None,
    ) -> CarrierCapability | None:
        """Check a capability before any carrier bytes are opened.

        In strict schedule-backed mode a missing, forged, cross-assignment, or
        wrong-permission capability is rejected.  The low-level unbound store
        retains its original actor-signature checks for the standalone
        mechanical carrier tests; it is never used as an orchestrator's
        carrier surface because the orchestrator binds capabilities at init.
        """

        if self._capabilities is None:
            return None
        if capability is None:
            raise ValueError(f"carrier {operation} capability is required")
        parsed = CarrierCapability.model_validate(
            capability.model_dump(mode="python")
        )
        if self._capabilities.get(parsed.capability_hash) != parsed:
            raise ValueError("carrier capability is not in the frozen schedule")
        if not parsed.permits(operation):
            raise ValueError(f"carrier capability does not permit {operation}")
        if parsed.carrier_id != carrier_id:
            raise ValueError("carrier capability identifier mismatch")
        if carrier_class is not None and parsed.carrier_class != carrier_class:
            raise ValueError("carrier capability class mismatch")
        if record is not None:
            if (
                parsed.carrier_id != record.carrier_id
                or parsed.carrier_class != record.carrier_class
                or parsed.lineage_id != record.lineage_id
                or parsed.generation <= record.generation
            ):
                raise ValueError("carrier capability does not authorize this record")
        if actor is not None and (
            parsed.actor_id != actor.actor_id
            or parsed.lifecycle_id != actor.lifecycle_id
            or parsed.lineage_id != actor.lineage_id
            or parsed.generation != actor.generation
        ):
            raise ValueError("carrier capability does not authorize this actor")
        if recipient is not None:
            if not self.registry.active(recipient.lifecycle_id):
                raise ValueError("carrier recipient lifecycle is not active")
            if (
                parsed.actor_id != recipient.actor_id
                or parsed.lifecycle_id != recipient.lifecycle_id
                or parsed.lineage_id != recipient.lineage_id
                or parsed.generation != recipient.generation
            ):
                raise ValueError("carrier capability does not authorize this recipient")
        return parsed

    def _scheduled_writer_capability(
        self, record: CarrierRecord
    ) -> CarrierCapability | None:
        """Bind durable content to the frozen schedule's exact writer grant."""

        if self._capabilities is None:
            if record.write_capability_hash is not None:
                raise ValueError("unbound store cannot validate bound carrier authority")
            return None
        matches = tuple(
            capability
            for capability in self._capabilities.values()
            if capability.can_write
            and capability.actor_id == record.writer.actor_id
            and capability.lifecycle_id == record.writer.lifecycle_id
            and capability.lineage_id == record.lineage_id
            and capability.generation == record.generation
            and capability.carrier_id == record.carrier_id
            and capability.carrier_class == record.carrier_class
        )
        if len(matches) != 1:
            raise ValueError("carrier writer is not authorized by the frozen schedule")
        capability = matches[0]
        if record.write_capability_hash != capability.capability_hash:
            raise ValueError("carrier writer capability attribution mismatch")
        return capability

    def _validate_scheduled_read_attribution(self, record: CarrierRecord) -> None:
        """Validate every persisted read against its recorded schedule grant."""

        if self._capabilities is None:
            if record.read_capability_hashes:
                raise ValueError("unbound store cannot validate bound read attribution")
            return
        if len(record.read_capability_hashes) != len(record.read_actions):
            raise ValueError("carrier read capability attribution is incomplete")
        for action, capability_hash in zip(
            record.read_actions, record.read_capability_hashes, strict=True
        ):
            capability = self._capabilities.get(capability_hash)
            if (
                capability is None
                or not capability.can_read
                or capability.actor_id != action.actor_id
                or capability.lifecycle_id != action.lifecycle_id
                or capability.lineage_id != action.lineage_id
                or capability.generation != action.generation
                or capability.carrier_id != record.carrier_id
                or capability.carrier_class != record.carrier_class
            ):
                raise ValueError("carrier read is not authorized by the frozen schedule")

    def _content_path(self, carrier_id: str) -> Path:
        _validate_carrier_id(carrier_id)
        return self.root / f"{carrier_id}.carrier"

    def _record_path(self, carrier_id: str) -> Path:
        _validate_carrier_id(carrier_id)
        return self.root / f"{carrier_id}.record.json"

    def _load_records_unlocked(
        self,
        *,
        content_capability: CarrierCapability | None = None,
        verify_all_content: bool = True,
    ) -> None:
        _check_root(self.root)
        records: dict[str, CarrierRecord] = {}
        clock = 0
        for path in sorted(self.root.iterdir(), key=lambda item: item.name):
            if path.name == _LOCK_NAME:
                _check_artifact(path, kind="carrier lock", missing_ok=False)
                continue
            if path.name.endswith(".carrier"):
                carrier_id = path.name[: -len(".carrier")]
                _validate_carrier_id(carrier_id)
                _check_artifact(path, kind="carrier content", missing_ok=False)
                continue
            if not path.name.endswith(".record.json"):
                continue
            _check_artifact(path, kind="carrier metadata", missing_ok=False)
            path_carrier_id = path.name[: -len(".record.json")]
            _validate_carrier_id(path_carrier_id)
            record = CarrierRecord.model_validate_json(
                _read_artifact(path, kind="carrier metadata")
            )
            _validate_carrier_id(record.carrier_id)
            if record.carrier_id != path_carrier_id:
                raise ValueError("persisted carrier metadata filename/ID mismatch")
            _validate_digest(record.content_hash, label="content hash")
            normalized_parents = _validate_parent_hashes(record.parent_hashes)
            if normalized_parents != record.parent_hashes:
                raise ValueError("persisted carrier parent hashes are not canonical")
            if record.carrier_class not in ALLOWED_CARRIER_CLASSES:
                raise ValueError("persisted carrier class is undeclared")
            if record.logical_time < 1:
                raise ValueError("persisted carrier logical time is invalid")
            binding = carrier_write_binding(
                carrier_id=record.carrier_id,
                carrier_class=record.carrier_class,
                lineage_id=record.lineage_id,
                generation=record.generation,
                content_hash=record.content_hash,
                parent_hashes=record.parent_hashes,
            )
            if (
                not verify_action(record.writer)
                or record.writer.action != "carrier_write"
                or record.writer.payload_hash != record.content_hash
                or tuple(record.writer.parent_hashes)
                != (*record.parent_hashes, binding)
                or record.write_authority
                != stable_hash(
                    {
                        "lifecycle_id": record.writer.lifecycle_id,
                        "public_key": record.writer.public_key_b64,
                    }
                )
            ):
                raise ValueError("persisted carrier writer provenance is invalid")
            self._scheduled_writer_capability(record)
            read_binding = carrier_read_binding(record)
            expected_read_parents = (record.content_hash, read_binding)
            for action in record.read_actions:
                _validate_parent_hashes(tuple(action.parent_hashes))
                if (
                    action.action != "carrier_read"
                    or action.payload_hash != record.content_hash
                    or action.lineage_id != record.lineage_id
                    or action.generation <= record.generation
                    or tuple(action.parent_hashes) != expected_read_parents
                ):
                    raise ValueError("persisted carrier read lacks carrier-ID/provenance binding")
            self._validate_scheduled_read_attribution(record)
            verify_this_content = verify_all_content
            if content_capability is not None:
                verify_this_content = record.carrier_id == content_capability.carrier_id
                if verify_this_content and not self._capability_applies_to_record(
                    content_capability, record
                ):
                    raise ValueError("carrier capability does not authorize this record")
            if verify_this_content:
                content_path = self._content_path(record.carrier_id)
                content = _read_artifact(content_path, kind="carrier content")
                if sha256_bytes(content) != record.content_hash:
                    raise ValueError("carrier durable hash mismatch")
            if record.carrier_id in records:
                raise ValueError("duplicate persisted carrier identifier")
            records[record.carrier_id] = record
            clock = max(clock, record.logical_time)
        self._records = records
        self._clock = clock

    @contextlib.contextmanager
    def _transaction(
        self,
        *,
        reload: bool = True,
        content_capability: CarrierCapability | None = None,
        verify_all_content: bool = True,
    ) -> Iterator[None]:
        _check_root(self.root)
        flags = os.O_RDWR | os.O_CREAT | _NOFOLLOW | _CLOEXEC
        try:
            fd = os.open(self._lock_path, flags, 0o600)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError("carrier lock must not be a symlink") from exc
            raise
        try:
            _check_fd(fd, kind="carrier lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            if reload:
                self._load_records_unlocked(
                    content_capability=content_capability,
                    verify_all_content=verify_all_content,
                )
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _persist_record(self, record: CarrierRecord) -> None:
        destination = self._record_path(record.carrier_id)
        _check_artifact(destination, kind="carrier metadata")
        temporary = self.root / (
            f".{record.carrier_id}.record.tmp-{os.getpid()}-{uuid4().hex}"
        )
        _check_artifact(temporary, kind="carrier metadata temporary")
        try:
            _write_new_artifact(
                temporary, record.model_dump_json().encode(), kind="carrier metadata temporary"
            )
            _check_artifact(temporary, kind="carrier metadata temporary", missing_ok=False)
            os.replace(temporary, destination)
            _check_artifact(destination, kind="carrier metadata", missing_ok=False)
            _fsync_directory(self.root)
        except Exception:
            # Never unlink a path we did not create.  A failed transaction can
            # leave a uniquely named temporary artifact for later inspection;
            # startup will not treat it as a published record.
            raise

    def enumerate(
        self,
        *,
        capability: CarrierCapability | None = None,
    ) -> tuple[CarrierRecord, ...]:
        if self._capabilities is not None:
            self._require_capability(
                capability,
                operation="read",
                carrier_id=capability.carrier_id if capability is not None else "",
            )
        with self._transaction(verify_all_content=False):
            if self._capabilities is None:
                return tuple(self._records[key] for key in sorted(self._records))
            assert capability is not None
            return tuple(
                record
                for key, record in sorted(self._records.items())
                if key == capability.carrier_id
                and record.carrier_class == capability.carrier_class
                and self._capability_applies_to_record(capability, record)
            )

    @staticmethod
    def _capability_applies_to_record(
        capability: CarrierCapability, record: CarrierRecord
    ) -> bool:
        return (
            capability.carrier_id == record.carrier_id
            and capability.carrier_class == record.carrier_class
            and capability.lineage_id == record.lineage_id
            and capability.generation > record.generation
        )

    def write(
        self,
        *,
        carrier_id: str,
        carrier_class: StateClass,
        content: bytes,
        writer: SignedAction,
        parent_hashes: tuple[str, ...] = (),
        capability: CarrierCapability | None = None,
    ) -> CarrierDraft:
        _validate_carrier_id(carrier_id)
        try:
            carrier_class = StateClass(carrier_class)
        except ValueError as exc:
            raise ValueError("carrier class is invalid") from exc
        if carrier_class not in ALLOWED_CARRIER_CLASSES:
            raise ValueError("undeclared or forbidden carrier class")
        normalized_parents = _validate_parent_hashes(tuple(parent_hashes))
        content_hash = sha256_bytes(content)
        binding = carrier_write_binding(
            carrier_id=carrier_id,
            carrier_class=carrier_class,
            lineage_id=writer.lineage_id,
            generation=writer.generation,
            content_hash=content_hash,
            parent_hashes=normalized_parents,
        )
        if writer.action != "carrier_write" or writer.payload_hash != content_hash:
            raise ValueError("carrier write action/hash mismatch")
        if tuple(writer.parent_hashes) != (*normalized_parents, binding):
            raise ValueError("carrier write action lacks complete ID/provenance binding")
        self._require_capability(
            capability,
            operation="write",
            carrier_id=carrier_id,
            carrier_class=carrier_class,
            actor=writer,
        )
        with self._transaction(verify_all_content=False):
            if carrier_id in self._records:
                existing = self._records[carrier_id]
                if self._record_matches_write(
                    existing,
                    carrier_class=carrier_class,
                    content_hash=content_hash,
                    writer=writer,
                    parent_hashes=normalized_parents,
                ):
                    # An exact signed replay is safe to return idempotently,
                    # but only while the lifecycle remains active.  A fresh
                    # signed action for the same immutable contract still
                    # consumes the next registry sequence.
                    if (
                        writer == existing.writer
                        and self.registry.active(writer.lifecycle_id)
                        and verify_action(writer)
                    ):
                        return existing
                    if not self.registry.verify(writer):
                        raise ValueError("carrier writer signature/authority is invalid")
                    return existing
                raise ValueError("carrier identifier reused with different content/provenance")
            if carrier_id in self._drafts:
                existing_draft, existing_content = self._drafts[carrier_id]
                if (
                    existing_draft.content_hash == content_hash
                    and existing_draft.carrier_class is carrier_class
                    and existing_draft.lineage_id == writer.lineage_id
                    and existing_draft.generation == writer.generation
                    and existing_draft.parent_hashes == normalized_parents
                    and existing_content == content
                ):
                    if (
                        writer == existing_draft.writer
                        and self.registry.active(writer.lifecycle_id)
                        and verify_action(writer)
                    ):
                        return existing_draft
                    if not self.registry.verify(writer):
                        raise ValueError("carrier writer signature/authority is invalid")
                    return existing_draft
                raise ValueError("carrier identifier reused before finalization")
            if not self.registry.verify(writer):
                raise ValueError("carrier writer signature/authority is invalid")
            content_path = self._content_path(carrier_id)
            try:
                durable_content = _read_artifact(content_path, kind="carrier content")
            except FileNotFoundError:
                durable_content = None
            if durable_content is not None and durable_content != content:
                raise ValueError("orphan carrier identifier has different durable content")
            draft = CarrierDraft(
                carrier_id=carrier_id,
                carrier_class=carrier_class,
                lineage_id=writer.lineage_id,
                generation=writer.generation,
                writer=writer,
                content_hash=content_hash,
                parent_hashes=normalized_parents,
            )
            self._drafts[carrier_id] = (draft, bytes(content))
            return draft

    @staticmethod
    def _record_matches_write(
        record: CarrierRecord,
        *,
        carrier_class: StateClass,
        content_hash: str,
        writer: SignedAction,
        parent_hashes: tuple[str, ...],
    ) -> bool:
        return (
            record.content_hash == content_hash
            and record.carrier_class is carrier_class
            and record.lineage_id == writer.lineage_id
            and record.generation == writer.generation
            and record.parent_hashes == parent_hashes
            and record.writer.actor_id == writer.actor_id
            and record.writer.lifecycle_id == writer.lifecycle_id
            and record.writer.session_id == writer.session_id
            and record.writer.public_key_b64 == writer.public_key_b64
        )

    def finalize_and_hash(
        self,
        carrier_id: str,
        *,
        capability: CarrierCapability | None = None,
    ) -> CarrierRecord:
        _validate_carrier_id(carrier_id)
        return self._finalize_and_hash(carrier_id, capability=capability)

    def _finalize_and_hash(
        self,
        carrier_id: str,
        *,
        capability: CarrierCapability | None,
    ) -> CarrierRecord:
        """Finalize after authorizing the schedule-scoped writer capability."""

        with self._transaction(verify_all_content=False):
            draft_entry = self._drafts.get(carrier_id)
            if draft_entry is None:
                if carrier_id in self._records:
                    self._require_capability(
                        capability,
                        operation="write",
                        carrier_id=carrier_id,
                        carrier_class=self._records[carrier_id].carrier_class,
                        actor=self._records[carrier_id].writer,
                    )
                    return self._records[carrier_id]
                raise KeyError(carrier_id)
            draft, content = draft_entry
            authorized_capability = self._require_capability(
                capability,
                operation="write",
                carrier_id=carrier_id,
                carrier_class=draft.carrier_class,
                actor=draft.writer,
            )
            existing = self._records.get(carrier_id)
            if existing is not None:
                if self._record_matches_write(
                    existing,
                    carrier_class=draft.carrier_class,
                    content_hash=draft.content_hash,
                    writer=draft.writer,
                    parent_hashes=draft.parent_hashes,
                ):
                    self._drafts.pop(carrier_id, None)
                    return existing
                raise ValueError("carrier identifier reused with different content/provenance")
            if sha256_bytes(content) != draft.content_hash:
                raise ValueError("carrier draft changed before finalization")
            path = self._content_path(carrier_id)
            try:
                durable_content = _read_artifact(path, kind="carrier content")
            except FileNotFoundError:
                durable_content = None
            if durable_content is not None and durable_content != content:
                raise ValueError("existing carrier content conflicts with draft")
            if durable_content is None:
                _publish_new_artifact(
                    path,
                    content,
                    kind="carrier content",
                    root=self.root,
                )
                durable_content = _read_artifact(path, kind="carrier content")
            if sha256_bytes(durable_content) != draft.content_hash:
                raise ValueError("carrier durable hash mismatch")
            self._clock += 1
            record = CarrierRecord(
                **draft.model_dump(),
                logical_time=self._clock,
                write_authority=stable_hash(
                    {
                        "lifecycle_id": draft.writer.lifecycle_id,
                        "public_key": draft.writer.public_key_b64,
                    }
                ),
                write_capability_hash=(
                    authorized_capability.capability_hash
                    if authorized_capability is not None
                    else None
                ),
            )
            self._persist_record(record)
            self._records[carrier_id] = record
            self._drafts.pop(carrier_id, None)
            return record

    def read(
        self,
        carrier_id: str,
        *,
        lineage_id: str | None = None,
        capability: CarrierCapability | None = None,
        recipient: ActorIdentity | None = None,
    ) -> tuple[CarrierRecord, bytes]:
        _validate_carrier_id(carrier_id)
        # Authorize before entering the content read path.  In strict mode
        # this is the only route to bytes; ``lineage_id`` is retained solely
        # for compatibility with the unbound low-level probe API.
        if self._capabilities is not None:
            if recipient is None:
                raise ValueError("carrier read recipient identity is required")
            self._require_capability(
                capability, operation="read", carrier_id=carrier_id
            )
            self._require_capability(
                capability,
                operation="read",
                carrier_id=carrier_id,
                recipient=recipient,
            )
        with self._transaction(
            content_capability=capability,
            verify_all_content=False,
        ):
            record = self._records[carrier_id]
            if self._capabilities is not None:
                self._require_capability(
                    capability,
                    operation="read",
                    carrier_id=carrier_id,
                    carrier_class=record.carrier_class,
                    record=record,
                    recipient=recipient,
                )
            elif lineage_id is None or record.lineage_id != lineage_id:
                raise ValueError("cross-lineage carrier read is forbidden")
            content = _read_artifact(
                self._content_path(carrier_id), kind="carrier content"
            )
            if sha256_bytes(content) != record.content_hash:
                raise ValueError("carrier content failed durable hash verification")
            return record, content

    def record_read(
        self,
        carrier_id: str,
        reader: SignedAction,
        *,
        capability: CarrierCapability | None = None,
    ) -> CarrierRecord:
        _validate_carrier_id(carrier_id)
        with self._transaction(verify_all_content=False):
            record = self._records[carrier_id]
            authorized_capability = self._require_capability(
                capability,
                operation="read",
                carrier_id=carrier_id,
                carrier_class=record.carrier_class,
                record=record,
                actor=reader,
            )
            if (
                reader.action != "carrier_read"
                or reader.payload_hash != record.content_hash
                or reader.lineage_id != record.lineage_id
                or reader.generation <= record.generation
                or tuple(reader.parent_hashes)
                != (record.content_hash, carrier_read_binding(record))
            ):
                raise ValueError("carrier read provenance mismatch")
            _validate_parent_hashes(tuple(reader.parent_hashes))
            if not self.registry.verify(reader):
                raise ValueError("carrier reader signature/authority is invalid")
            updated = CarrierRecord.model_validate(
                record.model_copy(
                    update={
                        "read_by": (*record.read_by, reader.actor_id),
                        "read_actions": (*record.read_actions, reader),
                        "read_capability_hashes": (
                            *record.read_capability_hashes,
                            *(
                                (authorized_capability.capability_hash,)
                                if authorized_capability is not None
                                else ()
                            ),
                        ),
                    }
                ).model_dump(mode="python")
            )
            self._persist_record(updated)
            self._records[carrier_id] = updated
            return updated

    def provenance(
        self,
        carrier_id: str,
        *,
        capability: CarrierCapability | None = None,
    ) -> dict:
        _validate_carrier_id(carrier_id)
        with self._transaction(verify_all_content=False):
            record = self._records[carrier_id]
            self._require_capability(
                capability,
                operation="read",
                carrier_id=carrier_id,
                carrier_class=record.carrier_class,
                record=record,
            )
            return {
                "who": record.writer.actor_id,
                "what": record.carrier_id,
                "when": record.logical_time,
                "generation": record.generation,
                "lineage": record.lineage_id,
                "hash": record.content_hash,
                "write_authority": record.write_authority,
                "read_by": list(record.read_by),
                "parentage": list(record.parent_hashes),
                "carrier_class": record.carrier_class,
            }

    def close(self) -> None:
        if self._owned_root:
            _check_root(self.root)
            shutil.rmtree(self.root)


__all__ = [
    "ALLOWED_CARRIER_CLASSES",
    "CarrierCapability",
    "DeclaredCarrierStore",
    "carrier_read_binding",
    "carrier_write_binding",
]
