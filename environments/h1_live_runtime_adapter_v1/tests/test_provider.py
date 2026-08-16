"""Provider-boundary tests.

These tests exercise only signed mechanical requests and faked transports.  No
test in this module contacts a provider or asks a model to generate output.
The request fixture mirrors the actor's narrow ``provider_request`` action so
that gateway authentication is tested without giving tests a private actor
key or adding a production signing escape hatch.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from openai import RateLimitError
from pydantic import ValidationError

from h1_live_runtime_adapter_v1.attribution import ActionRegistry
from h1_live_runtime_adapter_v1.canonical import canonical_bytes, sha256_bytes, stable_hash
from h1_live_runtime_adapter_v1.models import (
    ActorIdentity,
    ActorSpec,
    ProviderPolicy,
    ProviderRequest,
    ProviderResponse,
    SignedAction,
)
from h1_live_runtime_adapter_v1.provider import (
    AmbiguousDeliveryError,
    InvalidProviderResponseError,
    OpenAIResponsesBackend,
    ProviderGateway,
    ProviderRejectedError,
    SafeToRetryError,
    ScriptedMechanicalBackend,
)


ACTION_DOMAIN = b"h1-live-runtime-action/v1\0"
REGISTRATION_DOMAIN = b"h1-live-runtime-registration/v1\0"
_USE_FIXTURE_RECEIPT_KEY = object()


def _public_key(private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()


@dataclass
class RequestFixture:
    request: ProviderRequest
    registry: ActionRegistry
    policy: ProviderPolicy
    private_key: Ed25519PrivateKey
    identity: ActorIdentity
    receipt_private_key: Ed25519PrivateKey

    @property
    def actor_spec(self) -> ActorSpec:
        return ActorSpec(
            actor_id=self.identity.actor_id,
            lifecycle_id=self.identity.lifecycle_id,
            generation=self.identity.generation,
            lineage_id=self.identity.lineage_id,
            position=self.identity.position,
            gateway_public_key_b64=_public_key(self.receipt_private_key),
        )


def _fixture(*, policy: ProviderPolicy | None = None) -> RequestFixture:
    """Create one independently registered, actor-authored request."""

    suffix = uuid4().hex
    policy = policy or ProviderPolicy(
        base_url="https://provider.invalid/v1", model="mechanical-test-model"
    )
    actor_id = f"actor-{suffix}"
    lifecycle_id = f"lifecycle-{suffix}"
    session_id = f"session-{suffix}"
    lineage_id = f"lineage-{suffix}"
    private_key = Ed25519PrivateKey.generate()
    receipt_private_key = Ed25519PrivateKey.generate()
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    input_messages = ({"role": "user", "content": "mechanical canary"},)
    attempt_id = f"attempt-{suffix}"
    assignment_hash = stable_hash({"attempt_id": attempt_id, "frozen": True})
    common_prior_hashes = {"runtime": stable_hash("common-prior-v1")}
    semantic_payload = {
        "policy": policy.model_dump(mode="json"),
        "input": list(input_messages),
        "instructions": None,
        "attempt_id": attempt_id,
        "assignment_hash": assignment_hash,
        "common_prior_hashes": common_prior_hashes,
    }
    payload_hash = stable_hash(semantic_payload)
    unsigned = {
        "actor_id": actor_id,
        "lifecycle_id": lifecycle_id,
        "session_id": session_id,
        "generation": 0,
        "lineage_id": lineage_id,
        "public_key_b64": public_key_b64,
        "sequence": 1,
        "action_id": f"{lifecycle_id}:1",
        "action": "provider_request",
        "payload_hash": payload_hash,
        "parent_hashes": [],
    }
    signature_b64 = base64.b64encode(
        private_key.sign(ACTION_DOMAIN + canonical_bytes(unsigned))
    ).decode()
    action = SignedAction(**unsigned, signature_b64=signature_b64)
    request = ProviderRequest(
        action=action,
        policy=policy,
        input=input_messages,
        instructions=None,
        attempt_id=attempt_id,
        assignment_hash=assignment_hash,
        common_prior_hashes=common_prior_hashes,
    )
    identity_values = dict(
        actor_id=actor_id,
        lifecycle_id=lifecycle_id,
        generation=0,
        lineage_id=lineage_id,
        position="test",
        gateway_public_key_b64=_public_key(receipt_private_key),
        session_id=session_id,
        public_key_b64=public_key_b64,
        namespace_pid=1,
        namespace_process_start_ticks=1,
        environment_fingerprint=stable_hash("test-environment"),
        environment_names=(),
        namespace_ids={},
        effective_capabilities_hex="0",
        no_new_privileges=True,
        open_extra_fd_count=0,
        open_extra_fd_targets={},
    )
    registration_signature_b64 = base64.b64encode(
        private_key.sign(REGISTRATION_DOMAIN + canonical_bytes(identity_values))
    ).decode()
    identity = ActorIdentity(
        **identity_values, registration_signature_b64=registration_signature_b64
    )
    registry = ActionRegistry()
    registry.register(identity)
    return RequestFixture(
        request=request,
        registry=registry,
        policy=policy,
        private_key=private_key,
        identity=identity,
        receipt_private_key=receipt_private_key,
    )


def _resign_request(
    fixture: RequestFixture, *, sequence: int = 2, **changes: Any
) -> ProviderRequest:
    values = {
        "policy": fixture.request.policy,
        "input": fixture.request.input,
        "instructions": fixture.request.instructions,
        "attempt_id": fixture.request.attempt_id,
        "assignment_hash": fixture.request.assignment_hash,
        "common_prior_hashes": fixture.request.common_prior_hashes,
    }
    values.update(changes)
    semantic_payload = {
        "policy": values["policy"].model_dump(mode="json"),
        "input": list(values["input"]),
        "instructions": values["instructions"],
        "attempt_id": values["attempt_id"],
        "assignment_hash": values["assignment_hash"],
        "common_prior_hashes": values["common_prior_hashes"],
    }
    action_values = fixture.request.action.model_dump(
        mode="python", exclude={"signature_b64"}
    )
    action_values.update(
        sequence=sequence, action_id=f"{fixture.identity.lifecycle_id}:{sequence}"
    )
    action_values["payload_hash"] = stable_hash(semantic_payload)
    signature = base64.b64encode(
        fixture.private_key.sign(ACTION_DOMAIN + canonical_bytes(action_values))
    ).decode()
    return ProviderRequest(
        **values,
        action=SignedAction(**action_values, signature_b64=signature),
    )


def _response(request: ProviderRequest, *, request_hash: str | None = None, **changes: Any) -> ProviderResponse:
    output_text = "mechanical provider response"
    values: dict[str, Any] = {
        "provider": "fake-provider",
        "model": request.policy.model,
        "response_id": f"response-{uuid4().hex}",
        "request_id": f"request-{uuid4().hex}",
        "output_text": output_text,
        "output_hash": sha256_bytes(output_text.encode()),
        "request_hash": request.semantic_hash() if request_hash is None else request_hash,
        "store_requested": False,
        "provider_storage_observed": False,
        "previous_response_id": None,
        "conversation_id": None,
        "tool_calls": 0,
    }
    response = ProviderResponse(**values)
    # model_copy deliberately bypasses validation so the gateway's defensive
    # revalidation is exercised for adversarial backend objects.
    return response.model_copy(update=changes)


class _SequenceBackend:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self, request: ProviderRequest, wire_attempt_id: str) -> Any:
        assert wire_attempt_id.startswith(f"{request.attempt_id}:wire:")
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return await outcome(request)
        return outcome


def _gateway(
    fixture: RequestFixture,
    *,
    expected: ProviderPolicy | None = None,
    registry: ActionRegistry | None = None,
    expected_common_prior_hashes: dict[str, str] | None = None,
    expected_assignment_hashes: dict[str, str] | None = None,
    expected_request_hashes: dict[str, str] | None = None,
    expected_actor_specs: dict[str, ActorSpec] | None = None,
    ledger_path: Path | None = None,
    receipt_private_key: Ed25519PrivateKey | None | object = _USE_FIXTURE_RECEIPT_KEY,
    max_safe_retries: int = 0,
) -> ProviderGateway:
    if receipt_private_key is _USE_FIXTURE_RECEIPT_KEY:
        receipt_private_key = fixture.receipt_private_key
    return ProviderGateway(
        registry or fixture.registry,
        expected_policy=expected or fixture.policy,
        ledger_path=ledger_path,
        expected_common_prior_hashes=expected_common_prior_hashes
        or fixture.request.common_prior_hashes,
        expected_assignment_hashes=expected_assignment_hashes
        or {fixture.request.attempt_id: fixture.request.assignment_hash},
        expected_request_hashes=expected_request_hashes
        or {fixture.request.attempt_id: fixture.request.semantic_hash()},
        expected_actor_specs=expected_actor_specs
        or {fixture.request.attempt_id: fixture.actor_spec},
        receipt_private_key=receipt_private_key,
        max_safe_retries=max_safe_retries,
    )


def test_provider_request_has_actor_authorship_and_tampering_is_rejected() -> None:
    fixture = _fixture()
    assert fixture.request.action.action == "provider_request"
    assert fixture.request.action.payload_hash == fixture.request.semantic_hash()

    tampered_signature = fixture.request.action.model_copy(
        update={"signature_b64": base64.b64encode(b"not-a-signature").decode()}
    )
    tampered = fixture.request.model_copy(update={"action": tampered_signature})
    with pytest.raises(ValueError, match="active actor authorization|not registered"):
        asyncio.run(_gateway(fixture).execute(tampered, _SequenceBackend(_response(tampered))))


def test_provider_request_payload_hash_mismatch_is_rejected_at_model_boundary() -> None:
    fixture = _fixture()
    invalid_action = fixture.request.action.model_copy(
        update={"payload_hash": stable_hash("different-request")}
    )
    with pytest.raises(ValidationError, match="signed provider request hash mismatch"):
        ProviderRequest.model_validate(fixture.request.model_copy(update={"action": invalid_action}))


@pytest.mark.asyncio
async def test_policy_pin_rejects_a_different_provider_contract() -> None:
    fixture = _fixture()
    pinned = ProviderPolicy(
        base_url=fixture.policy.base_url,
        model="different-mechanical-model",
    )
    with pytest.raises(ValueError, match="pinned gateway policy"):
        await _gateway(fixture, expected=pinned).execute(
            fixture.request, _SequenceBackend(_response(fixture.request))
        )


@pytest.mark.asyncio
async def test_common_prior_pin_rejects_changed_source_hashes() -> None:
    fixture = _fixture()
    gateway = _gateway(
        fixture,
        expected_common_prior_hashes={"runtime": stable_hash("different")},
    )
    with pytest.raises(ValueError, match="common priors"):
        await gateway.execute(
            fixture.request, _SequenceBackend(_response(fixture.request))
        )


@pytest.mark.asyncio
async def test_caller_forgeable_pre_dispatch_error_is_terminal() -> None:
    fixture = _fixture()
    backend = _SequenceBackend(
        SafeToRetryError("caller cannot prove pre-dispatch failure"),
        _response(fixture.request),
    )
    gateway = _gateway(fixture)
    with pytest.raises(SafeToRetryError):
        await gateway.execute(fixture.request, backend)

    assert backend.calls == 1
    assert len(gateway.attempts) == 1
    assert gateway.attempts[0].retryable is False
    assert gateway.attempts[0].dispatch_phase == "unknown"


@pytest.mark.asyncio
async def test_safe_rate_limit_retry_budget_is_terminal_when_exhausted() -> None:
    fixture = _fixture()
    backend = _SequenceBackend(SafeToRetryError("429"))
    gateway = _gateway(fixture)
    with pytest.raises(ValueError, match="retry budget is frozen"):
        await gateway.execute(fixture.request, backend, max_safe_retries=1)
    assert backend.calls == 0


def test_retry_budget_is_nonnegative_and_frozen_at_gateway_creation() -> None:
    fixture = _fixture()
    with pytest.raises(ValueError, match="freezes the retry budget"):
        _gateway(fixture, max_safe_retries=1)
    with pytest.raises(ValueError, match="nonnegative"):
        _gateway(fixture, max_safe_retries=-1)
    with pytest.raises(ValueError, match="nonnegative"):
        _gateway(fixture, max_safe_retries=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: asyncio.TimeoutError("timeout"),
        lambda: httpx.ReadTimeout("transport timeout"),
        lambda: httpx.ConnectError("transport failure"),
        lambda: ValueError("malformed provider response"),
        lambda: RuntimeError("backend crashed"),
    ],
    ids=["timeout", "transport-timeout", "transport-error", "malformed", "crash"],
)
async def test_timeout_transport_malformed_and_crash_are_terminal(
    error_factory: Callable[[], BaseException],
) -> None:
    fixture = _fixture()
    backend = _SequenceBackend(error_factory())
    gateway = _gateway(fixture)
    with pytest.raises(type(error_factory())):
        await gateway.execute(fixture.request, backend)
    assert backend.calls == 1
    assert len(gateway.attempts) == 1
    assert gateway.attempts[0].retryable is False
    assert gateway.attempts[0].outcome.endswith("_terminal")


@pytest.mark.asyncio
async def test_cancellation_is_terminal_and_not_retried() -> None:
    fixture = _fixture()
    backend = _SequenceBackend(asyncio.CancelledError())
    gateway = _gateway(fixture)
    with pytest.raises(asyncio.CancelledError):
        await gateway.execute(fixture.request, backend)
    assert backend.calls == 1
    assert gateway.attempts[0].outcome == "cancelled_unknown_delivery"
    assert gateway.attempts[0].retryable is False


@pytest.mark.asyncio
async def test_response_request_hash_mismatch_is_rejected() -> None:
    fixture = _fixture()
    gateway = _gateway(fixture)
    wrong_hash = stable_hash("different-request-hash")
    with pytest.raises(ValueError, match="request hash mismatch"):
        await gateway.execute(
            fixture.request,
            _SequenceBackend(_response(fixture.request, request_hash=wrong_hash)),
        )


def test_stateless_policy_rejects_continuation_tools_storage_and_retries() -> None:
    base = {"base_url": "https://provider.invalid/v1", "model": "mechanical-test-model"}
    assert ProviderPolicy(**base).model_dump(mode="json") == {
        "adapter": "openai_responses_stateless_v1",
        "base_url": base["base_url"],
        "model": base["model"],
        "store": False,
        "previous_response_id": None,
        "conversation": None,
        "tools": [],
        "background": False,
        "stream": False,
        "include": [],
        "max_retries": 0,
    }
    for field, value in {
        "store": True,
        "previous_response_id": "prior-response",
        "conversation": "conversation-id",
        "tools": ({"type": "function"},),
        "background": True,
        "max_retries": 1,
    }.items():
        with pytest.raises(ValidationError, match=field):
            ProviderPolicy(**base, **{field: value})


def test_provider_response_model_rejects_continuation_and_conversation() -> None:
    fixture = _fixture()
    for field in ("previous_response_id", "conversation_id"):
        values = _response(fixture.request).model_dump(mode="python")
        values[field] = "unexpected-state"
        with pytest.raises(ValidationError, match=field):
            ProviderResponse.model_validate(values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [{"provider_storage_observed": True}, {"tool_calls": 1}],
    ids=["provider-stored", "tool-call"],
)
async def test_gateway_rejects_response_that_reports_storage_or_tools(
    invalid: dict[str, Any],
) -> None:
    fixture = _fixture()
    gateway = _gateway(fixture)
    with pytest.raises(ValueError, match="stateless|tool"):
        await gateway.execute(
            fixture.request,
            _SequenceBackend(_response(fixture.request, **invalid)),
        )


@pytest.mark.asyncio
async def test_revoked_or_unknown_actor_cannot_use_provider_gateway() -> None:
    fixture = _fixture()
    fixture.registry.revoke(fixture.request.action.lifecycle_id)
    with pytest.raises(ValueError, match="active actor authorization"):
        await _gateway(fixture).execute(
            fixture.request, _SequenceBackend(_response(fixture.request))
        )

    unknown = _fixture()
    empty_registry = ActionRegistry()
    with pytest.raises(ValueError, match="active actor authorization|not registered"):
        await _gateway(unknown, registry=empty_registry).execute(
            unknown.request, _SequenceBackend(_response(unknown.request))
        )


@pytest.mark.asyncio
async def test_scripted_backend_is_one_call_and_carries_no_provider_state() -> None:
    fixture = _fixture()
    backend = ScriptedMechanicalBackend()
    response = await _gateway(fixture).execute(fixture.request, backend)
    assert backend.calls == 1
    assert response.store_requested is False
    assert response.provider_storage_observed is False
    assert response.previous_response_id is None
    assert response.conversation_id is None
    assert response.tool_calls == 0
    assert response.request_hash == fixture.request.semantic_hash()


@pytest.mark.asyncio
async def test_accepted_attempt_replays_durably_after_gateway_restart(tmp_path: Path) -> None:
    fixture = _fixture()
    ledger = tmp_path / "attempts.sqlite"
    first_backend = ScriptedMechanicalBackend()
    first = _gateway(fixture, ledger_path=ledger)
    expected = await first.execute(fixture.request, first_backend)
    first.close()

    restarted_registry = ActionRegistry()
    restarted_registry.register(fixture.identity)
    second_backend = _SequenceBackend(RuntimeError("must not call provider"))
    second = _gateway(
        fixture,
        registry=restarted_registry,
        ledger_path=ledger,
        receipt_private_key=None,
    )
    replay = await second.execute(fixture.request, second_backend)
    second.close()
    assert replay == expected
    assert first_backend.calls == 1
    assert second_backend.calls == 0


@pytest.mark.asyncio
async def test_accepted_attempt_replays_in_process_without_reconsuming_actor_sequence() -> None:
    fixture = _fixture()
    gateway = _gateway(fixture)
    first_backend = ScriptedMechanicalBackend()
    expected = await gateway.execute(fixture.request, first_backend)
    replay = await gateway.execute(
        fixture.request, _SequenceBackend(RuntimeError("must not call provider"))
    )
    assert replay == expected
    assert first_backend.calls == 1
    gateway.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "wrong-model"),
        ("request_hash", "0" * 64),
        ("provider_storage_observed", True),
        ("status", "failed"),
        ("tool_calls", 1),
        ("store_requested", True),
        ("previous_response_id", "response-1"),
        ("conversation_id", "conversation-1"),
        ("output_text", "changed"),
        ("response_id", ""),
        ("gateway_receipt", None),
    ],
)
async def test_durable_replay_revalidates_every_response_contract_field(
    tmp_path: Path, field: str, value: Any
) -> None:
    fixture = _fixture()
    ledger = tmp_path / f"attempts-{field}.sqlite"
    first = _gateway(fixture, ledger_path=ledger)
    await first.execute(fixture.request, ScriptedMechanicalBackend())
    first.close()
    with sqlite3.connect(ledger) as connection:
        row = connection.execute(
            "SELECT response_json FROM logical_attempts WHERE attempt_id = ?",
            (fixture.request.attempt_id,),
        ).fetchone()
        assert row is not None
        response = json.loads(row[0])
        response[field] = value
        connection.execute(
            "UPDATE logical_attempts SET response_json = ? WHERE attempt_id = ?",
            (json.dumps(response), fixture.request.attempt_id),
        )
        connection.commit()
    restarted_registry = ActionRegistry()
    restarted_registry.register(fixture.identity)
    second = _gateway(
        fixture,
        registry=restarted_registry,
        ledger_path=ledger,
        receipt_private_key=None,
    )
    with pytest.raises((InvalidProviderResponseError, ValidationError, ValueError)):
        await second.execute(fixture.request, _SequenceBackend(RuntimeError("no call")))
    second.close()


@pytest.mark.asyncio
async def test_durable_replay_binds_actor_and_lifecycle(tmp_path: Path) -> None:
    fixture = _fixture()
    ledger = tmp_path / "attempts.sqlite"
    first = _gateway(fixture, ledger_path=ledger)
    await first.execute(fixture.request, ScriptedMechanicalBackend())
    first.close()
    with sqlite3.connect(ledger) as connection:
        connection.execute(
            "UPDATE logical_attempts SET actor_id = ? WHERE attempt_id = ?",
            ("different-actor", fixture.request.attempt_id),
        )
        connection.commit()
    restarted_registry = ActionRegistry()
    restarted_registry.register(fixture.identity)
    second = _gateway(
        fixture,
        registry=restarted_registry,
        ledger_path=ledger,
        receipt_private_key=None,
    )
    with pytest.raises(ValueError, match="different actor or lifecycle"):
        await second.execute(fixture.request, _SequenceBackend(RuntimeError("no call")))
    second.close()


@pytest.mark.asyncio
async def test_expected_request_hash_pin_rejects_same_assignment_with_changed_body() -> None:
    fixture = _fixture()
    gateway = _gateway(
        fixture,
        expected_request_hashes={fixture.request.attempt_id: fixture.request.semantic_hash()},
    )
    changed = _resign_request(
        fixture,
        input=({"role": "user", "content": "changed but same assignment"},),
    )
    with pytest.raises(ValueError, match="frozen request contract"):
        await gateway.execute(changed, _SequenceBackend(_response(changed)))
    gateway.close()


@pytest.mark.asyncio
async def test_gateway_receipt_key_is_pinned_across_restart_and_required_for_new_issue(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    ledger = tmp_path / "attempts.sqlite"
    signing_key = fixture.receipt_private_key
    # The receipt key is part of the frozen actor/spec binding; a different
    # key must be rejected before any dispatch.
    first = _gateway(
        fixture,
        ledger_path=ledger,
        receipt_private_key=signing_key,
    )
    expected = await first.execute(fixture.request, ScriptedMechanicalBackend())
    pinned_public_key = first.public_key_b64
    first.close()

    with pytest.raises(ValueError, match="differs from ledger pin"):
        _gateway(
            fixture,
            ledger_path=ledger,
            receipt_private_key=Ed25519PrivateKey.generate(),
        )
    restarted_registry = ActionRegistry()
    restarted_registry.register(fixture.identity)
    replay_gateway = _gateway(
        fixture,
        registry=restarted_registry,
        ledger_path=ledger,
        receipt_private_key=None,
    )
    replay = await replay_gateway.execute(
        fixture.request, _SequenceBackend(RuntimeError("must not call provider"))
    )
    assert replay == expected
    assert replay.gateway_receipt is not None
    assert replay.gateway_receipt.public_key_b64 == pinned_public_key
    # A restarted replay-only gateway has no receipt private key; its frozen
    # one-attempt contract rejects any new request before backend dispatch.
    with pytest.raises(ValueError, match="frozen assignment|frozen request"):
        await replay_gateway.execute(
            _resign_request(fixture, attempt_id="attempt-not-in-contract"),
            _SequenceBackend(RuntimeError("must not call provider")),
        )
    replay_gateway.close()


@pytest.mark.asyncio
async def test_same_logical_attempt_with_changed_signed_body_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    gateway = _gateway(fixture, ledger_path=tmp_path / "attempts.sqlite")
    await gateway.execute(fixture.request, ScriptedMechanicalBackend())
    changed = _resign_request(
        fixture,
        input=({"role": "user", "content": "changed mechanical canary"},),
    )
    with pytest.raises(ValueError, match="reused with changed request|frozen request contract"):
        await gateway.execute(changed, ScriptedMechanicalBackend())
    gateway.close()


@pytest.mark.asyncio
async def test_same_logical_attempt_with_changed_signed_authorization_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    gateway = _gateway(fixture, ledger_path=tmp_path / "attempts.sqlite")
    await gateway.execute(fixture.request, ScriptedMechanicalBackend())
    changed_authorization = _resign_request(fixture)
    with pytest.raises(ValueError, match="changed actor authorization"):
        await gateway.execute(changed_authorization, ScriptedMechanicalBackend())
    gateway.close()


@pytest.mark.asyncio
async def test_in_flight_reserved_attempt_blocks_redispatch_as_ambiguous(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    gateway = _gateway(fixture, ledger_path=tmp_path / "attempts.sqlite")
    gateway.ledger.reserve(fixture.request)
    backend = _SequenceBackend(RuntimeError("must not call provider"))
    with pytest.raises(AmbiguousDeliveryError, match="terminal/in-flight"):
        await gateway.execute(fixture.request, backend)
    assert backend.calls == 0
    gateway.close()


@pytest.mark.asyncio
async def test_backend_cannot_present_a_prior_gateway_receipt_on_a_fresh_attempt(
    tmp_path: Path,
) -> None:
    first = _fixture()
    first_gateway = _gateway(first, ledger_path=tmp_path / "first.sqlite")
    accepted = await first_gateway.execute(first.request, ScriptedMechanicalBackend())
    first_gateway.close()

    second = _fixture()
    second_gateway = _gateway(second, ledger_path=tmp_path / "second.sqlite")
    # A prior accepted response can never be replayed onto a new request: its
    # signed request_hash fails the fresh-path contract before any ledger
    # write, so no cross-attempt response presentation is possible.
    with pytest.raises(InvalidProviderResponseError, match="request hash mismatch"):
        await second_gateway.execute(second.request, _SequenceBackend(accepted))
    second_gateway.close()


@pytest.mark.asyncio
async def test_gateway_rejects_empty_provider_output_text(tmp_path: Path) -> None:
    fixture = _fixture()
    empty = _response(fixture.request).model_copy(
        update={"output_text": "", "output_hash": sha256_bytes(b"")}
    )
    gateway = _gateway(fixture, ledger_path=tmp_path / "attempts.sqlite")
    with pytest.raises(InvalidProviderResponseError, match="empty output text"):
        await gateway.execute(fixture.request, _SequenceBackend(empty))
    gateway.close()


@pytest.mark.asyncio
async def test_restarted_gateway_without_receipt_key_cannot_dispatch_a_fresh_attempt(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    ledger = tmp_path / "attempts.sqlite"
    first = _gateway(fixture, ledger_path=ledger)
    await first.execute(fixture.request, ScriptedMechanicalBackend())
    first.close()

    second_attempt = _resign_request(
        fixture, attempt_id="attempt-second", sequence=1
    )
    restarted_registry = ActionRegistry()
    restarted_registry.register(fixture.identity)
    second = _gateway(
        fixture,
        registry=restarted_registry,
        ledger_path=ledger,
        receipt_private_key=None,
        expected_assignment_hashes={
            fixture.request.attempt_id: fixture.request.assignment_hash,
            second_attempt.attempt_id: second_attempt.assignment_hash,
        },
        expected_request_hashes={
            fixture.request.attempt_id: fixture.request.semantic_hash(),
            second_attempt.attempt_id: second_attempt.semantic_hash(),
        },
        expected_actor_specs={
            fixture.request.attempt_id: fixture.actor_spec,
            second_attempt.attempt_id: fixture.actor_spec,
        },
    )
    backend = _SequenceBackend(RuntimeError("must not call provider"))
    with pytest.raises(RuntimeError, match="no receipt signing key"):
        await second.execute(second_attempt, backend)
    assert backend.calls == 0
    second.close()


class _FakeOutputText:
    type = "output_text"
    text = "fake mechanical output"


class _FakeMessage:
    type = "message"
    content = [_FakeOutputText()]


class _FakeParsedResponse:
    id = "fake-response-id"
    model = "mechanical-test-model"
    output_text = "fake mechanical output"
    output: list[Any] = [_FakeMessage()]
    status = "completed"
    error = None
    incomplete_details = None
    previous_response_id = None
    conversation = None


class _FakeRawResponse:
    headers = {"x-request-id": "fake-request-id"}

    def parse(self) -> _FakeParsedResponse:
        return _FakeParsedResponse()


class _FakeRawResponses:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls = 0
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _FakeRawResponse:
        self.calls += 1
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return _FakeRawResponse()


class _FakeResponses:
    def __init__(self, raw: _FakeRawResponses) -> None:
        self.with_raw_response = raw


class _FakeOpenAIClient:
    instances: list["_FakeOpenAIClient"] = []
    next_error: BaseException | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.raw = _FakeRawResponses(self.next_error)
        self.responses = _FakeResponses(self.raw)
        self.closed = False
        self.instances.append(self)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_openai_backend_sets_no_store_continuation_tools_or_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _fixture()
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = None
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    wire_id = f"{fixture.request.attempt_id}:wire:1"
    response = await OpenAIResponsesBackend(api_key="test-only-key")(
        fixture.request, wire_id
    )
    client = _FakeOpenAIClient.instances[-1]
    assert client.kwargs["max_retries"] == 0
    assert client.raw.calls == 1
    assert client.raw.kwargs is not None
    assert client.raw.kwargs["store"] is False
    assert client.raw.kwargs["background"] is False
    assert client.raw.kwargs["tools"] == []
    assert client.raw.kwargs["stream"] is False
    assert client.raw.kwargs["include"] == []
    assert client.raw.kwargs["extra_headers"]["X-Client-Request-Id"] == wire_id
    assert "previous_response_id" not in client.raw.kwargs
    assert "conversation" not in client.raw.kwargs
    assert response.store_requested is False
    assert response.provider_storage_observed is None
    assert response.previous_response_id is None
    assert response.conversation_id is None
    assert response.tool_calls == 0
    assert client.closed is True


@pytest.mark.parametrize(
    "input_messages",
    [
        ({"role": "user", "content": "ok", "extra": "key"},),
        ({"role": "tool", "content": "ok"},),
        ({"role": "user", "content": 5},),
        ("not-an-object",),
    ],
)
def test_provider_request_input_shape_is_restricted_to_declared_plain_messages(
    input_messages: object,
) -> None:
    fixture = _fixture()
    with pytest.raises(ValidationError):
        _resign_request(fixture, input=input_messages)


@pytest.mark.asyncio
async def test_openai_backend_requires_server_x_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _fixture()
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = None
    monkeypatch.setattr(_FakeRawResponse, "headers", {})
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    with pytest.raises(InvalidProviderResponseError, match="x-request-id"):
        await OpenAIResponsesBackend(api_key="test-only-key")(
            fixture.request, f"{fixture.request.attempt_id}:wire:1"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_type",
    [
        "file_search_call",
        "code_interpreter_call",
        "image_generation_call",
        "local_shell_call",
        "mcp_list_tools",
        "mcp_approval_request",
        "custom_tool_call",
        "apply_patch_call",
        "compaction",
        "program",
    ],
)
async def test_openai_backend_rejects_every_non_allowlisted_output_type(
    monkeypatch: pytest.MonkeyPatch, output_type: str
) -> None:
    fixture = _fixture()

    class Disallowed:
        type = output_type

    monkeypatch.setattr(_FakeParsedResponse, "output", [Disallowed()])
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = None
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    with pytest.raises(InvalidProviderResponseError, match="disallowed output"):
        await OpenAIResponsesBackend(api_key="test-only-key")(
            fixture.request, f"{fixture.request.attempt_id}:wire:1"
        )


@pytest.mark.asyncio
async def test_openai_backend_rejects_refusal_message_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture()

    class Refusal:
        type = "refusal"

    class Message:
        type = "message"
        content = [Refusal()]

    monkeypatch.setattr(_FakeParsedResponse, "output", [Message()])
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = None
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    with pytest.raises(InvalidProviderResponseError, match="disallowed content"):
        await OpenAIResponsesBackend(api_key="test-only-key")(
            fixture.request, f"{fixture.request.attempt_id}:wire:1"
        )


@pytest.mark.asyncio
async def test_openai_backend_allows_reasoning_metadata_but_promotes_only_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture()

    class Reasoning:
        type = "reasoning"

    monkeypatch.setattr(
        _FakeParsedResponse,
        "output",
        [Reasoning(), _FakeMessage()],
    )
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = None
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    response = await OpenAIResponsesBackend(api_key="test-only-key")(
        fixture.request, f"{fixture.request.attempt_id}:wire:1"
    )
    assert response.output_text == "fake mechanical output"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", ["failed", "in_progress", "queued", "cancelled", "incomplete"]
)
async def test_openai_backend_accepts_only_completed_status(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    fixture = _fixture()
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = None
    monkeypatch.setattr(_FakeParsedResponse, "status", status)
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    with pytest.raises(InvalidProviderResponseError, match="not completed"):
        await OpenAIResponsesBackend(api_key="test-only-key")(
            fixture.request, f"{fixture.request.attempt_id}:wire:1"
        )


@pytest.mark.asyncio
async def test_gateway_rejects_wrong_provider_reported_model() -> None:
    fixture = _fixture()
    wrong = _response(fixture.request).model_copy(update={"model": "wrong-model"})
    with pytest.raises(InvalidProviderResponseError, match="pinned model"):
        await _gateway(fixture).execute(fixture.request, _SequenceBackend(wrong))


@pytest.mark.asyncio
async def test_openai_backend_rate_limit_is_terminal_without_idempotency_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _fixture()
    http_response = httpx.Response(429, request=httpx.Request("POST", "https://provider.invalid"))
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = RateLimitError(
        "rate limited", response=http_response, body=None
    )
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    with pytest.raises(ProviderRejectedError):
        await OpenAIResponsesBackend(api_key="test-only-key")(
            fixture.request, f"{fixture.request.attempt_id}:wire:1"
        )
    client = _FakeOpenAIClient.instances[-1]
    assert client.kwargs["max_retries"] == 0
    assert client.raw.calls == 1
    assert client.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("timeout"), httpx.ConnectError("transport")],
    ids=["timeout", "transport"],
)
async def test_openai_backend_treats_ambiguous_transport_as_terminal(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    fixture = _fixture()
    _FakeOpenAIClient.instances.clear()
    _FakeOpenAIClient.next_error = error
    monkeypatch.setattr(
        "h1_live_runtime_adapter_v1.provider.AsyncOpenAI", _FakeOpenAIClient
    )
    with pytest.raises(AmbiguousDeliveryError):
        await OpenAIResponsesBackend(api_key="test-only-key")(
            fixture.request, f"{fixture.request.attempt_id}:wire:1"
        )
    client = _FakeOpenAIClient.instances[-1]
    assert client.raw.calls == 1
    assert client.closed is True
