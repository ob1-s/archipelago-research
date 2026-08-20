"""Standard Ed25519 action authentication."""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical import canonical_bytes, stable_hash
from .models import ActorIdentity, GatewayReceipt, SignedAction


def actor_identity_binding(
    *,
    actor_id: str,
    lifecycle_id: str,
    session_id: str,
    generation: int,
    lineage_id: str,
    public_key_b64: str,
) -> str:
    """Hash the exact actor identity a gateway receipt is delivered to."""

    return stable_hash(
        {
            "actor_id": actor_id,
            "lifecycle_id": lifecycle_id,
            "session_id": session_id,
            "generation": generation,
            "lineage_id": lineage_id,
            "public_key_b64": public_key_b64,
        }
    )


def action_identity_binding(action: SignedAction) -> str:
    return actor_identity_binding(
        actor_id=action.actor_id,
        lifecycle_id=action.lifecycle_id,
        session_id=action.session_id,
        generation=action.generation,
        lineage_id=action.lineage_id,
        public_key_b64=action.public_key_b64,
    )


def verify_registration(identity: ActorIdentity) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(identity.public_key_b64)
        )
        registration = identity.model_dump(
            exclude={"registration_signature_b64"}, mode="json"
        )
        key.verify(
            base64.b64decode(identity.registration_signature_b64),
            b"h1-live-runtime-registration/v1\0" + canonical_bytes(registration),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_action(action: SignedAction) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(action.public_key_b64))
        key.verify(
            base64.b64decode(action.signature_b64),
            b"h1-live-runtime-action/v1\0"
            + canonical_bytes(action.unsigned_payload()),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_gateway_receipt(receipt: GatewayReceipt) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(receipt.public_key_b64)
        )
        key.verify(
            base64.b64decode(receipt.signature_b64),
            b"h1-live-runtime-gateway-receipt/v1\0"
            + canonical_bytes(receipt.unsigned_payload()),
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
