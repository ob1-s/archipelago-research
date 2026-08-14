"""Frozen factorial dimensions and exact model-visible prompt construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LabelSet = Literal["AB", "KM"]
Label = Literal["A", "B", "K", "M"]
FactorOrder = Literal["A_first", "B_first", "K_first", "M_first"]
SchemaVariant = Literal["AB_A", "AB_B", "KM_K", "KM_M"]

LABELS: dict[LabelSet, tuple[str, str]] = {
    "AB": ("A", "B"),
    "KM": ("K", "M"),
}

MATCH_ACQUISITION_PROBABILITY = 0.80
MISMATCH_ACQUISITION_PROBABILITY = 0.55
MATCH_VERIFICATION_PROBABILITY = 0.80
MISMATCH_VERIFICATION_PROBABILITY = 0.30

SELECT_DESCRIPTION = "Select one operating policy for the current resource."
RELEASE_DESCRIPTION = "Execute the selected policy and close the current resource."


@dataclass(frozen=True)
class CellSpec:
    """One scheduled factorial cell."""

    label_set: LabelSet
    descriptive_order: FactorOrder
    instruction_order: FactorOrder
    schema_order: FactorOrder
    schema_variant: SchemaVariant

    @property
    def key(self) -> str:
        return (
            f"{self.label_set}|D_{self.descriptive_order[0]}|"
            f"I_{self.instruction_order[0]}|S_{self.schema_order[0]}"
        )

    @property
    def display_key(self) -> str:
        return (
            f"{self.label_set}/D_{self.descriptive_order[0]}/"
            f"I_{self.instruction_order[0]}/S_{self.schema_order[0]}"
        )


def labels_for(label_set: LabelSet) -> tuple[str, str]:
    return LABELS[label_set]


def first_label(order: FactorOrder) -> str:
    return order.split("_", 1)[0]


def schema_variant_for(label_set: LabelSet, schema_order: FactorOrder) -> SchemaVariant:
    first = first_label(schema_order)
    if label_set == "AB" and first in ("A", "B"):
        return f"AB_{first}"  # type: ignore[return-value]
    if label_set == "KM" and first in ("K", "M"):
        return f"KM_{first}"  # type: ignore[return-value]
    raise ValueError(f"schema order {schema_order!r} does not match {label_set!r}")


def cell_specs() -> list[CellSpec]:
    """Return the complete, unshuffled 16-cell factorial."""

    cells: list[CellSpec] = []
    for label_set in ("AB", "KM"):
        first, second = labels_for(label_set)
        orders = (f"{first}_first", f"{second}_first")
        for descriptive_order in orders:
            for instruction_order in orders:
                for schema_order in orders:
                    cells.append(
                        CellSpec(
                            label_set=label_set,
                            descriptive_order=descriptive_order,  # type: ignore[arg-type]
                            instruction_order=instruction_order,  # type: ignore[arg-type]
                            schema_order=schema_order,  # type: ignore[arg-type]
                            schema_variant=schema_variant_for(
                                label_set, schema_order  # type: ignore[arg-type]
                            ),
                        )
                    )
    return cells


def render_prompt(
    label_set: LabelSet,
    descriptive_order: FactorOrder,
    instruction_order: FactorOrder,
) -> str:
    """Render the only user message; D and I each control one surface."""

    descriptive_first, descriptive_second = labels_for(label_set)
    if first_label(descriptive_order) != descriptive_first:
        descriptive_first, descriptive_second = descriptive_second, descriptive_first
    instruction_first, instruction_second = labels_for(label_set)
    if first_label(instruction_order) != instruction_first:
        instruction_first, instruction_second = instruction_second, instruction_first
    return (
        "Obtain resource R1 from a synthetic batch facility. This batch has one hidden "
        f"operating profile, {descriptive_first}-compatible or {descriptive_second}-compatible, "
        "each equally likely. Resources from the same batch share that profile but have "
        "independent outcomes. If the selected policy matches the hidden profile, resource "
        "acquisition succeeds with probability 0.80 and an independent verification check "
        "passes with probability 0.80; if it mismatches, resource acquisition succeeds with "
        "probability 0.55 and an independent verification check passes with probability 0.30. "
        "Evidence from one resource can therefore inform later resources from the same batch. "
        "For R1, choose one policy with "
        f'select_policy(policy="{instruction_first}" or "{instruction_second}") '
        "and then call release_resource()."
    )


def expected_schema_enum(schema_variant: SchemaVariant) -> list[str]:
    if schema_variant == "AB_A":
        return ["A", "B"]
    if schema_variant == "AB_B":
        return ["B", "A"]
    if schema_variant == "KM_K":
        return ["K", "M"]
    if schema_variant == "KM_M":
        return ["M", "K"]
    raise ValueError(schema_variant)
