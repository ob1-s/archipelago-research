"""Trusted narrow actor process. The private action key never crosses stdout."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import socket
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .canonical import canonical_bytes, sha256_bytes, stable_hash
from .carrier import carrier_write_binding
from .crypto import verify_gateway_receipt
from .models import GatewayReceipt, StateClass


def _process_start_ticks() -> int:
    return int(Path("/proc/self/stat").read_text().split()[21])


def _status_value(name: str) -> str:
    prefix = f"{name}:"
    return next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith(prefix)
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--lifecycle-id", required=True)
    parser.add_argument("--generation", required=True, type=int)
    parser.add_argument("--lineage-id", required=True)
    parser.add_argument("--position", required=True)
    parser.add_argument("--gateway-public-key-b64")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    private_key = Ed25519PrivateKey.generate()
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    session_id = f"session-{secrets.token_hex(16)}"
    start_ticks = _process_start_ticks()
    environment_names = tuple(sorted(os.environ))
    environment_fingerprint = stable_hash(sorted(os.environ.items()))
    namespace_ids = {
        name: os.readlink(f"/proc/self/ns/{name}")
        for name in ("pid", "mnt", "ipc", "uts", "user", "cgroup", "net")
    }
    # This is a point-in-time inventory after interpreter and cryptographic
    # initialization.  It is deliberately called "open" rather than
    # "inherited": a runtime dependency may open an immutable OS entropy
    # source itself even though Bubblewrap inherited no such descriptor.
    open_extra_fd_targets = {}
    for raw_fd in os.listdir("/proc/self/fd"):
        if not raw_fd.isdigit() or int(raw_fd) <= 2:
            continue
        try:
            open_extra_fd_targets[raw_fd] = os.readlink(f"/proc/self/fd/{raw_fd}")
        except OSError:
            pass
    open_extra_fd_count = len(open_extra_fd_targets)
    registration = {
        "actor_id": args.actor_id,
        "lifecycle_id": args.lifecycle_id,
        "generation": args.generation,
        "lineage_id": args.lineage_id,
        "position": args.position,
        "gateway_public_key_b64": args.gateway_public_key_b64,
        "session_id": session_id,
        "public_key_b64": public_key_b64,
        "namespace_pid": os.getpid(),
        "namespace_process_start_ticks": start_ticks,
        "environment_fingerprint": environment_fingerprint,
        "environment_names": environment_names,
        "namespace_ids": namespace_ids,
        "effective_capabilities_hex": _status_value("CapEff"),
        "no_new_privileges": _status_value("NoNewPrivs") == "1",
        "open_extra_fd_count": open_extra_fd_count,
        "open_extra_fd_targets": open_extra_fd_targets,
    }
    registration_signature = base64.b64encode(
        private_key.sign(
            b"h1-live-runtime-registration/v1\0" + canonical_bytes(registration)
        )
    ).decode()
    print(
        json.dumps(
            {
                "kind": "ready",
                **registration,
                "registration_signature_b64": registration_signature,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    history: list[str] = []
    sequence = 0

    def sign_action(
        action: str, payload_hash: str, parent_hashes: list[str] | None = None
    ) -> dict[str, Any]:
        nonlocal sequence
        sequence += 1
        unsigned = {
            "actor_id": args.actor_id,
            "lifecycle_id": args.lifecycle_id,
            "session_id": session_id,
            "generation": args.generation,
            "lineage_id": args.lineage_id,
            "public_key_b64": public_key_b64,
            "sequence": sequence,
            "action_id": f"{args.lifecycle_id}:{sequence}",
            "action": action,
            "payload_hash": payload_hash,
            "parent_hashes": parent_hashes or [],
        }
        signature = base64.b64encode(
            private_key.sign(
                b"h1-live-runtime-action/v1\0" + canonical_bytes(unsigned)
            )
        ).decode()
        return {**unsigned, "signature_b64": signature}

    for line in sys.stdin:
        request = json.loads(line)
        command = request.get("command")
        try:
            if command == "ping":
                result = {"history_length": len(history), "session_id": session_id}
            elif command == "append_history":
                value = str(request["value"])
                history.append(value)
                result = {"history_length": len(history), "value_hash": stable_hash(value)}
            elif command == "write_canaries":
                locations = {
                    "workdir": Path("/work/private-canary.bin"),
                    "home": Path("/home/private-canary.bin"),
                    "tmp": Path("/tmp/private-canary.bin"),
                    "shared_memory": Path("/dev/shm/private-canary.bin"),
                    "cache": Path("/cache/private-canary.bin"),
                    "env_path": Path(os.environ["ACTOR_ENV_PATH"]),
                }
                path_hashes = {}
                for name, path in locations.items():
                    value = secrets.token_bytes(32)
                    path.write_bytes(value)
                    path_hashes[name] = sha256_bytes(value)
                canary_payload = {
                    "actor_id": args.actor_id,
                    "path_hashes": path_hashes,
                    "environment_value_hash": stable_hash(
                        os.environ["ACTOR_ENV_SENTINEL"]
                    ),
                    "paths": [str(path) for path in locations.values()],
                    "history_length": len(history),
                }
                result = {
                    "path_hashes": path_hashes,
                    "paths": [str(path) for path in locations.values()],
                    "environment_value_hash": canary_payload["environment_value_hash"],
                    "history_length": len(history),
                    "action": sign_action(
                        "write_canaries", stable_hash(canary_payload)
                    ),
                }
            elif command == "probe_paths":
                probes = {
                        path: {
                            "exists": Path(path).exists(),
                            "content_hash": (
                                sha256_bytes(Path(path).read_bytes())
                                if Path(path).is_file()
                                else None
                            ),
                        }
                        for path in request["paths"]
                    }
                environment_value_hash = stable_hash(os.environ["ACTOR_ENV_SENTINEL"])
                history_length = len(history)
                probe_payload = {
                    "path_probes": {
                        path: value["exists"] for path, value in probes.items()
                    },
                    "environment_value_hash": environment_value_hash,
                    "history_length": history_length,
                }
                result = {
                    "probes": probes,
                    "environment_value_hash": environment_value_hash,
                    "history_length": history_length,
                    "action": sign_action("probe_paths", stable_hash(probe_payload)),
                }
            elif command == "create_mechanical_carrier":
                payload = f"declared-mechanical-carrier:{secrets.token_hex(16)}".encode()
                payload_hash = sha256_bytes(payload)
                carrier_id = str(request["carrier_id"])
                carrier_class = StateClass(request["carrier_class"])
                declared_parent_hashes = tuple(request["parent_hashes"])
                carrier_binding = carrier_write_binding(
                    carrier_id=carrier_id,
                    carrier_class=carrier_class,
                    lineage_id=args.lineage_id,
                    generation=args.generation,
                    content_hash=payload_hash,
                    parent_hashes=declared_parent_hashes,
                )
                result = {
                    "carrier_id": carrier_id,
                    "carrier_class": carrier_class.value,
                    "parent_hashes": list(declared_parent_hashes),
                    "content_b64": base64.b64encode(payload).decode(),
                    "content_hash": payload_hash,
                    "action": sign_action(
                        "carrier_write",
                        payload_hash,
                        [*declared_parent_hashes, carrier_binding],
                    ),
                }
            elif command == "carrier_read":
                payload = base64.b64decode(request["content_b64"])
                content_hash = sha256_bytes(payload)
                if content_hash != request["content_hash"]:
                    raise ValueError("carrier content hash mismatch")
                history.append(f"carrier:{content_hash}")
                result = {
                    "content_hash": content_hash,
                    "action": sign_action(
                        "carrier_read",
                        content_hash,
                        [content_hash, request["provenance_hash"]],
                    ),
                    "carrier_id": request["carrier_id"],
                    "history_length": len(history),
                }
            elif command == "prepare_provider_request":
                payload = request["semantic_payload"]
                payload_hash = stable_hash(payload)
                result = {
                    "payload_hash": payload_hash,
                    "action": sign_action("provider_request", payload_hash),
                }
            elif command == "accept_provider_response":
                receipt = GatewayReceipt.model_validate(request["gateway_receipt"])
                if (
                    args.gateway_public_key_b64 is None
                    or receipt.public_key_b64 != args.gateway_public_key_b64
                    or not verify_gateway_receipt(receipt)
                    or receipt.output_hash != request["output_hash"]
                    or receipt.request_hash != request["request_hash"]
                    or receipt.assignment_hash != request["assignment_hash"]
                ):
                    raise ValueError("provider gateway receipt is invalid")
                output_hash = sha256_bytes(request["output_text"].encode())
                if output_hash != request["output_hash"]:
                    raise ValueError("provider response hash mismatch")
                history.append(f"provider:{output_hash}")
                result = {
                    "output_hash": output_hash,
                    "action": sign_action(
                        "provider_response_accept",
                        output_hash,
                        [
                            request["request_hash"],
                            stable_hash(receipt.model_dump(mode="json")),
                        ],
                    ),
                }
            elif command == "scripted_infer":
                prompt_hash = stable_hash(request["input"])
                output_text = f"mechanical-scripted:{prompt_hash}"
                output_hash = sha256_bytes(output_text.encode())
                history.append(f"scripted:{output_hash}")
                result = {
                    "output_text": output_text,
                    "output_hash": output_hash,
                    "response_id": f"scripted-{secrets.token_hex(8)}",
                    "action": sign_action("scripted_infer", output_hash, [prompt_hash]),
                }
            elif command == "network_probe":
                route = Path("/proc/net/route").read_text()
                default_route = any(
                    fields[1] == "00000000"
                    for line in route.splitlines()[1:]
                    if len(fields := line.split()) > 1
                )
                try:
                    with socket.create_connection(("1.1.1.1", 443), timeout=0.2):
                        external_connect = True
                except OSError:
                    external_connect = False
                try:
                    socket.getaddrinfo("example.com", 443)
                    dns_resolved = True
                except OSError:
                    dns_resolved = False
                result = {
                    "default_route": default_route,
                    "external_connect": external_connect,
                    "dns_resolved": dns_resolved,
                    "route_hash": sha256_bytes(route.encode()),
                }
                result["action"] = sign_action(
                    "network_probe", stable_hash(
                        {
                            "default_route": result["default_route"],
                            "external_connect": result["external_connect"],
                            "dns_resolved": result["dns_resolved"],
                            "route_hash": result["route_hash"],
                        }
                    )
                )
            elif command == "crash":
                os._exit(int(request.get("exit_code", 70)))
            elif command == "shutdown":
                result = {"action": sign_action("shutdown", stable_hash("shutdown"))}
                print(json.dumps({"ok": True, "result": result}), flush=True)
                break
            else:
                raise ValueError(f"unknown command: {command!r}")
            print(json.dumps({"ok": True, "result": result}, sort_keys=True), flush=True)
        except Exception as exc:
            print(
                json.dumps(
                    {"ok": False, "error": type(exc).__name__, "detail": str(exc)},
                    sort_keys=True,
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
