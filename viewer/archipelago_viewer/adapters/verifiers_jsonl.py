"""Adapter for verifiers.v1 ``traces.jsonl`` episodes (read-only).

Parses the JSONL directly with stdlib (no verifiers import needed) so the
viewer stays fully decoupled from research code.  One JSON ``Episode`` per
line: ``{"id", "env", "ok", "errors", "traces": [Trace]}``.  Bare ``Trace``
rows (``{"nodes": [...], ...}`` without ``"traces"``) are also supported.

Derivation rules (all deterministic, none invent trajectory facts):

* ``group_mode="community"`` (default) merges all rows of one file into a
  single ``ViewerEpisode``: each trace becomes one agent and the clock is the
  real per-node epoch timestamp, offset so ``t=0`` at the earliest activity.
  This is the "machine society" view over a whole run directory.
* ``group_mode="one"`` emits one episode per file-limited trace (first trace
  of the first row by default), for inspecting a single rollout.
* Nodes become message/tool events in trace order.  Model calls become
  ``provider_request`` events.  Env assay arrays in ``trace.info`` whose items
  carry an integer ``index`` are interleaved at that node's timestamp.
  Read/write-shaped assay items (``notes_read``, ``artifact_read``,
  ``carrier_write``, ...) additionally produce ``artifact_read`` /
  ``artifact_write`` events; everything else stays a typed ``info`` event
  with the verbatim payload.
* Artifacts come from ``task.data`` (artifacts / resources / notes file) with
  provenance copied from ``trace.info`` (writer rollout, presentation order,
  exact inherited state) — never synthesized.
"""

from __future__ import annotations

import json
from typing import Any

from .base import Adapter
from ..schema import ViewerAgent, ViewerArtifact, ViewerEvent, ViewerEpisode
from ..util import fold_text, stable_id

_READ_KINDS = {
    "notes_read",
    "artifact_read",
    "read",
    "carrier_read",
    "predecessor_artifact_read",
    "exact_artifact_state_read",
    "exact_inherited_state_read",
}
_WRITE_KINDS = {
    "notes_write",
    "artifact_write",
    "write",
    "carrier_write",
    "successor_facing_write",
}

_ASSAY_KEYS = (
    "policy_events",
    "events",
    "phase1_events",
    "phase2_events",
    "behavior_after_first_notes_read",
    "behavior_after_first_artifact_read",
    "all_notes_reads",
    "successor_facing_writes",
    "exact_artifact_state_read",
    "exact_inherited_state_read",
    "transmission_events",
)


def _now_utc() -> str:
    from ..util import now_utc
    return now_utc()


def _node_time(nodes: list[dict[str, Any]], index: int, fallback: float) -> float:
    if 0 <= index < len(nodes):
        ts = nodes[index].get("timestamp")
        if isinstance(ts, (int, float)):
            return float(ts)
    return fallback


def _message_fields(node: dict[str, Any]) -> dict[str, Any]:
    message = node.get("message") or {}
    fields: dict[str, Any] = {
        "role": message.get("role", "unknown"),
    }
    if message.get("content") is not None:
        fields["content"] = message["content"]
    if message.get("reasoning_content"):
        fields["reasoning_content"] = message["reasoning_content"]
    calls = message.get("tool_calls")
    if calls:
        fields["tool_calls"] = [
            {"name": c.get("name", "?"), "arguments": c.get("arguments", "{}")}
            for c in calls
        ]
    return fields


class VerifiersTracesAdapter(Adapter):
    name = "verifiers-traces.jsonl"
    extensions = (".jsonl", ".jsonl.gz")

    @classmethod
    def _probe(cls, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                row = json.loads(fh.readline())
        except (OSError, json.JSONDecodeError):
            return False
        return "traces" in row or "nodes" in row

    @classmethod
    def load(
        cls,
        path: str,
        limit: int | None = None,
        group_mode: str = "community",
    ) -> list[ViewerEpisode]:
        rows: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if limit and len(rows) >= limit:
                    break
        traces: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for row in rows:
            row_traces = row.get("traces")
            if isinstance(row_traces, list):
                for tr in row_traces:
                    traces.append((tr, row))
            elif isinstance(row.get("nodes"), list):
                traces.append((row, {"env": row.get("env", {}), "id": row.get("id")}))
        if not traces:
            return []
        if group_mode == "one":
            tr, row = traces[0]
            return [cls._single(tr, row, path)]
        return [cls._community(traces, path)]

    # ------------------------------------------------------------------ single

    @classmethod
    def _single(
        cls, tr: dict[str, Any], row: dict[str, Any], path: str
    ) -> ViewerEpisode:
        nodes = tr.get("nodes") or []
        return cls._build(
            episode_id=stable_id("ep", tr.get("id", "trace"), width=12),
            title=f"{cls._task_name(tr)} — {tr.get('id', '')[:8]}",
            tr=tr,
            row=row,
            path=path,
            all_traces=[tr],
            nodes=nodes,
        )

    @classmethod
    def _community(
        cls, traces: list[tuple[dict[str, Any], dict[str, Any]]], path: str
    ) -> ViewerEpisode:
        first_tr, first_row = traces[0]
        env_id = (first_row.get("env") or {}).get("id", "?")
        conditions: dict[str, int] = {}
        for tr, _row in traces:
            condition = cls._condition(tr)
            conditions[condition] = conditions.get(condition, 0) + 1
        title = (
            f"{env_id} · {len(traces)} rollouts"
            + (f" · {', '.join(f'{k}={v}' for k, v in sorted(conditions.items()))}" if conditions else "")
        )
        all_nodes = [tr.get("nodes") or [] for tr, _row in traces]
        return cls._build(
            episode_id=stable_id("com", path, width=12),
            title=title,
            tr=first_tr,
            row=first_row,
            path=path,
            all_traces=[tr for tr, _row in traces],
            nodes=sum(all_nodes, []),  # only for t0 / fallback clock
        )

    # ------------------------------------------------------------------ build

    @classmethod
    def _build(
        cls,
        episode_id: str,
        title: str,
        tr: dict[str, Any],
        row: dict[str, Any],
        path: str,
        all_traces: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
    ) -> ViewerEpisode:
        agent_config = tr.get("agent") or {}
        model = cls._model_name(agent_config)
        task = tr.get("task") or {}
        task_data = task.get("data") or {}
        task_name = task_data.get("name") or task.get("type", "")
        env_id = (row.get("env") or {}).get("id", "?")

        episode = ViewerEpisode(
            id=episode_id,
            title=title,
            environment=env_id,
            model=model,
            source=cls.describe(path),
            source_kind=cls.name,
            generated_at=_now_utc(),
        )
        episode.meta = {
            "task": task_name,
            "condition": cls._condition(tr),
            "trace_count": len(all_traces),
            "run": (tr.get("run") or {}).get("id", ""),
            "stop_condition": tr.get("stop_condition"),
            "ok": bool(tr.get("ok")),
            "rewards": tr.get("rewards") or {},
            "timing": tr.get("timing") or {},
        }

        # ---- agents (one per trace in community mode)
        per_trace = [tr] + [t for t in all_traces if t is not tr]
        for i, trace in enumerate(per_trace):
            cfg = trace.get("agent") or {}
            trace_id = trace.get("id", f"trace-{i}")
            model_name = cls._model_name(cfg)
            episode.agents.append(
                ViewerAgent(
                    id=stable_id("ag", trace_id, width=10),
                    name=cfg.get("name") or f"agent-{i}",
                    role="assistant",
                    generation=0,
                    source_id=trace_id,
                    attributes={
                        "model": model_name,
                        "trace_ok": bool(trace.get("ok")),
                        "stop_condition": trace.get("stop_condition"),
                        "num_turns": len(trace.get("nodes") or []),
                    },
                )
            )
        agent_ids = {a.source_id: a.id for a in episode.agents}

        # ---- artifacts from task data + assay provenance
        artifacts: dict[str, ViewerArtifact] = {}
        for item in task_data.get("artifacts") or []:
            cls._add_task_artifact(artifacts, item, task_data)
        for item in task_data.get("resources") or []:
            cls._add_task_artifact(artifacts, item, task_data, fallback_kind="resource")
        notes_path = task_data.get("notes_path") or "notes.txt"
        if notes_path and not any(a.name == notes_path for a in artifacts.values()):
            artifacts[stable_id("art", "note", notes_path, width=10)] = ViewerArtifact(
                id=stable_id("art", "note", notes_path, width=10),
                kind="note",
                name=str(notes_path),
                content_preview=fold_text(str(task_data.get("initial_notes") or ""), 200),
            )

        # ---- event stream
        events: list[ViewerEvent] = []
        t0 = min(
            (
                float(node.get("timestamp"))
                for trace in per_trace
                for node in (trace.get("nodes") or [])
                if isinstance(node.get("timestamp"), (int, float))
            ),
            default=0.0,
        )
        seq = 0

        def emit(
            kind: str,
            t: float,
            title: str,
            detail: str = "",
            agent_key: str = "",
            payload: dict[str, Any] | None = None,
        ) -> ViewerEvent:
            nonlocal seq
            event = ViewerEvent(
                seq=seq,
                t=max(0.0, t - t0),
                kind=kind,
                agent_id=agent_ids.get(agent_key, "") if agent_key else "",
                title=title,
                detail=detail,
                payload=dict(payload or {}),
            )
            events.append(event)
            seq += 1
            return event

        # node times per trace (for assay interleaving)
        node_times: dict[str, list[float]] = {}
        fallback_clocks: dict[str, float] = {}
        for trace in per_trace:
            trace_nodes = trace.get("nodes") or []
            times: list[float] = []
            for node in trace_nodes:
                ts = node.get("timestamp")
                if isinstance(ts, (int, float)):
                    times.append(float(ts))
                else:
                    times.append(times[-1] + 1.0 if times else t0)
            node_times[trace.get("id", "")] = times
            fallback_clocks[trace.get("id", "")] = (times[-1] + 1.0) if times else t0

        for trace in per_trace:
            trace_id = trace.get("id", "")
            rk = trace.get("run") or {}
            run_id = rk.get("id", "")
            agent_key = trace_id
            agent_id = agent_ids.get(agent_key, "")
            trace_nodes = trace.get("nodes") or []
            times = node_times.get(trace_id, [])
            for i, node in enumerate(trace_nodes):
                t = times[i] if i < len(times) else fallback_clocks.get(trace_id, t0)
                fields = _message_fields(node)
                role = fields["role"]
                if role == "user":
                    emit("user_message", t, "user message",
                         detail=fold_text(
                             cls._text_of(fields.get("content", "")), 160
                         ),
                         payload=fields)
                elif role == "assistant":
                    text = fold_text(str(fields.get("content") or ""), 200)
                    calls = fields.get("tool_calls") or []
                    emit(
                        "assistant_message",
                        t,
                        "assistant",
                        detail=text or (f"{len(calls)} tool call(s)" if calls else ""),
                        agent_key=agent_key,
                        payload=fields,
                    )
                    for call in calls:
                        emit(
                            "tool_call",
                            t,
                            f"tool_call {call.get('name', '?')}",
                            detail=str(call.get("arguments", "{}"))[:160],
                            agent_key=agent_key,
                            payload={"name": call.get("name"), "arguments": call.get("arguments")},
                        )
                elif role == "tool":
                    emit(
                        "tool_result",
                        t,
                        "tool result",
                        detail=fold_text(
                            cls._text_of(fields.get("content", "")), 180
                        ),
                        agent_key=agent_key,
                        payload=fields,
                    )
                elif role == "system":
                    emit(
                        "system_message",
                        t,
                        "system message",
                        detail=fold_text(
                            cls._text_of(fields.get("content", "")), 160
                        ),
                        payload=fields,
                    )

            # model calls
            for call in trace.get("calls") or []:
                node_index = call.get("node")
                t = (
                    times[node_index]
                    if isinstance(node_index, int) and 0 <= node_index < len(times)
                    else fallback_clocks.get(trace_id, t0)
                )
                usage = call.get("usage") or {}
                time_span = call.get("time") or {}
                emit(
                    "provider_request",
                    t,
                    "model call",
                    detail=(
                        f"{call.get('model', '?')} · {call.get('finish_reason') or '?'} "
                        f"· {usage.get('completion_tokens', 0)} out"
                    ),
                    agent_key=agent_key,
                    payload={
                        "model": call.get("model"),
                        "endpoint": call.get("endpoint"),
                        "finish_reason": call.get("finish_reason"),
                        "usage": usage,
                        "time": time_span,
                    },
                )

            # assay arrays from info: interleave by node index
            info = trace.get("info") or {}
            for key, value in info.items():
                if not isinstance(value, list) or key not in _ASSAY_KEYS:
                    continue
                for position, item in enumerate(value):
                    if not isinstance(item, dict):
                        continue
                    index = item.get("index")
                    if isinstance(index, int) and 0 <= index < len(times):
                        t = times[index]
                    else:
                        t = fallback_clocks.get(trace_id, t0) + 0.001 * position
                    if cls._is_read(item):
                        kind_event = "artifact_read"
                    elif cls._is_write(item):
                        kind_event = "artifact_write"
                    else:
                        kind_event = None
                    if kind_event is not None:
                        emit(
                            kind_event,
                            t,
                            f"{item.get('kind', '?')} {item.get('argument', '')}"[:80],
                            detail=fold_text(str(item.get("result") or ""), 140),
                            agent_key=agent_key,
                            payload={"assay": key, "record": item},
                        )
                    else:
                        emit(
                            "info",
                            t,
                            f"{key} #{item.get('index', position)} {item.get('kind', '')}".strip(),
                            detail=fold_text(str(item.get("result") or item.get("argument") or ""), 140),
                            agent_key=agent_key,
                            payload={"assay": key, "record": item},
                        )

            # phase markers derived from assay fields (verbatim values only)
            exposure_index = info.get("exposure_event_index")
            if isinstance(exposure_index, int) and 0 <= exposure_index < len(times):
                emit(
                    "phase",
                    times[exposure_index],
                    "phase2 exposure delivered",
                    detail=fold_text(str(info.get("exposure_text") or ""), 120),
                    agent_key=agent_key,
                    payload={"exposure_text": info.get("exposure_text")},
                )
            transition = info.get("transition")
            if isinstance(transition, str) and transition:
                emit(
                    "phase",
                    times[-1] if times else t0,
                    f"transition: {transition}",
                    agent_key=agent_key,
                    payload={"transition": transition},
                )

            # phase-machine state reported verbatim when present (no synthesis)
            postcommitment = info.get("postcommitment_policy")
            if isinstance(postcommitment, dict):
                summary = ", ".join(
                    f"{k}={postcommitment.get(k)}"
                    for k in (
                        "assignment_stage",
                        "phase1_policy",
                        "phase1_success",
                        "phase2_policy",
                        "phase2_success",
                        "transition",
                    )
                    if k in postcommitment
                )
                emit(
                    "info",
                    fallback_clocks.get(trace_id, t0),
                    "postcommitment policy state",
                    detail=fold_text(summary, 160),
                    agent_key=agent_key,
                    payload={"postcommitment_policy": postcommitment},
                )

            # artifact-inheritance metadata reported verbatim when present
            transmission = info.get("policy_transmission")
            if isinstance(transmission, dict):
                first_read = transmission.get("first_artifact_read_index")
                if isinstance(first_read, int) and 0 <= first_read < len(times):
                    emit(
                        "artifact_read",
                        times[first_read],
                        "first artifact read (harness)",
                        detail=(
                            f"writer_rollout={transmission.get('artifact_writer_rollout')} "
                            f"provenance={transmission.get('artifact_provenance')}"
                        ),
                        agent_key=agent_key,
                        payload={"policy_transmission": transmission},
                    )
                emit(
                    "info",
                    fallback_clocks.get(trace_id, t0),
                    "policy transmission state",
                    detail=fold_text(
                        f"condition={transmission.get('condition')} "
                        f"available={transmission.get('artifact_available')} "
                        f"writer={transmission.get('artifact_writer_rollout')} "
                        f"provenance={transmission.get('artifact_provenance')}",
                        160,
                    ),
                    agent_key=agent_key,
                    payload={"policy_transmission": transmission},
                )

            # rewards / metrics / stop
            for name, reward in (trace.get("rewards") or {}).items():
                if isinstance(reward, dict):
                    emit(
                        "reward",
                        fallback_clocks.get(trace_id, t0),
                        f"reward {name}",
                        detail=f"score={reward.get('score')} weight={reward.get('weight')}",
                        agent_key=agent_key,
                        payload={"name": name, **reward},
                    )
                else:
                    emit(
                        "reward",
                        fallback_clocks.get(trace_id, t0),
                        f"reward {name}",
                        detail=f"score={reward}",
                        agent_key=agent_key,
                        payload={"name": name, "score": reward},
                    )
            for name, value in (trace.get("metrics") or {}).items():
                emit(
                    "metric",
                    fallback_clocks.get(trace_id, t0),
                    f"metric {name}",
                    detail=f"value={value}",
                    agent_key=agent_key,
                    payload={"name": name, "value": value},
                )
            emit(
                "stop",
                fallback_clocks.get(trace_id, t0),
                "trace end",
                detail=f"stop_condition={trace.get('stop_condition')} ok={trace.get('ok')}",
                agent_key=agent_key,
                payload={
                    "stop_condition": trace.get("stop_condition"),
                    "is_completed": trace.get("is_completed"),
                    "ok": trace.get("ok"),
                    "errors": trace.get("errors") or [],
                },
            )

        # ---- artifact write linkage (provenance from assay records)
        cls._link_artifacts(episode, artifacts, events)
        episode.artifacts = sorted(artifacts.values(), key=lambda a: a.id)
        episode.events = events
        return episode

    # ---------------------------------------------------------- small helpers

    @staticmethod
    def _text_of(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", item)))
                else:
                    parts.append(str(item))
            return " ".join(parts)
        return str(content or "")

    @staticmethod
    def _is_read(item: dict[str, Any]) -> bool:
        kind = str(item.get("kind") or "")
        if kind in _READ_KINDS:
            return True
        key = str(item.get("key") or "")
        return "read" in key or kind.endswith("_read")

    @staticmethod
    def _is_write(item: dict[str, Any]) -> bool:
        kind = str(item.get("kind") or "")
        if kind in _WRITE_KINDS:
            return True
        key = str(item.get("key") or "")
        return "write" in key or kind.endswith("_write")

    @staticmethod
    def _condition(tr: dict[str, Any]) -> str:
        task_data = (tr.get("task") or {}).get("data") or {}
        return str(
            task_data.get("condition")
            or task_data.get("assigned_condition")
            or (tr.get("info") or {}).get("condition")
            or ""
        )

    @staticmethod
    def _task_name(tr: dict[str, Any]) -> str:
        task = tr.get("task") or {}
        data = task.get("data") or {}
        return str(data.get("name") or task.get("type") or "task")

    @staticmethod
    def _model_name(agent_config: dict[str, Any]) -> str:
        for key in ("model", "model_id"):
            value = agent_config.get(key)
            if isinstance(value, str) and value:
                return value
        client = agent_config.get("client") or {}
        for key in ("model", "model_id"):
            value = client.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @classmethod
    def _add_task_artifact(
        cls,
        artifacts: dict[str, ViewerArtifact],
        item: Any,
        task_data: dict[str, Any],
        fallback_kind: str = "artifact",
    ) -> None:
        if isinstance(item, str):
            name = item
            kind = fallback_kind
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or item.get("kind") or "?")
            kind = str(item.get("kind") or fallback_kind)
        else:
            return
        if not name or name == "?":
            return
        key = stable_id("art", str(task_data.get("name", "")), name, width=10)
        if key not in artifacts:
            artifacts[key] = ViewerArtifact(
                id=key, kind=kind, name=name, content_preview=""
            )

    @staticmethod
    def _link_artifacts(
        episode: ViewerEpisode,
        artifacts: dict[str, ViewerArtifact],
        events: list[ViewerEvent],
    ) -> None:
        by_name: dict[str, ViewerArtifact] = {
            artifact.name: artifact for artifact in artifacts.values()
        }
        for event in events:
            if event.kind not in ("artifact_read", "artifact_write"):
                continue
            record = event.payload.get("record") or {}
            argument = str(record.get("argument") or "")
            target = by_name.get(argument) or by_name.get(
                argument.split("/")[-1].split(".")[0]
            )
            event.payload["artifact_id"] = target.id if target else ""
            if target and event.kind == "artifact_write" and target.created_at == -1:
                target.created_at = event.seq
                target.agent_id = event.agent_id
                target.provenance.setdefault("writes", []).append(
                    {"seq": event.seq, "record": record}
                )
            if target and event.kind == "artifact_read":
                target.provenance.setdefault("reads", []).append(
                    {"seq": event.seq, "agent_id": event.agent_id, "record": record}
                )