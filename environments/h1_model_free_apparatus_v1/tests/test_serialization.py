import json

import pytest
from pydantic import ValidationError

from h1_model_free_apparatus_v1.canonical import canonical_json, stable_hash
from h1_model_free_apparatus_v1.engine import run_fixture
from h1_model_free_apparatus_v1.fixtures import FIXTURE_MANIFEST
from h1_model_free_apparatus_v1.models import FixtureCase


def test_mapping_order_does_not_change_hash():
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})


def test_fixture_round_trip_and_hash_are_stable():
    outcome = run_fixture(FIXTURE_MANIFEST[0])
    wire = canonical_json(outcome)
    restored = type(outcome).model_validate_json(wire)
    assert restored == outcome
    assert stable_hash(restored) == stable_hash(outcome)


def test_unknown_fields_fail_strict_schema():
    data = FIXTURE_MANIFEST[0].model_dump(mode="python")
    data["secret_leak"] = True
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(data)


def test_nonfinite_numbers_are_not_serializable():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_output_json_is_sorted_and_compact():
    wire = canonical_json({"z": 1, "a": [2, 3]})
    assert wire == '{"a":[2,3],"z":1}'
    assert json.loads(wire) == {"a": [2, 3], "z": 1}


def test_nonstring_mapping_keys_are_rejected_before_hashing():
    with pytest.raises(TypeError):
        stable_hash({1: "ambiguous"})
