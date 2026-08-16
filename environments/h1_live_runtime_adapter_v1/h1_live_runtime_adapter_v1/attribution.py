"""Public-key registry for actor action verification and revocation."""

from __future__ import annotations

from .crypto import verify_action, verify_registration
from .models import ActorIdentity, SignedAction


class ActionRegistry:
    """Holds public identities only; it has no operation capable of signing."""

    def __init__(self) -> None:
        self._identities: dict[str, ActorIdentity] = {}
        self._active: set[str] = set()
        self._seen_keys: set[str] = set()
        self._last_sequence: dict[str, int] = {}

    def register(self, identity: ActorIdentity) -> None:
        if not verify_registration(identity):
            raise ValueError("actor registration proof is invalid")
        if identity.lifecycle_id in self._identities:
            raise ValueError("lifecycle identity cannot be registered twice")
        if identity.public_key_b64 in self._seen_keys:
            raise ValueError("actor public signing key cannot be reused")
        self._identities[identity.lifecycle_id] = identity
        self._active.add(identity.lifecycle_id)
        self._seen_keys.add(identity.public_key_b64)
        self._last_sequence[identity.lifecycle_id] = 0

    def revoke(self, lifecycle_id: str) -> None:
        if lifecycle_id not in self._identities:
            raise KeyError(lifecycle_id)
        self._active.discard(lifecycle_id)

    def verify(self, action: SignedAction, *, consume: bool = True) -> bool:
        identity = self._identities.get(action.lifecycle_id)
        if identity is None or action.lifecycle_id not in self._active:
            return False
        if (
            action.actor_id != identity.actor_id
            or action.session_id != identity.session_id
            or action.generation != identity.generation
            or action.lineage_id != identity.lineage_id
            or action.public_key_b64 != identity.public_key_b64
            or not verify_action(action)
        ):
            return False
        last = self._last_sequence[action.lifecycle_id]
        if action.sequence != last + 1:
            return False
        if consume:
            self._last_sequence[action.lifecycle_id] = action.sequence
        return True

    def active(self, lifecycle_id: str) -> bool:
        return lifecycle_id in self._active

    def public_record(self, lifecycle_id: str) -> ActorIdentity:
        return self._identities[lifecycle_id]

    @property
    def private_key_count(self) -> int:
        return 0
