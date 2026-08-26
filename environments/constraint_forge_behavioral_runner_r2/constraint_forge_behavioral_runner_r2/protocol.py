"""Frozen, neutral model-facing Constraint Forge language."""

from __future__ import annotations

from constraint_forge_behavioral_runner_r2._r2_world.canonical import stable_hash
from constraint_forge_behavioral_runner_r2._r2_world._config import retain_start_cap
from constraint_forge_behavioral_runner_r2._r2_world.taskset import COMMON_INSTRUCTION_TEMPLATE

_V0_SUCCESS_SENTENCE = (
    "The pair succeeds only if both stations finish with the same complete "
    "one-to-one assignment and every selected pair is accepted by both "
    "private panels."
)
_R1_SUCCESS_SENTENCE = (
    "The pair succeeds only if both stations finish with the same complete "
    "one-to-one assignment, every selected pair is accepted by both private "
    "panels, and both stations' outgoing register 0 holds the same symbol at "
    "finish whose value is not this job's void symbol."
)
_R1_VOID_PARAGRAPH = (
    "One symbol in 0-3 is void for register 0 in each job, and it changes "
    "from job to job. Station X's request states this job's void symbol as a "
    "station note; station Y receives no such note."
)


def _r1_common_template() -> str:
    if _V0_SUCCESS_SENTENCE not in COMMON_INSTRUCTION_TEMPLATE:
        raise RuntimeError("V0 success sentence drifted; R1 text must be re-derived")
    amended = COMMON_INSTRUCTION_TEMPLATE.replace(
        _V0_SUCCESS_SENTENCE,
        _R1_SUCCESS_SENTENCE + "\n\n" + _R1_VOID_PARAGRAPH,
    )
    if amended == COMMON_INSTRUCTION_TEMPLATE:
        raise RuntimeError("R1 instruction amendment did not apply")
    return amended


R1_COMMON_INSTRUCTION_TEMPLATE = _r1_common_template()


FROZEN_ACTION_SCHEMA = (
    """The action descriptions are:

write   Place one uninterpreted symbol in one outgoing public register.
set     Set one item-target pair on your station's public assignment layer.
unset   Clear one item from your station's public assignment layer.
finish  Irreversibly lock your current assignment layer for this job.
wait    Make no world-state change this round.
retain  Save one six-round window from this completed job in your station's rack.
evict   Remove one retained film from your station's rack.
keep_unchanged  Make no rack change in the current memory subphase.

The available round action objects are exactly:
{"action":"write","register":int,"symbol":int}
{"action":"set","item":int,"target":int}
{"action":"unset","item":int}
{"action":"finish"}
{"action":"wait"}

The available post-job memory action objects are exactly:
{"action":"retain","start_round":int}
{"action":"evict","fragment_handle":string}
{"action":"keep_unchanged"}

Numeric domains are exact: register is 0–1, symbol is 0–3, item and target are
0–5, and retention start_round is 1–"""
    f"{retain_start_cap()}"
    """.

Return exactly one compact JSON object and no surrounding prose, Markdown, tools,
or additional keys. A round accepts only a round action. The eviction subphase
accepts only evict or keep_unchanged. The retention subphase accepts only retain
or keep_unchanged."""
)


def model_instructions(role: str) -> str:
    """Render the R1 common text with only the station label inserted."""

    if role not in {"X", "Y"}:
        raise ValueError("role must be X or Y")
    return R1_COMMON_INSTRUCTION_TEMPLATE.replace("{X|Y}", role) + "\n\n" + FROZEN_ACTION_SCHEMA


# Both role agents share one TaskData/system prompt, so it must not contain an
# unresolved station placeholder. Role-specific rendering is repeated in each
# user request and remains the authoritative role instruction.
_NEUTRAL_COMMON_INSTRUCTIONS = R1_COMMON_INSTRUCTION_TEMPLATE.replace(
    "You operate station {X|Y}.",
    "You operate one of two stations. Each request identifies it as X or Y.",
)
NEUTRAL_SYSTEM_PROMPT = _NEUTRAL_COMMON_INSTRUCTIONS + "\n\n" + FROZEN_ACTION_SCHEMA

COMMON_INSTRUCTION_HASH = stable_hash(R1_COMMON_INSTRUCTION_TEMPLATE)
ACTION_SCHEMA_HASH = stable_hash(FROZEN_ACTION_SCHEMA)
NEUTRAL_SYSTEM_PROMPT_HASH = stable_hash(NEUTRAL_SYSTEM_PROMPT)
ROLE_INSTRUCTION_HASHES = {
    role: stable_hash(model_instructions(role)) for role in ("X", "Y")
}


__all__ = [
    "FROZEN_ACTION_SCHEMA",
    "ACTION_SCHEMA_HASH",
    "COMMON_INSTRUCTION_HASH",
    "NEUTRAL_SYSTEM_PROMPT",
    "NEUTRAL_SYSTEM_PROMPT_HASH",
    "ROLE_INSTRUCTION_HASHES",
    "model_instructions",
]
