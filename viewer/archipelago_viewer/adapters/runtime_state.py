"""Adapter for the H1 live-runtime qualification record (read-only).

``docs/h1_live_runtime_adapter_2026-08-15/RUNTIME_BOUNDARY_STATE.json`` is a
complete, signed, machine-generated record of a real mechanical turnover:
lifecycle journal rows, actor identities, teardown evidence, signed actions
(canaries, carrier writes/reads, probes, provider traffic), retries, and the
21 qualification gates.

Mapping rules (deterministic, no invented facts):

* Lifecycle journal rows become ``spawn`` / ``teardown`` /
  ``authorization_revoked`` events in journal-sequence order with the verbatim
  row in the payload.  Successor spawn with ``generation >= 1`` is flagged
  ``turnover`` by the reducer (never by this adapter).
* Teardown evidence is matched to actors by ``runtime_process_id``.
* The carrier record becomes a ``carrier`` artifact plus ``carrier_*``
  events; the signed writer/reader actions become ``artifact_write`` /
  ``artifact_read`` events with the full action in the payload.
* All other signed actions (``write_canaries``, ``probe_paths``,
  ``network_probe``, ``provider_request``, ``provider_response_accept``)
  become events of the matching kind with verbatim payloads.
* The clock is synthetic: events are ordered exactly as in the source and
  ``t`` increments by 1 second per emitted event (documented rule; the journal
  carries no wall-clock).
* Gate results, readiness adjudications, record hash, and status are copied
  into ``meta`` verbatim.
"""

from __future__ import annotations

import json
from typing import Any

from .base import Adapter
from ..schema import ViewerAgent, ViewerArtifact, ViewerCarrier, ViewerEvent, ViewerEpisode
from ..util import fold_text, stable_id


def _now_utc() -> str:
    from ..util import now_utc
    return now_utc()


class RuntimeBoundaryAdapter(Adapter):
    name = "h1-runtime-boundary-state.json"
    extensions = (".json",)

    @classmethod
    def _probe(cls, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(data, dict) and "boundary_assessment" in data and "runtime_boundary" in data

    @classmethod
    def load(cls, path: str, limit: int | None = None, group_mode: str = "community") -> list[ViewerEpisode]:
        with open(path, "r", encoding="utf-8") as fh:
            report = json.load(fh)
        return [cls._build(report, path)]

    # ---------------------------------------------------------------- build

    @classmethod
    def _build(cls, report: dict[str, Any], path: str) -> ViewerEpisode:
        boundary = report.get("runtime_boundary") or {}
        assessment = report.get("boundary_assessment") or {}
        episode = ViewerEpisode(
            id=stable_id("h1", boundary.get("provider_policy", {}).get("adapter", "runtime"), report.get("record_hash", ""), width=12),
            title="H1 live-runtime mechanical turnover",
            environment="h1_live_runtime_adapter_v1",
            source=cls.describe(path),
            source_kind=cls.name,
            generated_at=_now_utc(),
        )
        episode.meta = {
            "status": report.get("status"),
            "record_hash": report.get("record_hash"),
            "execution_status": report.get("execution_status"),
            "authorized_to_run_h1": report.get("authorized_to_run_h1"),
            "live_model_calls": report.get("live_model_calls"),
            "scientific_result": report.get("scientific_result"),
            "qualification_version": report.get("qualification_version"),
            "gates": report.get("gate_results") or {},
            "gate_pass": sum(
                1 for v in (report.get("gate_results") or {}).values() if v is True
            ),
            "assessment": assessment,
            "claim_mapping": report.get("claim_mapping") or [],
            "fixtures": report.get("runtime_fixture_assessments") or [],
            "readiness_questions": report.get("readiness_questions") or [],
            "required_as_part_of_h1_freeze": report.get("required_as_part_of_h1_freeze") or [],
            "required_before_h1_execution": report.get("required_before_h1_execution") or [],
            "recommended_defense_in_depth": report.get("recommended_defense_in_depth") or [],
        }

        # ---- agents ---------------------------------------------------------
        actors: list[tuple[str, Any]] = []  # (side, ActorRuntimeRecord)
        for side in ("predecessors", "successors"):
            for record in boundary.get(side) or []:
                actors.append((side, record))
        actor_ids: dict[str, str] = {}
        for side, record in actors:
            identity = record.get("identity") or {}
            actor_id = stable_id(
                "h1a", identity.get("lifecycle_id", ""), identity.get("actor_id", ""), width=10
            )
            lineage_id = str(identity.get("lineage_id", ""))
            generation = int(identity.get("generation", 0))
            actor_ids[identity.get("lifecycle_id", "")] = actor_id
            episode.agents.append(
                ViewerAgent(
                    id=actor_id,
                    name=f"{side[:-1]} actor" if side in ("predecessors", "successors") else side,
                    role="actor",
                    lineage_id=lineage_id,
                    generation=generation,
                    source_id=identity.get("actor_id", ""),
                    attributes={
                        "side": side,
                        "session_id": identity.get("session_id"),
                        "runtime_process_id": record.get("runtime_process_id"),
                        "namespace_ids": identity.get("namespace_ids") or {},
                        "environment_fingerprint": identity.get("environment_fingerprint"),
                        "public_key_b64": identity.get("public_key_b64", "")[:24] + "…" if identity.get("public_key_b64") else "",
                        "record": record,
                    },
                )
            )
        controller_id = "controller"
        episode.agents.insert(
            0,
            ViewerAgent(
                id=controller_id,
                name="controller (Orchestrator)",
                role="controller",
                attributes={
                    "adapter": boundary.get("provider_policy", {}).get("adapter"),
                    "actor_network_mode": boundary.get("actor_network_mode"),
                    "runtime_versions": boundary.get("runtime_versions") or {},
                    "common_prior_hashes": boundary.get("common_prior_hashes") or {},
                },
            ),
        )

        # ---- carriers & artifacts -------------------------------------------
        artifact_ids: dict[str, str] = {}
        carriers: list[ViewerCarrier] = []
        for record in boundary.get("carrier_records") or []:
            carrier_id = str(record.get("carrier_id", "carrier"))
            artifact_key = stable_id("h1art", carrier_id, width=10)
            artifact_ids[carrier_id] = artifact_key
            episode.meta.setdefault("carrier_records", []).append(
                {"carrier_id": carrier_id, "record": record}
            )

        # ---- event stream ----------------------------------------------------
        events: list[ViewerEvent] = []
        seq = 0
        clock = 0.0

        def emit(
            kind: str,
            title: str,
            detail: str = "",
            agent_id: str = "",
            payload: dict[str, Any] | None = None,
        ) -> ViewerEvent:
            nonlocal seq, clock
            event = ViewerEvent(
                seq=seq,
                t=clock,
                kind=kind,
                agent_id=agent_id,
                title=title,
                detail=detail,
                payload=dict(payload or {}),
            )
            events.append(event)
            seq += 1
            clock += 1.0
            return event

        # lifecycle journal rows ("sequence" ascending in the source; keep order)
        lifecycle_rows = boundary.get("lifecycle_events") or []
        lifecycle_rows.sort(key=lambda row: int(row.get("sequence", 0)))
        by_lifecycle: dict[str, dict[str, Any]] = {}
        for row in lifecycle_rows:
            lifecycle_id = row.get("lifecycle_id", "")
            by_lifecycle.setdefault(lifecycle_id, {})[row.get("event", "")] = row
            actor_id = actor_ids.get(lifecycle_id, controller_id)
            kind = {
                "spawned": "spawn",
                "teardown_complete": "teardown",
                "authorization_revoked": "authorization_revoked",
            }.get(row.get("event", ""), "info")
            emit(
                kind,
                f"{row.get('event')} · gen {row.get('generation')}",
                detail=(
                    f"attempt={row.get('attempt_id')} lifecycle={lifecycle_id[:8]}" 
                    if row.get("event") != "spawned"
                    else f"lineage={row.get('lineage_id', '')[:8]} attempt={row.get('attempt_id')}"
                ),
                agent_id=actor_id,
                payload={"journal_row": row},
            )
        # turnover flag interpretation lives in the reducer (adapter is factual)

        # teardown evidence matched by runtime process id
        teardowns = boundary.get("teardowns") or []
        for teardown in teardowns:
            target = controller_id
            for side, record in actors:
                if record.get("runtime_process_id") == teardown.get("runtime_process_id"):
                    identity = record.get("identity") or {}
                    target = actor_ids.get(identity.get("lifecycle_id", ""), controller_id)
                    break
            emit(
                "note",
                "teardown evidence",
                detail=(
                    f"return_code={teardown.get('return_code')} "
                    f"process_absent={teardown.get('process_absent')} "
                    f"group_absent={teardown.get('process_group_absent')} "
                    f"root_removed={teardown.get('private_root_removed')} "
                    f"key_invalidated={teardown.get('key_invalidated')}"
                ),
                agent_id=target,
                payload={"teardown": teardown},
            )

        # carrier record: finalize + signed writer/reader actions
        def action_events(
            action: dict[str, Any] | None, kind_map: dict[str, str], container: str
        ) -> None:
            if not isinstance(action, dict):
                return
            actor_key = action.get("actor_id", "")
            actor_id = ""
            for side, record in actors:
                if (record.get("identity") or {}).get("actor_id") == actor_key:
                    actor_id = actor_ids.get(
                        (record.get("identity") or {}).get("lifecycle_id", ""), ""
                    )
                    break
            name = action.get("action", "?")
            emit(
                kind_map.get(name, "info"),
                f"signed action: {name} · seq {action.get('sequence')}",
                detail=f"payload_hash={str(action.get('payload_hash') or '')[:12]}…",
                agent_id=actor_id or controller_id,
                payload={"container": container, "action": action},
            )

        actions_map = {
            "carrier_write": "artifact_write",
            "carrier_read": "artifact_read",
            "write_canaries": "note",
            "probe_paths": "network_probe",
            "network_probe": "network_probe",
            "provider_request": "provider_request",
            "provider_response_accept": "provider_response",
        }
        for record in boundary.get("carrier_records") or []:
            carrier_id = str(record.get("carrier_id", "carrier"))
            artifact_key = artifact_ids.get(carrier_id)
            if artifact_key:
                writer_action = record.get("writer")
                writer_agent = ""
                if isinstance(writer_action, dict):
                    for side, actor in actors:
                        if (actor.get("identity") or {}).get("actor_id") == writer_action.get("actor_id"):
                            writer_agent = actor_ids.get(
                                (actor.get("identity") or {}).get("lifecycle_id", ""), ""
                            )
                episode.artifacts.append(
                    ViewerArtifact(
                        id=artifact_key,
                        kind="carrier",
                        name=carrier_id,
                        agent_id=writer_agent,
                        content_preview=str(record.get("content_hash", ""))[:16] + "…",
                        lineage_id=str(record.get("lineage_id", "")),
                        generation=int(record.get("generation", 0)),
                        provenance={
                            "writer_action": writer_action,
                            "parent_hashes": record.get("parent_hashes") or [],
                            "content_hash": record.get("content_hash"),
                            "logical_time": record.get("logical_time"),
                            "write_capability_hash": record.get("write_capability_hash"),
                        },
                        attributes={"record": record},
                    )
                )
                carrier = ViewerCarrier(
                    id=stable_id("h1c", carrier_id, width=10),
                    kind="declared",
                    from_agent_id=writer_agent,
                    to_agent_id="",
                    artifact_ids=[artifact_key],
                    capability="read",
                    attributes={
                        "carrier_id": carrier_id,
                        "read_capability_hashes": record.get("read_capability_hashes") or [],
                        "read_count": len(record.get("read_actions") or []),
                    },
                )
                carriers.append(carrier)
            emit(
                "carrier_finalize",
                f"carrier finalized: {carrier_id}",
                detail=f"logical_time={record.get('logical_time')} writer={str(record.get('write_authority'))[:20]}",
                payload={"carrier_record": record},
            )
            if isinstance(record.get("writer"), dict):
                action_events(record["writer"], actions_map, "carrier_writer")
            for read_action in record.get("read_actions") or []:
                action_events(read_action, actions_map, "carrier_read")
                emit(
                    "carrier_read",
                    "carrier read",
                    detail=f"reader={read_action.get('actor_id', '?')}",
                    payload={"carrier_record": {**record, "read_action": read_action}},
                )

        # canary / probes / provider traffic actions (fixed explicit order)
        action_events(boundary.get("predecessor_canary", {}).get("action") if isinstance(boundary.get("predecessor_canary"), dict) else None, actions_map, "canary")
        action_events(boundary.get("successor_path_probe_action"), actions_map, "path_probe")
        action_events(boundary.get("network_probe_action"), actions_map, "network_probe")
        emit(
            "network_probe",
            "network probe result",
            detail=json.dumps(boundary.get("network_probe") or {}, sort_keys=True)[:160],
            payload={"network_probe": boundary.get("network_probe") or {}},
        )
        action_events(boundary.get("provider_request_action"), actions_map, "provider_request")
        action_events(boundary.get("provider_response_acceptance"), actions_map, "provider_acceptance")
        if boundary.get("provider_response_id") is not None:
            episode.artifacts.append(
                ViewerArtifact(
                    id=stable_id("h1art", "provider-response", str(boundary.get("provider_response_id", "")), width=10),
                    kind="provider_response",
                    name=f"response {str(boundary.get('provider_response_id'))[:12]}",
                    content_preview=str(boundary.get("provider_status", "")),
                    provenance={
                        "provider_status": boundary.get("provider_status"),
                        "provider_storage_observed": boundary.get("provider_storage_observed"),
                        "receipt_provider_request_id": (
                            boundary.get("provider_gateway_receipt") or {}
                        ).get("provider_request_id"),
                    },
                )
            )
        for attempt in boundary.get("retry_attempts") or []:
            emit(
                "provider_request",
                "retry attempt",
                detail=(
                    f"outcome={attempt.get('outcome')} phase={attempt.get('dispatch_phase')} "
                    f"wire={str(attempt.get('wire_attempt_id'))[:8]}"
                ),
                agent_id=controller_id,
                payload={"retry_attempt": attempt},
            )
        # gate summary at the end
        emit(
            "note",
            "qualification summary",
            detail=(
                f"status={report.get('status')} · gates {episode.meta['gate_pass']}/"
                f"{len(report.get('gate_results') or {})} · record_hash={str(report.get('record_hash'))[:12]}…"
            ),
            agent_id=controller_id,
            payload={"status": report.get("status"), "record_hash": report.get("record_hash")},
        )

        episode.artifacts.sort(key=lambda a: a.id)
        episode.carriers = carriers
        episode.events = events
        return episode