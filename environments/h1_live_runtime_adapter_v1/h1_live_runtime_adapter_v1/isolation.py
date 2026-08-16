"""Bubblewrap actor lifecycle with fresh private namespaces and ephemeral keys."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import shutil
import signal
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import Any

from .crypto import verify_registration
from .crypto import verify_action
from .models import ActorIdentity, ActorSpec, SignedAction, TeardownEvidence


class ActorProtocolError(RuntimeError):
    pass


class IsolatedActor:
    def __init__(
        self,
        spec: ActorSpec,
        process: asyncio.subprocess.Process,
        identity: ActorIdentity,
        private_root: Path,
        launcher_pid: int,
    ) -> None:
        self.spec = spec
        self.process = process
        self.identity = identity
        self.private_root = private_root
        self.launcher_pid = launcher_pid
        self.closed = False
        self._last_sequence = 0

    async def command(self, command: str, **payload: Any) -> dict[str, Any]:
        if self.closed or self.process.returncode is not None:
            raise ActorProtocolError("actor process is not live")
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        request = json.dumps({"command": command, **payload}, sort_keys=True).encode()
        self.process.stdin.write(request + b"\n")
        await self.process.stdin.drain()
        line = await self.process.stdout.readline()
        if not line:
            raise ActorProtocolError("actor exited before replying")
        response = json.loads(line)
        if not response.get("ok"):
            raise ActorProtocolError(
                f"{response.get('error', 'ActorError')}: {response.get('detail', '')}"
            )
        return response["result"]

    def validate_action(self, raw: dict[str, Any]) -> SignedAction:
        action = SignedAction.model_validate(raw)
        if not verify_action(action):
            raise ActorProtocolError("invalid actor action signature")
        if (
            action.actor_id != self.identity.actor_id
            or action.lifecycle_id != self.identity.lifecycle_id
            or action.session_id != self.identity.session_id
            or action.public_key_b64 != self.identity.public_key_b64
            or action.generation != self.identity.generation
            or action.lineage_id != self.identity.lineage_id
        ):
            raise ActorProtocolError("signed action identity mismatch")
        if action.sequence != self._last_sequence + 1:
            raise ActorProtocolError("signed action sequence is not contiguous")
        self._last_sequence = action.sequence
        return action

    async def stop(self) -> TeardownEvidence:
        if not self.closed and self.process.returncode is None:
            with contextlib.suppress(Exception):
                result = await asyncio.wait_for(self.command("shutdown"), timeout=2)
                self.validate_action(result["action"])
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.process.wait(), timeout=2)
        if self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.launcher_pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.launcher_pid, signal.SIGKILL)
                await self.process.wait()
        self.closed = True
        process_absent = not Path(f"/proc/{self.launcher_pid}").exists()
        try:
            os.getpgid(self.launcher_pid)
            process_group_absent = False
        except ProcessLookupError:
            process_group_absent = True
        shutil.rmtree(self.private_root, ignore_errors=True)
        return TeardownEvidence(
            actor_id=self.identity.actor_id,
            lifecycle_id=self.identity.lifecycle_id,
            launcher_pid=self.launcher_pid,
            runtime_process_id=self.launcher_pid,
            return_code=self.process.returncode or 0,
            process_absent=process_absent,
            process_group_absent=process_group_absent,
            private_root_removed=not self.private_root.exists(),
            key_invalidated=True,
        )


class BubblewrapActorFactory:
    """Starts one actor per call; there is no borrowed or stale-worker spawn path."""

    def __init__(self) -> None:
        if shutil.which("bwrap") is None:
            raise RuntimeError("bubblewrap is required for the qualified runtime")
        self.package_root = Path(__file__).resolve().parent.parent
        self.python_root = Path(sys.executable).resolve().parents[1]
        self.python_name = Path(sys.executable).resolve().name
        self.site_packages = Path(sysconfig.get_paths()["purelib"])
        self.live: dict[str, IsolatedActor] = {}
        self.seen_lifecycles: set[str] = set()
        self.seen_actor_ids: set[str] = set()

    async def spawn(self, spec: ActorSpec) -> IsolatedActor:
        if spec.lifecycle_id in self.seen_lifecycles:
            raise ValueError("lifecycle identifiers cannot be reused")
        if spec.actor_id in self.seen_actor_ids:
            raise ValueError("actor identifiers cannot be reused")
        # Controller environment variables such as TMPDIR must not choose an
        # actor backing location.  A fixed, mode-0700 host path prevents an
        # inherited controller setting from changing isolation semantics.
        private_root = Path(tempfile.mkdtemp(prefix="h1-actor-", dir="/tmp"))
        mounts = {}
        for name in ("work", "home", "tmp", "cache", "env-slot"):
            path = private_root / name
            path.mkdir(mode=0o700)
            mounts[name] = path
        environment_sentinel = secrets.token_hex(32)
        argv = [
            "bwrap",
            "--unshare-all",
            "--unshare-user",
            "--disable-userns",
            "--assert-userns-disabled",
            "--as-pid-1",
            "--new-session",
            "--die-with-parent",
            "--cap-drop",
            "ALL",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
        ]
        if Path("/lib64").exists():
            argv += ["--ro-bind", "/lib64", "/lib64"]
        argv += [
            "--ro-bind",
            str(self.python_root),
            "/python",
            "--ro-bind",
            str(self.site_packages),
            "/deps",
            "--ro-bind",
            str(self.package_root),
            "/app",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--bind",
            str(mounts["work"]),
            "/work",
            "--bind",
            str(mounts["home"]),
            "/home",
            "--bind",
            str(mounts["tmp"]),
            "/tmp",
            "--bind",
            str(mounts["cache"]),
            "/cache",
            "--bind",
            str(mounts["env-slot"]),
            "/env-slot",
            "--chdir",
            "/work",
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "PYTHONPATH",
            "/deps:/app",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "HOME",
            "/home",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "XDG_CACHE_HOME",
            "/cache",
            "--setenv",
            "ACTOR_ENV_PATH",
            "/env-slot/private-canary.bin",
            "--setenv",
            "ACTOR_ENV_SENTINEL",
            environment_sentinel,
            f"/python/bin/{self.python_name}",
            "-m",
            "h1_live_runtime_adapter_v1.actor_worker",
            "--actor-id",
            spec.actor_id,
            "--lifecycle-id",
            spec.lifecycle_id,
            "--generation",
            str(spec.generation),
            "--lineage-id",
            spec.lineage_id,
            "--position",
            spec.position,
        ]
        if spec.gateway_public_key_b64 is not None:
            argv += ["--gateway-public-key-b64", spec.gateway_public_key_b64]
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            if not line:
                assert process.stderr is not None
                detail = (await process.stderr.read()).decode(errors="replace")[-2000:]
                raise ActorProtocolError(f"actor failed to start: {detail}")
            raw = json.loads(line)
            if raw.pop("kind", None) != "ready":
                raise ActorProtocolError("actor did not emit a ready record")
            identity = ActorIdentity.model_validate(raw)
            if not verify_registration(identity):
                raise ActorProtocolError("actor registration proof is invalid")
            if identity.namespace_pid != 1:
                raise ActorProtocolError("actor is not PID 1 in its fresh PID namespace")
            if int(identity.effective_capabilities_hex, 16) != 0:
                raise ActorProtocolError("actor retained effective Linux capabilities")
            if not identity.no_new_privileges:
                raise ActorProtocolError("actor runtime did not set no-new-privileges")
            # Python/cryptography may open the sandbox's fresh /dev/urandom.
            # That immutable entropy device is neither predecessor state nor
            # an externally writable carrier.  Every other descriptor above
            # stdin/stdout/stderr fails closed (regular files, pipes, sockets,
            # memfd, eventfd, and inherited host handles included).
            unexpected_fds = {
                fd: target
                for fd, target in identity.open_extra_fd_targets.items()
                if target != "/dev/urandom"
            }
            if unexpected_fds:
                raise ActorProtocolError(
                    "actor has an undeclared open file descriptor: "
                    f"{unexpected_fds!r}"
                )
            expected_environment = {
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
            if set(identity.environment_names) != expected_environment:
                raise ActorProtocolError(
                    "actor environment differs from the exact allowlist: "
                    f"{identity.environment_names!r}"
                )
            if any(
                getattr(identity, field) != getattr(spec, field)
                for field in (
                    "actor_id",
                    "lifecycle_id",
                    "generation",
                    "lineage_id",
                    "position",
                    "gateway_public_key_b64",
                )
            ):
                raise ActorProtocolError("actor registration identity mismatch")
        except Exception:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            shutil.rmtree(private_root, ignore_errors=True)
            raise
        actor = IsolatedActor(spec, process, identity, private_root, process.pid)
        self.live[spec.actor_id] = actor
        self.seen_lifecycles.add(spec.lifecycle_id)
        self.seen_actor_ids.add(spec.actor_id)
        return actor

    async def stop(self, actor: IsolatedActor) -> TeardownEvidence:
        evidence = await actor.stop()
        self.live.pop(actor.spec.actor_id, None)
        return evidence

    async def close(self) -> list[TeardownEvidence]:
        evidence = []
        for actor in list(self.live.values()):
            evidence.append(await self.stop(actor))
        return evidence
