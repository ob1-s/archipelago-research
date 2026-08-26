"""Stateless Responses adapter with fail-closed, durable attempt accounting."""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
import sqlite3
import tempfile
from types import MappingProxyType
from pathlib import Path
from typing import Mapping, Protocol

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import ValidationError

from .attribution import ActionRegistry
from .canonical import canonical_bytes, sha256_bytes, stable_hash
from .crypto import verify_action, verify_gateway_receipt
from .isolation import IsolatedActor
from .models import (
    GatewayReceipt,
    ProviderPolicy,
    ProviderRequest,
    ProviderResponse,
    RetryAttempt,
    ActorSpec,
)


class SafeToRetryError(RuntimeError):
    """Legacy marker for a pre-dispatch-shaped failure; never auto-retried."""


class AmbiguousDeliveryError(RuntimeError):
    """A request may have been accepted; replay would create an ambiguous unit."""


class ProviderRejectedError(RuntimeError):
    """The provider returned a terminal rejection; no automatic retry is allowed."""


class InvalidProviderResponseError(ValueError):
    """A response arrived but failed the completed stateless response contract."""


class ProviderBackend(Protocol):
    async def __call__(
        self, request: ProviderRequest, wire_attempt_id: str
    ) -> ProviderResponse: ...


_ALLOWED_RESPONSE_OUTPUT_TYPES = frozenset({"message", "reasoning"})
_ALLOWED_MESSAGE_CONTENT_TYPES = frozenset({"output_text"})


def _validate_openai_output_items(response: object) -> None:
    """Accept only the non-tool Responses output surface used by this adapter.

    The SDK's ``ResponseOutputItem`` union grows as new tools and programmatic
    surfaces are added.  Counting a handful of known tool names is therefore
    not a closed-world check: a newly added item type could silently pass as a
    zero-tool response.  The adapter accepts only ordinary message output and
    reasoning metadata.  Reasoning is deliberately not copied into the
    ``ProviderResponse``; only the message's output text is promoted.
    """

    output = getattr(response, "output", None)
    if not isinstance(output, list) or not output:
        raise InvalidProviderResponseError("provider response has no output items")
    output_types = [getattr(item, "type", None) for item in output]
    unexpected = sorted(
        {
            item_type
            for item_type in output_types
            if item_type not in _ALLOWED_RESPONSE_OUTPUT_TYPES
        },
        key=lambda value: repr(value),
    )
    if unexpected:
        raise InvalidProviderResponseError(
            f"provider emitted disallowed output item type(s): {unexpected!r}"
        )
    messages = [item for item in output if getattr(item, "type", None) == "message"]
    if len(messages) != 1:
        raise InvalidProviderResponseError(
            "provider response must contain exactly one message output item"
        )
    content = getattr(messages[0], "content", None)
    if not isinstance(content, list) or not content:
        raise InvalidProviderResponseError("provider message has no content items")
    content_types = [getattr(item, "type", None) for item in content]
    unexpected_content = sorted(
        {
            item_type
            for item_type in content_types
            if item_type not in _ALLOWED_MESSAGE_CONTENT_TYPES
        },
        key=lambda value: repr(value),
    )
    if unexpected_content:
        raise InvalidProviderResponseError(
            "provider message contains disallowed content item type(s): "
            f"{unexpected_content!r}"
        )


def _public_key_b64(private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()


def _validate_retry_budget(value: int) -> int:
    """Validate the one immutable retry budget used by a gateway.

    This runtime deliberately freezes the budget at zero.  A caller-supplied
    backend cannot manufacture a pre-dispatch proof that would authorize a
    second provider dispatch, and no HTTP retry is safe without a provider
    idempotency contract.  The parameter remains explicit so future versions
    can replace it with a gateway-owned capability rather than re-opening a
    freely caller-controlled knob.
    """

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("retry budget must be a nonnegative integer")
    if value != 0:
        raise ValueError("this stateless gateway freezes the retry budget at zero")
    return value


async def prepare_request(
    actor: IsolatedActor,
    *,
    policy: ProviderPolicy,
    input: tuple[dict, ...],
    instructions: str | None,
    attempt_id: str,
    assignment_hash: str,
    common_prior_hashes: dict[str, str],
) -> ProviderRequest:
    semantic_payload = {
        "policy": policy.model_dump(mode="json"),
        "input": list(input),
        "instructions": instructions,
        "attempt_id": attempt_id,
        "assignment_hash": assignment_hash,
        "common_prior_hashes": common_prior_hashes,
    }
    result = await actor.command(
        "prepare_provider_request", semantic_payload=semantic_payload
    )
    action = actor.validate_action(result["action"])
    return ProviderRequest(
        action=action,
        policy=policy,
        input=input,
        instructions=instructions,
        attempt_id=attempt_id,
        assignment_hash=assignment_hash,
        common_prior_hashes=common_prior_hashes,
    )


class ScriptedMechanicalBackend:
    """No-model backend used to regression-test the signed request boundary."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(
        self, request: ProviderRequest, wire_attempt_id: str
    ) -> ProviderResponse:
        self.calls += 1
        output = f"mechanical-provider:{request.semantic_hash()}"
        return ProviderResponse(
            provider="scripted-mechanical",
            model=request.policy.model,
            response_id=f"scripted-response-{self.calls}",
            request_id=wire_attempt_id,
            output_text=output,
            output_hash=sha256_bytes(output.encode()),
            request_hash=request.semantic_hash(),
            store_requested=False,
            provider_storage_observed=False,
        )


class OpenAIResponsesBackend:
    """Real provider transport. Credentials remain in the gateway, never the actor."""

    def __init__(self, *, api_key: str, timeout: float = 120.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def __call__(
        self, request: ProviderRequest, wire_attempt_id: str
    ) -> ProviderResponse:
        policy = request.policy
        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=policy.base_url,
            max_retries=0,
            timeout=httpx.Timeout(self.timeout, connect=10),
        )
        kwargs = {
            "model": policy.model,
            "input": list(request.input),
            "instructions": request.instructions,
            "store": False,
            "background": False,
            "tools": [],
            "stream": False,
            "include": [],
            "extra_headers": {"X-Client-Request-Id": wire_attempt_id},
        }
        try:
            raw = await client.responses.with_raw_response.create(**kwargs)
            response = raw.parse()
        except RateLimitError as exc:
            # A correlation identifier is not an idempotency contract.  Even a
            # 429 is terminal here unless a future pinned provider contract
            # proves the request was rejected before generation.
            raise ProviderRejectedError("provider rate limit; not retried") from exc
        except (
            APITimeoutError,
            APIConnectionError,
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise AmbiguousDeliveryError(
                "provider delivery is unknown after timeout/connection failure"
            ) from exc
        finally:
            await client.close()

        if response.status != "completed":
            raise InvalidProviderResponseError(
                f"provider response status is not completed: {response.status!r}"
            )
        if response.error is not None or response.incomplete_details is not None:
            raise InvalidProviderResponseError("provider response reports error/incomplete")
        if response.previous_response_id is not None:
            raise InvalidProviderResponseError("provider response reports continuation")
        if getattr(response, "conversation", None) is not None:
            raise InvalidProviderResponseError("provider response belongs to a conversation")
        _validate_openai_output_items(response)
        output = response.output_text
        if not output:
            raise InvalidProviderResponseError("provider response has empty output text")
        request_id = raw.headers.get("x-request-id")
        if not request_id:
            raise InvalidProviderResponseError(
                "provider response lacks a server x-request-id"
            )
        return ProviderResponse(
            provider="openai-responses",
            model=response.model,
            response_id=response.id,
            request_id=request_id,
            output_text=output,
            output_hash=sha256_bytes(output.encode()),
            request_hash=request.semantic_hash(),
            store_requested=False,
            # Responses does not report a `store` field. Keep provider-internal
            # retention unknown rather than laundering the request flag into
            # a storage observation.
            provider_storage_observed=None,
            tool_calls=0,
        )


class AttemptLedger:
    """SQLite uniqueness/terminal-state ledger for logical provider attempts."""

    def __init__(self, path: Path | None = None) -> None:
        self._owned = path is None
        if path is None:
            descriptor, raw_path = tempfile.mkstemp(
                prefix="h1-provider-attempts-", suffix=".sqlite", dir="/tmp"
            )
            os.close(descriptor)
            path = Path(raw_path)
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS logical_attempts (
                attempt_id TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                lifecycle_id TEXT NOT NULL,
                authorization_hash TEXT,
                state TEXT NOT NULL,
                response_json TEXT
            )
            """
        )
        # The adapter is additive and may be pointed at a ledger produced by
        # an earlier model of this package.  Keep the old rows readable but
        # fail closed on replay until their missing authorization binding is
        # explicitly migrated; never silently infer it from a new request.
        columns = {
            row[1]
            for row in self.connection.execute(
                "PRAGMA table_info(logical_attempts)"
            ).fetchall()
        }
        if "authorization_hash" not in columns:
            self.connection.execute(
                "ALTER TABLE logical_attempts ADD COLUMN authorization_hash TEXT"
            )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transport_attempts (
                attempt_id TEXT NOT NULL,
                transport_attempt INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                PRIMARY KEY (attempt_id, transport_attempt)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gateway_metadata (
                metadata_key TEXT PRIMARY KEY,
                metadata_value TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def reserve(self, request: ProviderRequest) -> ProviderResponse | None:
        request_hash = request.semantic_hash()
        authorization_hash = stable_hash(request.action.model_dump(mode="json"))
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT request_hash, actor_id, lifecycle_id, authorization_hash, "
                "state, response_json FROM logical_attempts "
                "WHERE attempt_id = ?",
                (request.attempt_id,),
            ).fetchone()
            if row is not None:
                (
                    existing_hash,
                    existing_actor_id,
                    existing_lifecycle_id,
                    existing_authorization_hash,
                    state,
                    response_json,
                ) = row
                if existing_hash != request_hash:
                    raise ValueError("logical attempt ID reused with changed request")
                if (
                    existing_actor_id != request.action.actor_id
                    or existing_lifecycle_id != request.action.lifecycle_id
                ):
                    raise ValueError(
                        "logical attempt ID reused by a different actor or lifecycle"
                    )
                if existing_authorization_hash is None:
                    raise ValueError(
                        "logical attempt replay lacks an authorization binding"
                    )
                if existing_authorization_hash != authorization_hash:
                    raise ValueError(
                        "logical attempt replay has changed actor authorization"
                    )
                if state == "accepted" and response_json is not None:
                    self.connection.commit()
                    return ProviderResponse.model_validate_json(response_json)
                raise AmbiguousDeliveryError(
                    f"logical attempt already has terminal/in-flight state {state!r}"
                )
            self.connection.execute(
                "INSERT INTO logical_attempts "
                "(attempt_id, request_hash, actor_id, lifecycle_id, "
                "authorization_hash, state, response_json) "
                "VALUES (?, ?, ?, ?, ?, 'active', NULL)",
                (
                    request.attempt_id,
                    request_hash,
                    request.action.actor_id,
                    request.action.lifecycle_id,
                    authorization_hash,
                ),
            )
            self.connection.commit()
            return None
        except BaseException:
            self.connection.rollback()
            raise

    def pin_gateway(self, *, gateway_id: str, public_key_b64: str) -> None:
        """Persist the receipt verification identity for this ledger.

        The private signing key is intentionally not written to the attempt
        ledger.  A process restart can replay accepted records using the
        durable public pin, while a process that needs to issue a new receipt
        must be launched with the matching private key.
        """

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            rows = dict(
                self.connection.execute(
                    "SELECT metadata_key, metadata_value FROM gateway_metadata"
                ).fetchall()
            )
            if rows and (
                rows.get("gateway_id") != gateway_id
                or rows.get("public_key_b64") != public_key_b64
            ):
                raise ValueError("gateway receipt identity differs from ledger pin")
            self.connection.execute(
                "INSERT OR REPLACE INTO gateway_metadata "
                "(metadata_key, metadata_value) VALUES (?, ?)",
                ("gateway_id", gateway_id),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO gateway_metadata "
                "(metadata_key, metadata_value) VALUES (?, ?)",
                ("public_key_b64", public_key_b64),
            )
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def gateway_metadata(self) -> tuple[str, str] | None:
        rows = dict(
            self.connection.execute(
                "SELECT metadata_key, metadata_value FROM gateway_metadata"
            ).fetchall()
        )
        if not rows:
            return None
        if set(rows) != {"gateway_id", "public_key_b64"}:
            raise ValueError("gateway receipt identity pin is incomplete")
        return rows["gateway_id"], rows["public_key_b64"]

    def append(self, attempt: RetryAttempt) -> None:
        self.connection.execute(
            "INSERT INTO transport_attempts VALUES (?, ?, ?)",
            (
                attempt.logical_attempt_id,
                attempt.transport_attempt,
                attempt.model_dump_json(),
            ),
        )
        self.connection.commit()

    def finish(
        self,
        attempt_id: str,
        state: str,
        response: ProviderResponse | None = None,
    ) -> None:
        self.connection.execute(
            "UPDATE logical_attempts SET state = ?, response_json = ? WHERE attempt_id = ?",
            (state, response.model_dump_json() if response else None, attempt_id),
        )
        self.connection.commit()

    def records(self, attempt_id: str | None = None) -> tuple[RetryAttempt, ...]:
        if attempt_id is None:
            rows = self.connection.execute(
                "SELECT record_json FROM transport_attempts "
                "ORDER BY attempt_id, transport_attempt"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT record_json FROM transport_attempts WHERE attempt_id = ? "
                "ORDER BY transport_attempt",
                (attempt_id,),
            ).fetchall()
        return tuple(RetryAttempt.model_validate_json(row[0]) for row in rows)

    def close(self) -> None:
        self.connection.close()
        if self._owned:
            self.path.unlink(missing_ok=True)
            Path(f"{self.path}-wal").unlink(missing_ok=True)
            Path(f"{self.path}-shm").unlink(missing_ok=True)


class ProviderGateway:
    """Verifies authorship and prevents duplicate/ambiguous logical attempts."""

    def __init__(
        self,
        registry: ActionRegistry,
        expected_policy: ProviderPolicy | None = None,
        *,
        ledger_path: Path | None = None,
        expected_common_prior_hashes: dict[str, str] | None = None,
        expected_assignment_hashes: dict[str, str] | None = None,
        expected_request_hashes: dict[str, str] | None = None,
        expected_actor_specs: Mapping[str, ActorSpec] | None = None,
        receipt_private_key: Ed25519PrivateKey | None = None,
        max_safe_retries: int = 0,
    ) -> None:
        # A gateway without a frozen contract is not a safe provider boundary:
        # callers could select a policy, prior set, assignment, request body,
        # or actor after the gateway is constructed.  Keep the constructor
        # shape readable for callers, but fail closed before any ledger row or
        # backend dispatch if one pin is omitted.
        if (
            expected_policy is None
            or expected_common_prior_hashes is None
            or expected_assignment_hashes is None
            or expected_request_hashes is None
            or expected_actor_specs is None
        ):
            raise ValueError(
                "provider gateway requires a complete frozen policy, prior, "
                "assignment, request, and actor/spec contract"
            )
        self.registry = registry
        self._expected_policy_hash = request_contract_hash(expected_policy)
        self.expected_common_prior_hashes = MappingProxyType(
            dict(expected_common_prior_hashes)
        )
        self.expected_assignment_hashes = MappingProxyType(
            dict(expected_assignment_hashes)
        )
        self.expected_request_hashes = MappingProxyType(
            dict(expected_request_hashes)
        )
        self.expected_actor_specs = MappingProxyType(
            {
                attempt_id: ActorSpec.model_validate(
                    spec.model_dump(mode="python")
                )
                for attempt_id, spec in expected_actor_specs.items()
            }
        )
        contract_keys = set(self.expected_assignment_hashes)
        if contract_keys != set(self.expected_request_hashes) or contract_keys != set(
            self.expected_actor_specs
        ):
            raise ValueError(
                "provider gateway frozen contract maps must have identical attempts"
            )
        if not contract_keys:
            raise ValueError("provider gateway frozen contract cannot be empty")
        self.ledger = AttemptLedger(ledger_path)
        self._max_safe_retries = _validate_retry_budget(max_safe_retries)
        self.attempts: list[RetryAttempt] = []
        self._execute_lock = asyncio.Lock()
        pinned_gateway = self.ledger.gateway_metadata()
        if pinned_gateway is None:
            self.gateway_id = f"gateway-{secrets.token_hex(16)}"
            self._receipt_private_key = (
                receipt_private_key or Ed25519PrivateKey.generate()
            )
            self.public_key_b64 = _public_key_b64(self._receipt_private_key)
            self.ledger.pin_gateway(
                gateway_id=self.gateway_id, public_key_b64=self.public_key_b64
            )
        else:
            self.gateway_id, self.public_key_b64 = pinned_gateway
            self._receipt_private_key = receipt_private_key
            if receipt_private_key is not None and (
                _public_key_b64(receipt_private_key) != self.public_key_b64
            ):
                raise ValueError("receipt signing key differs from ledger pin")
        if any(
            spec.gateway_public_key_b64 != self.public_key_b64
            for spec in self.expected_actor_specs.values()
        ):
            raise ValueError(
                "every frozen actor/spec must bind the gateway receipt public key"
            )

    @property
    def max_safe_retries(self) -> int:
        """Return the immutable gateway retry budget."""

        return self._max_safe_retries

    @property
    def expected_policy_hash(self) -> str:
        """Return the immutable hash of the pinned provider policy."""

        return self._expected_policy_hash

    def _receipt(
        self, request: ProviderRequest, response: ProviderResponse
    ) -> GatewayReceipt:
        if self._receipt_private_key is None:
            raise RuntimeError("provider gateway has no receipt signing key")
        unsigned = {
            "gateway_id": self.gateway_id,
            "public_key_b64": self.public_key_b64,
            "logical_attempt_id": request.attempt_id,
            "assignment_hash": request.assignment_hash,
            "request_hash": request.semantic_hash(),
            "response_id": response.response_id,
            "provider_request_id": response.request_id,
            "output_hash": response.output_hash,
        }
        signature = base64.b64encode(
            self._receipt_private_key.sign(
                b"h1-live-runtime-gateway-receipt/v1\0"
                + canonical_bytes(unsigned)
            )
        ).decode()
        return GatewayReceipt(**unsigned, signature_b64=signature)

    def _verify_action_without_consuming(self, request: ProviderRequest) -> bool:
        """Verify actor authorship while leaving sequence state untouched.

        ``ActionRegistry.verify`` intentionally consumes a sequence number.
        Replay must consult the durable ledger before consuming that number,
        otherwise the exact signed request that produced an accepted record
        can never be replayed in-process.  We therefore perform the registry's
        identity/signature checks through its read-only public APIs first, and
        consume the sequence only after a new ledger reservation is made.
        """

        action = request.action
        try:
            identity = self.registry.public_record(action.lifecycle_id)
        except KeyError:
            return False
        return bool(
            self.registry.active(action.lifecycle_id)
            and action.actor_id == identity.actor_id
            and action.session_id == identity.session_id
            and action.generation == identity.generation
            and action.lineage_id == identity.lineage_id
            and action.public_key_b64 == identity.public_key_b64
            and verify_action(action)
        )

    def _validate_scheduled_actor(self, request: ProviderRequest) -> None:
        """Require the request actor to be the exact frozen schedule actor.

        Registry authentication proves that an action came from *a* live
        actor.  This additional pin proves it came from the actor/lifecycle,
        generation, lineage, position, and gateway binding assigned to this
        specific attempt; an actor cannot substitute for another scheduled
        actor merely by signing the same request hash.
        """

        expected = self.expected_actor_specs.get(request.attempt_id)
        if expected is None:
            raise ValueError("request attempt is absent from the frozen actor/spec contract")
        action = request.action
        if (
            action.actor_id != expected.actor_id
            or action.lifecycle_id != expected.lifecycle_id
            or action.generation != expected.generation
            or action.lineage_id != expected.lineage_id
        ):
            raise ValueError("provider request actor differs from frozen actor/spec binding")
        try:
            identity = self.registry.public_record(action.lifecycle_id)
        except KeyError as exc:
            raise ValueError("provider request actor is not registered") from exc
        if (
            identity.actor_id != expected.actor_id
            or identity.lifecycle_id != expected.lifecycle_id
            or identity.generation != expected.generation
            or identity.lineage_id != expected.lineage_id
            or identity.position != expected.position
            or (
                expected.gateway_public_key_b64 is not None
                and identity.gateway_public_key_b64 != expected.gateway_public_key_b64
            )
        ):
            raise ValueError("registered actor differs from frozen actor/spec binding")

    def _validate_response_contract(
        self,
        request: ProviderRequest,
        response: ProviderResponse,
        *,
        require_receipt: bool,
    ) -> ProviderResponse:
        """Revalidate both fresh and durable responses at the gateway boundary."""

        if response.status != "completed":
            raise InvalidProviderResponseError("provider response is not completed")
        if not response.response_id:
            raise InvalidProviderResponseError("provider response ID is empty")
        if not response.output_text:
            raise InvalidProviderResponseError("provider response has empty output text")
        if response.model != request.policy.model:
            raise InvalidProviderResponseError(
                "provider-reported model differs from pinned model"
            )
        request_hash = request.semantic_hash()
        if response.request_hash != request_hash:
            raise InvalidProviderResponseError("provider response/request hash mismatch")
        if response.store_requested is not False:
            raise InvalidProviderResponseError("provider response store flag is not false")
        if response.provider_storage_observed is True:
            raise InvalidProviderResponseError(
                "provider reported storage despite stateless request"
            )
        if response.previous_response_id is not None:
            raise InvalidProviderResponseError("provider response reports continuation")
        if response.conversation_id is not None:
            raise InvalidProviderResponseError("provider response belongs to a conversation")
        if response.tool_calls != 0:
            raise InvalidProviderResponseError("provider emitted a tool call")
        receipt = response.gateway_receipt
        if not require_receipt:
            if receipt is not None:
                raise InvalidProviderResponseError(
                    "backend cannot supply a gateway receipt"
                )
            return response
        if receipt is None:
            raise InvalidProviderResponseError("accepted replay lacks a gateway receipt")
        if not verify_gateway_receipt(receipt):
            raise InvalidProviderResponseError("gateway receipt signature is invalid")
        if (
            receipt.gateway_id != self.gateway_id
            or receipt.public_key_b64 != self.public_key_b64
            or receipt.logical_attempt_id != request.attempt_id
            or receipt.assignment_hash != request.assignment_hash
            or receipt.request_hash != request_hash
            or receipt.response_id != response.response_id
            or receipt.provider_request_id != response.request_id
            or receipt.output_hash != response.output_hash
        ):
            raise InvalidProviderResponseError(
                "gateway receipt does not bind the accepted response"
            )
        return response

    def _record(self, attempt: RetryAttempt) -> None:
        self.ledger.append(attempt)
        self.attempts.append(attempt)

    async def execute(
        self,
        request: ProviderRequest,
        backend: ProviderBackend,
        *,
        max_safe_retries: int | None = None,
    ) -> ProviderResponse:
        request = ProviderRequest.model_validate(request.model_dump(mode="python"))
        if max_safe_retries is not None and max_safe_retries != self.max_safe_retries:
            raise ValueError("retry budget is frozen by the provider gateway")
        if request_contract_hash(request.policy) != self.expected_policy_hash:
            raise ValueError("provider policy differs from the pinned gateway policy")
        if request.common_prior_hashes != self.expected_common_prior_hashes:
            raise ValueError("request common priors differ from the pinned source hashes")
        if self.expected_assignment_hashes.get(request.attempt_id) != request.assignment_hash:
            raise ValueError("request differs from the frozen assignment hash")
        request_hash = request.semantic_hash()
        if self.expected_request_hashes.get(request.attempt_id) != request_hash:
            raise ValueError("request differs from the frozen request contract")
        self._validate_scheduled_actor(request)

        async with self._execute_lock:
            # Treat a direct mutation of a private attribute (or a future
            # deserialization bug) as a construction failure before reserving
            # a logical attempt.  No mutable retry knob may change the
            # dispatch plan after the ledger has been touched.
            _validate_retry_budget(self._max_safe_retries)
            # Verify identity and the Ed25519 proof without consuming sequence
            # state.  An accepted replay has already consumed this sequence in
            # the original call, so registry.verify(..., consume=True) cannot
            # be the pre-ledger check.
            if not self._verify_action_without_consuming(request):
                raise ValueError("provider request lacks active actor authorization")
            replay = self.ledger.reserve(request)
            if replay is not None:
                return self._validate_response_contract(
                    request, replay, require_receipt=True
                )
            # A restarted gateway may have the durable public receipt pin but
            # no private signing key.  It may replay accepted records, but it
            # must not dispatch a new provider request that it cannot attest.
            if self._receipt_private_key is None:
                self.ledger.finish(request.attempt_id, "rejected")
                raise RuntimeError("provider gateway has no receipt signing key")
            # Consume the actor sequence only after the new logical attempt is
            # durably reserved.  If this read-only check and consume disagree,
            # fail before any provider dispatch.
            if not self.registry.verify(request.action):
                self.ledger.finish(request.attempt_id, "rejected")
                raise ValueError("provider request lacks active actor authorization")
            for transport_attempt in range(1, self._max_safe_retries + 2):
                wire_attempt_id = f"{request.attempt_id}:wire:{transport_attempt}"
                try:
                    raw_response = await backend(request, wire_attempt_id)
                    response = ProviderResponse.model_validate(
                        raw_response.model_dump(mode="python")
                    )
                    response = self._validate_response_contract(
                        request, response, require_receipt=False
                    )
                except SafeToRetryError:
                    # SafeToRetryError is intentionally terminal.  An
                    # arbitrary backend callable cannot prove that it failed
                    # before dispatch, and the runtime has no provider
                    # idempotency contract.  Keeping the record type lets the
                    # audit distinguish the failure surface without granting
                    # caller-forgeable automatic retries.
                    retryable = False
                    self._record(
                        RetryAttempt(
                            actor_id=request.action.actor_id,
                            lifecycle_id=request.action.lifecycle_id,
                            logical_attempt_id=request.attempt_id,
                            transport_attempt=transport_attempt,
                            wire_attempt_id=wire_attempt_id,
                            request_hash=request_hash,
                            outcome="backend_claimed_pre_dispatch_rejection_terminal",
                            # The backend callable cannot prove that no
                            # bytes reached a provider.  Treat this as
                            # unknown delivery for audit purposes even though
                            # the caller labels it "pre-dispatch".
                            dispatch_phase="unknown",
                            retryable=retryable,
                        )
                    )
                    self.ledger.finish(request.attempt_id, "rejected")
                    raise
                except asyncio.CancelledError:
                    self._record(
                        RetryAttempt(
                            actor_id=request.action.actor_id,
                            lifecycle_id=request.action.lifecycle_id,
                            logical_attempt_id=request.attempt_id,
                            transport_attempt=transport_attempt,
                            wire_attempt_id=wire_attempt_id,
                            request_hash=request_hash,
                            outcome="cancelled_unknown_delivery",
                            dispatch_phase="unknown",
                            retryable=False,
                        )
                    )
                    self.ledger.finish(request.attempt_id, "unknown_delivery")
                    raise
                except AmbiguousDeliveryError:
                    self._record(
                        RetryAttempt(
                            actor_id=request.action.actor_id,
                            lifecycle_id=request.action.lifecycle_id,
                            logical_attempt_id=request.attempt_id,
                            transport_attempt=transport_attempt,
                            wire_attempt_id=wire_attempt_id,
                            request_hash=request_hash,
                            outcome="ambiguous_delivery_terminal",
                            dispatch_phase="unknown",
                            retryable=False,
                        )
                    )
                    self.ledger.finish(request.attempt_id, "unknown_delivery")
                    raise
                except ProviderRejectedError:
                    self._record(
                        RetryAttempt(
                            actor_id=request.action.actor_id,
                            lifecycle_id=request.action.lifecycle_id,
                            logical_attempt_id=request.attempt_id,
                            transport_attempt=transport_attempt,
                            wire_attempt_id=wire_attempt_id,
                            request_hash=request_hash,
                            outcome="provider_rejected_terminal",
                            dispatch_phase="response_received",
                            retryable=False,
                        )
                    )
                    self.ledger.finish(request.attempt_id, "rejected")
                    raise
                except (
                    InvalidProviderResponseError,
                    ValidationError,
                    AttributeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    self._record(
                        RetryAttempt(
                            actor_id=request.action.actor_id,
                            lifecycle_id=request.action.lifecycle_id,
                            logical_attempt_id=request.attempt_id,
                            transport_attempt=transport_attempt,
                            wire_attempt_id=wire_attempt_id,
                            request_hash=request_hash,
                            outcome=f"{type(exc).__name__}_terminal",
                            dispatch_phase="response_received",
                            retryable=False,
                        )
                    )
                    self.ledger.finish(request.attempt_id, "invalid_response")
                    raise
                except Exception as exc:
                    self._record(
                        RetryAttempt(
                            actor_id=request.action.actor_id,
                            lifecycle_id=request.action.lifecycle_id,
                            logical_attempt_id=request.attempt_id,
                            transport_attempt=transport_attempt,
                            wire_attempt_id=wire_attempt_id,
                            request_hash=request_hash,
                            outcome=f"{type(exc).__name__}_terminal",
                            dispatch_phase="unknown",
                            retryable=False,
                        )
                    )
                    self.ledger.finish(request.attempt_id, "unknown_delivery")
                    raise

                accepted = RetryAttempt(
                    actor_id=request.action.actor_id,
                    lifecycle_id=request.action.lifecycle_id,
                    logical_attempt_id=request.attempt_id,
                    transport_attempt=transport_attempt,
                    wire_attempt_id=wire_attempt_id,
                    request_hash=request_hash,
                    outcome="accepted_completed",
                    dispatch_phase="response_received",
                    provider_request_id=response.request_id,
                    provider_response_id=response.response_id,
                    retryable=False,
                )
                response = ProviderResponse.model_validate(
                    response.model_copy(
                        update={"gateway_receipt": self._receipt(request, response)}
                    ).model_dump(mode="python")
                )
                response = self._validate_response_contract(
                    request, response, require_receipt=True
                )
                self._record(accepted)
                self.ledger.finish(request.attempt_id, "accepted", response)
                return response
        raise AssertionError("unreachable")

    def close(self) -> None:
        self.ledger.close()
        self._receipt_private_key = None


def random_attempt_id() -> str:
    return f"attempt-{secrets.token_hex(16)}"


def request_contract_hash(policy: ProviderPolicy) -> str:
    return stable_hash(policy.model_dump(mode="json"))


__all__ = [
    "AmbiguousDeliveryError",
    "AttemptLedger",
    "InvalidProviderResponseError",
    "OpenAIResponsesBackend",
    "ProviderGateway",
    "ProviderRejectedError",
    "SafeToRetryError",
    "ScriptedMechanicalBackend",
    "prepare_request",
    "random_attempt_id",
    "request_contract_hash",
]
