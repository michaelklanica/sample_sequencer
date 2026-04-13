from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    label: str
    description: str
    is_common: bool = True


TEMPLATE_DEFINITIONS: tuple[TemplateDefinition, ...] = (
    TemplateDefinition(
        template_id="straight_2",
        label="Straight 2",
        description="Split selected leaf into 2 equal parts.",
        is_common=True,
    ),
    TemplateDefinition(
        template_id="straight_4",
        label="Straight 4",
        description="Split selected leaf into 4 equal parts.",
        is_common=True,
    ),
    TemplateDefinition(
        template_id="triplet_3",
        label="Triplet 3",
        description="Split selected leaf into 3 equal parts.",
        is_common=True,
    ),
    TemplateDefinition(
        template_id="quintuplet_5",
        label="Quintuplet 5",
        description="Split selected leaf into 5 equal parts.",
        is_common=True,
    ),
    TemplateDefinition(
        template_id="sextuplet_6",
        label="Sextuplet 6",
        description="Split selected leaf into 6 equal parts.",
        is_common=True,
    ),
    TemplateDefinition(
        template_id="four_last_triplet",
        label="4 + last split into 3",
        description="Split into 4, then subdivide the last part into 3.",
        is_common=False,
    ),
    TemplateDefinition(
        template_id="four_middle_triplet",
        label="4 + middle split into 3",
        description="Split into 4, then subdivide the middle part into 3.",
        is_common=False,
    ),
)


TEMPLATE_BY_ID: dict[str, TemplateDefinition] = {definition.template_id: definition for definition in TEMPLATE_DEFINITIONS}
COMMON_TEMPLATE_IDS: tuple[str, ...] = ("straight_2", "triplet_3", "straight_4")
