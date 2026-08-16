import pytest
from pydantic import ValidationError

from h1_live_runtime_adapter_v1.canonical import sha256_bytes
from h1_live_runtime_adapter_v1.models import (
    CarrierCapability,
    GatewayReceipt,
    ProviderResponse,
    SignedAction,
    StateClass,
)


def _signed_action(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "actor_id": "actor-0",
        "lifecycle_id": "lifecycle-0",
        "session_id": "session-0",
        "generation": 0,
        "lineage_id": "lineage-0",
        "public_key_b64": "unused-in-schema-test",
        "sequence": 1,
        "action_id": "lifecycle-0:1",
        "action": "schema-test",
        "payload_hash": "a" * 64,
        "parent_hashes": ["b" * 64],
        "signature_b64": "unused-in-schema-test",
    }
    values.update(updates)
    return values


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("payload_hash", "not-a-digest"),
        ("parent_hashes", ["not-a-digest"]),
        ("actor_id", "../unsafe"),
        ("action_id", "contains whitespace"),
    ],
)
def test_signed_action_schema_rejects_noncanonical_identity_or_hash_fields(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        SignedAction.model_validate(_signed_action(**{field: value}))


def test_provider_response_receipt_must_bind_the_same_response() -> None:
    output_text = "mechanical-output"
    output_hash = sha256_bytes(output_text.encode())
    receipt = GatewayReceipt(
        gateway_id="gateway-0",
        public_key_b64="unused-in-schema-test",
        logical_attempt_id="attempt-0",
        assignment_hash="a" * 64,
        request_hash="b" * 64,
        response_id="response-0",
        provider_request_id="request-0",
        output_hash=output_hash,
        signature_b64="unused-in-schema-test",
    )
    with pytest.raises(ValidationError, match="gateway receipt differs"):
        ProviderResponse(
            provider="scripted",
            model="mechanical",
            response_id="different-response",
            request_id="request-0",
            output_text=output_text,
            output_hash=output_hash,
            request_hash="b" * 64,
            gateway_receipt=receipt,
        )


def test_gateway_receipt_requires_provider_request_id() -> None:
    values = {
        "gateway_id": "gateway-0",
        "public_key_b64": "unused-in-schema-test",
        "logical_attempt_id": "attempt-0",
        "assignment_hash": "a" * 64,
        "request_hash": "b" * 64,
        "response_id": "response-0",
        "output_hash": sha256_bytes(b"mechanical-output"),
        "signature_b64": "unused-in-schema-test",
    }
    with pytest.raises(ValidationError, match="provider_request_id"):
        GatewayReceipt(**values)


def test_provider_response_requires_provider_request_id() -> None:
    output_text = "mechanical-output"
    with pytest.raises(ValidationError, match="request_id"):
        ProviderResponse(
            provider="scripted",
            model="mechanical",
            response_id="response-0",
            output_text=output_text,
            output_hash=sha256_bytes(output_text.encode()),
            request_hash="b" * 64,
            gateway_receipt=GatewayReceipt(
                gateway_id="gateway-0",
                public_key_b64="unused-in-schema-test",
                logical_attempt_id="attempt-0",
                assignment_hash="a" * 64,
                request_hash="b" * 64,
                response_id="response-0",
                provider_request_id="request-0",
                output_hash=sha256_bytes(output_text.encode()),
                signature_b64="unused-in-schema-test",
            ),
        )


def test_carrier_capability_requires_exactly_one_permission() -> None:
    common = {
        "attempt_id": "attempt-0",
        "actor_id": "actor-0",
        "lifecycle_id": "lifecycle-0",
        "lineage_id": "lineage-0",
        "generation": 0,
        "carrier_id": "carrier-0",
        "carrier_class": StateClass.DECLARED_LINEAGE_CARRIER,
    }
    with pytest.raises(ValidationError, match="exactly one"):
        CarrierCapability.from_fields(**common, can_read=False, can_write=False)
    with pytest.raises(ValidationError, match="exactly one"):
        CarrierCapability.from_fields(**common, can_read=True, can_write=True)
