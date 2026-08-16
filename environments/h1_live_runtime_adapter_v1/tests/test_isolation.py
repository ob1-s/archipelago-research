"""Mechanical qualification tests for the Bubblewrap actor boundary.

This module deliberately exercises the process and credential boundary only.
It never contacts a model, starts a provider client, or treats an actor's
scripted commands as scientific output.  The tests use the real Bubblewrap
launcher so that the claims below are about the qualified runtime rather than
about a mock process object.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest

from h1_live_runtime_adapter_v1.attribution import ActionRegistry
from h1_live_runtime_adapter_v1.canonical import canonical_bytes, stable_hash
from h1_live_runtime_adapter_v1.crypto import verify_action
from h1_live_runtime_adapter_v1.isolation import (
    ActorProtocolError,
    BubblewrapActorFactory,
)
from h1_live_runtime_adapter_v1.models import ActorSpec, StateClass


NAMESPACE_NAMES = {"pid", "mnt", "ipc", "uts", "user", "cgroup", "net"}
EXACT_ENVIRONMENT = {
    "ACTOR_ENV_PATH",
    "ACTOR_ENV_SENTINEL",
    "HOME",
    "LC_CTYPE",
    "PATH",
    "PWD",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPATH",
    "TMPDIR",
    "XDG_CACHE_HOME",
}
CANARY_NAMES = {
    "workdir",
    "home",
    "tmp",
    "shared_memory",
    "cache",
    "env_path",
}


def _spec(
    *,
    generation: int = 0,
    actor_id: str | None = None,
    lifecycle_id: str | None = None,
    lineage_id: str = "isolation-test-lineage",
) -> ActorSpec:
    suffix = uuid4().hex
    return ActorSpec(
        actor_id=actor_id or f"actor-{suffix}",
        lifecycle_id=lifecycle_id or f"lifecycle-{suffix}",
        generation=generation,
        lineage_id=lineage_id,
        position="isolation-test",
    )


async def _stop(factory: BubblewrapActorFactory, actor: object | None) -> None:
    if actor is None:
        return
    # The helper is intentionally tolerant of a test's preceding assertion
    # failing after the child has already exited.
    try:
        await factory.stop(actor)  # type: ignore[arg-type]
    except (ActorProtocolError, ProcessLookupError, asyncio.TimeoutError):
        await factory.close()


@pytest.mark.asyncio
async def test_fresh_actor_identity_os_isolation_and_all_namespaces() -> None:
    """Each generation has fresh identity, process, session, key and namespaces."""

    factory = BubblewrapActorFactory()
    predecessor = None
    successor = None
    try:
        predecessor = await factory.spawn(_spec(generation=0))
        predecessor_identity = predecessor.identity
        predecessor_process_id = predecessor.launcher_pid

        assert predecessor_identity.namespace_pid == 1
        assert int(predecessor_identity.effective_capabilities_hex, 16) == 0
        assert predecessor_identity.no_new_privileges is True
        assert set(predecessor_identity.namespace_ids) == NAMESPACE_NAMES
        assert predecessor_identity.open_extra_fd_count == len(
            predecessor_identity.open_extra_fd_targets
        )
        assert set(predecessor_identity.open_extra_fd_targets.values()) == {
            "/dev/urandom"
        }

        predecessor_teardown = await factory.stop(predecessor)
        predecessor = None
        assert predecessor_teardown.process_absent
        assert predecessor_teardown.process_group_absent
        assert predecessor_teardown.private_root_removed
        assert predecessor_teardown.key_invalidated

        successor = await factory.spawn(_spec(generation=1))
        successor_identity = successor.identity

        assert successor_identity.actor_id != predecessor_identity.actor_id
        assert successor.launcher_pid != predecessor_process_id
        assert successor.process.pid == successor.launcher_pid
        assert successor_identity.lifecycle_id != predecessor_identity.lifecycle_id
        assert successor_identity.session_id != predecessor_identity.session_id
        assert successor_identity.public_key_b64 != predecessor_identity.public_key_b64
        assert successor_identity.namespace_pid == 1
        assert int(successor_identity.effective_capabilities_hex, 16) == 0
        assert successor_identity.no_new_privileges is True
        assert set(successor_identity.namespace_ids) == NAMESPACE_NAMES
        # Namespace inode display values can be recycled after the predecessor
        # is destroyed. The factory's fixed --unshare-all exec path plus PID1,
        # fresh process-start identity, and full inventory are the stable proof.
        assert all(predecessor_identity.namespace_ids.values())
        assert all(successor_identity.namespace_ids.values())
    finally:
        await _stop(factory, predecessor)
        await _stop(factory, successor)


@pytest.mark.asyncio
async def test_work_home_tmp_cache_env_and_devshm_canaries_do_not_cross_turnover() -> None:
    """All enumerated mutable path surfaces and actor history are fresh."""

    factory = BubblewrapActorFactory()
    predecessor = None
    successor = None
    try:
        predecessor = await factory.spawn(_spec(generation=0))
        predecessor_environment_fingerprint = (
            predecessor.identity.environment_fingerprint
        )
        await predecessor.command("append_history", value="predecessor-only-history")
        predecessor_canary = await predecessor.command("write_canaries")
        canary_action = predecessor.validate_action(predecessor_canary.pop("action"))
        assert canary_action.action == "write_canaries"
        assert set(predecessor_canary["path_hashes"]) == CANARY_NAMES
        assert set(
            predecessor_canary["paths"]
        ) == {
            "/work/private-canary.bin",
            "/home/private-canary.bin",
            "/tmp/private-canary.bin",
            "/dev/shm/private-canary.bin",
            "/cache/private-canary.bin",
            "/env-slot/private-canary.bin",
        }
        predecessor_environment_hash = predecessor_canary["environment_value_hash"]

        await factory.stop(predecessor)
        predecessor = None

        successor = await factory.spawn(_spec(generation=1))
        probe = await successor.command("probe_paths", paths=predecessor_canary["paths"])
        probe_action = successor.validate_action(probe.pop("action"))
        assert probe_action.action == "probe_paths"
        assert probe["history_length"] == 0
        assert probe["environment_value_hash"] != predecessor_environment_hash
        assert set(probe["probes"]) == set(predecessor_canary["paths"])
        assert all(not item["exists"] for item in probe["probes"].values())
        assert all(item["content_hash"] is None for item in probe["probes"].values())

        # The new actor's allowlisted environment is present, but the prior
        # actor's random sentinel and path content are not.
        assert set(successor.identity.environment_names) == EXACT_ENVIRONMENT
        assert (
            successor.identity.environment_fingerprint
            != predecessor_environment_fingerprint
        )
    finally:
        await _stop(factory, predecessor)
        await _stop(factory, successor)


@pytest.mark.asyncio
async def test_exact_environment_allowlist_and_controller_tmpdir_cannot_redirect_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Controller temp settings cannot select an actor's private backing root."""

    monkeypatch.setenv("TMPDIR", "/dev/shm")
    factory = BubblewrapActorFactory()
    actor = None
    try:
        actor = await factory.spawn(_spec())
        assert actor.private_root.parent == Path("/tmp")
        assert actor.private_root != Path("/dev/shm")
        assert set(actor.identity.environment_names) == EXACT_ENVIRONMENT
        assert (await actor.command("ping"))["session_id"] == actor.identity.session_id
    finally:
        await _stop(factory, actor)


@pytest.mark.asyncio
async def test_host_file_descriptor_injection_is_not_inherited() -> None:
    """A deliberately inheritable controller fd cannot enter the actor."""

    read_fd, write_fd = os.pipe()
    host_fd = None
    try:
        host_fd = os.open("/etc/hosts", os.O_RDONLY)
        os.set_inheritable(read_fd, True)
        os.set_inheritable(write_fd, True)
        os.set_inheritable(host_fd, True)

        factory = BubblewrapActorFactory()
        actor = None
        try:
            actor = await factory.spawn(_spec())
            targets = actor.identity.open_extra_fd_targets
            assert actor.identity.open_extra_fd_count == len(targets)
            assert set(targets.values()) == {"/dev/urandom"}
            assert str(read_fd) not in targets
            assert str(write_fd) not in targets
            assert str(host_fd) not in targets
        finally:
            await _stop(factory, actor)
    finally:
        os.close(read_fd)
        os.close(write_fd)
        if host_fd is not None:
            os.close(host_fd)


@pytest.mark.asyncio
async def test_network_is_unshared_and_unknown_shell_or_tool_commands_are_rejected() -> None:
    """The actor has no route, DNS, or external socket and no shell/tool API."""

    factory = BubblewrapActorFactory()
    actor = None
    try:
        actor = await factory.spawn(_spec())
        network = await actor.command("network_probe")
        network_action = actor.validate_action(network.pop("action"))
        assert network_action.action == "network_probe"
        assert set(network) == {
            "default_route",
            "external_connect",
            "dns_resolved",
            "route_hash",
        }
        assert network["default_route"] is False
        assert network["dns_resolved"] is False
        assert network["external_connect"] is False
        assert re.fullmatch(r"[0-9a-f]{64}", network["route_hash"])

        for forbidden in ("shell", "exec", "tool", "mcp", "sign"):
            with pytest.raises(ActorProtocolError, match="unknown command"):
                await actor.command(forbidden, argv=["/bin/sh", "-c", "true"])
    finally:
        await _stop(factory, actor)


@pytest.mark.asyncio
async def test_crashed_actor_is_reaped_with_process_group_and_private_root_removed() -> None:
    """Crash teardown proves the launcher cannot leave a stale worker behind."""

    factory = BubblewrapActorFactory()
    actor = await factory.spawn(_spec())
    private_root = actor.private_root
    launcher_pid = actor.launcher_pid
    try:
        with pytest.raises(ActorProtocolError, match="exited before replying"):
            await actor.command("crash", exit_code=73)
        await actor.process.wait()

        evidence = await factory.stop(actor)
        actor = None
        assert evidence.return_code == 73
        assert evidence.launcher_pid == launcher_pid
        assert evidence.runtime_process_id == launcher_pid
        assert evidence.process_absent
        assert evidence.process_group_absent
        assert evidence.private_root_removed
        assert evidence.key_invalidated
        assert not private_root.exists()
        assert not Path(f"/proc/{launcher_pid}").exists()
    finally:
        await _stop(factory, actor)


@pytest.mark.asyncio
async def test_lifecycle_and_actor_identity_reuse_are_rejected() -> None:
    """The factory refuses stale lifecycle IDs and actor IDs after teardown."""

    factory = BubblewrapActorFactory()
    actor = None
    first = _spec()
    try:
        actor = await factory.spawn(first)
        with pytest.raises(ValueError, match="actor identifier"):
            await factory.spawn(
                _spec(actor_id=first.actor_id, lifecycle_id=fresh_lifecycle())
            )
        with pytest.raises(ValueError, match="lifecycle identifiers"):
            await factory.spawn(
                _spec(actor_id=fresh_actor(), lifecycle_id=first.lifecycle_id)
            )
    finally:
        await _stop(factory, actor)

    # A lifecycle remains spent after the process has been torn down.
    with pytest.raises(ValueError, match="lifecycle identifiers"):
        await factory.spawn(_spec(actor_id=fresh_actor(), lifecycle_id=first.lifecycle_id))

    # Actor identifiers are also spent after teardown; otherwise a standalone
    # factory user could accidentally relabel a fresh process as an old actor.
    with pytest.raises(ValueError, match="actor identifier"):
        await factory.spawn(
            _spec(actor_id=first.actor_id, lifecycle_id=fresh_lifecycle())
        )
    await factory.close()


def fresh_actor() -> str:
    return f"actor-{uuid4().hex}"


def fresh_lifecycle() -> str:
    return f"lifecycle-{uuid4().hex}"


@pytest.mark.asyncio
async def test_action_signatures_registry_authority_and_revocation_fail_closed() -> None:
    """Only the actor can produce actions; the registry verifies and revokes keys."""

    factory = BubblewrapActorFactory()
    registry = ActionRegistry()
    actor = None
    try:
        actor = await factory.spawn(_spec())
        registry.register(actor.identity)
        assert registry.private_key_count == 0
        assert not hasattr(registry, "sign")
        assert not any("private_key" in name for name in vars(registry))

        created = await actor.command(
            "create_mechanical_carrier",
            carrier_id="isolation-test-carrier",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER.value,
            parent_hashes=[],
        )
        action = actor.validate_action(created["action"])
        assert verify_action(action)
        assert registry.verify(action)

        tampered = action.model_copy(
            update={"payload_hash": stable_hash("tampered-action-payload")}
        )
        assert not verify_action(tampered)
        assert not registry.verify(tampered, consume=False)

        registry.revoke(actor.identity.lifecycle_id)
        next_created = await actor.command(
            "create_mechanical_carrier",
            carrier_id="isolation-test-carrier-2",
            carrier_class=StateClass.DECLARED_LINEAGE_CARRIER.value,
            parent_hashes=[],
        )
        next_action = actor.validate_action(next_created["action"])
        assert verify_action(next_action)
        assert not registry.verify(next_action)
        assert not registry.active(actor.identity.lifecycle_id)
    finally:
        await _stop(factory, actor)


@pytest.mark.asyncio
async def test_registration_signature_is_bound_to_identity_and_actor_cannot_sign_arbitrary_payloads() -> None:
    """The ready record is self-authenticating and the worker has no generic signer."""

    factory = BubblewrapActorFactory()
    actor = None
    try:
        actor = await factory.spawn(_spec())
        identity = actor.identity
        registration = identity.model_dump(
            exclude={"registration_signature_b64"}, mode="json"
        )
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(identity.public_key_b64))
        key.verify(
            base64.b64decode(identity.registration_signature_b64),
            b"h1-live-runtime-registration/v1\0" + canonical_bytes(registration),
        )

        with pytest.raises(ActorProtocolError, match="unknown command"):
            await actor.command("sign", payload="controller-forged-content")
    finally:
        await _stop(factory, actor)
