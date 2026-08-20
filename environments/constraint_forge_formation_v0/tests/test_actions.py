import pytest

from constraint_forge_formation_v0.actions import (
    ActionParseError,
    EvictAction,
    FinishAction,
    RetainAction,
    parse_memory_action,
    parse_world_action,
)


def test_exact_world_union_accepts_protocol_examples() -> None:
    assert parse_world_action('{"action":"write","register":0,"symbol":2}').action == "write"
    assert parse_world_action('{"action":"set","item":4,"target":1}').action == "set"
    assert isinstance(parse_world_action('{"action":"finish"}'), FinishAction)


@pytest.mark.parametrize(
    "text",
    [
        '{"action":"wait","extra":1}',
        '```json\n{"action":"wait"}\n```',
        'prefix {"action":"wait"}',
        '[{"action":"wait"},{"action":"finish"}]',
        '{"action":"unknown"}',
        '{"action":"write","register":0,"symbol":9}',
        '{"action":"wait"} {"action":"finish"}',
    ],
)
def test_parser_rejects_non_exact_actions(text: str) -> None:
    with pytest.raises(ActionParseError):
        parse_world_action(text)


def test_memory_union_is_phase_specific() -> None:
    assert isinstance(parse_memory_action('{"action":"retain","start_round":1}'), RetainAction)
    assert isinstance(parse_memory_action('{"action":"evict","fragment_handle":"h"}'), EvictAction)
    with pytest.raises(ActionParseError):
        parse_world_action('{"action":"retain","start_round":1}')
    with pytest.raises(ActionParseError):
        parse_memory_action('{"action":"set","item":0,"target":0}')
