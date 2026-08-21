"""Frozen, neutral model-facing Constraint Forge language."""

from __future__ import annotations

from constraint_forge_formation_v0.canonical import stable_hash
from constraint_forge_formation_v0.taskset import COMMON_INSTRUCTION_TEMPLATE


FROZEN_ACTION_SCHEMA = """The action descriptions are:

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
0–5, and retention start_round is 1–11.

Return exactly one compact JSON object and no surrounding prose, Markdown, tools,
or additional keys. A round accepts only a round action. The eviction subphase
accepts only evict or keep_unchanged. The retention subphase accepts only retain
or keep_unchanged."""


def model_instructions(role: str) -> str:
    """Render the frozen common text with only the station label inserted."""

    if role not in {"X", "Y"}:
        raise ValueError("role must be X or Y")
    return COMMON_INSTRUCTION_TEMPLATE.replace("{X|Y}", role) + "\n\n" + FROZEN_ACTION_SCHEMA


# Both role agents share one TaskData/system prompt, so it must not contain an
# unresolved station placeholder. Role-specific rendering is repeated in each
# user request and remains the authoritative role instruction.
_NEUTRAL_COMMON_INSTRUCTIONS = COMMON_INSTRUCTION_TEMPLATE.replace(
    "You operate station {X|Y}.",
    "You operate one of two stations. Each request identifies it as X or Y.",
)
NEUTRAL_SYSTEM_PROMPT = _NEUTRAL_COMMON_INSTRUCTIONS + "\n\n" + FROZEN_ACTION_SCHEMA

COMMON_INSTRUCTION_HASH = stable_hash(COMMON_INSTRUCTION_TEMPLATE)
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
