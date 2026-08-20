"""Deterministic reference policies used only by the model-free preflight.

These policies are never exposed to a behavioral model.  Every policy below
accepts only the role-local :class:`Observation` plus a generator-derived
codebook; no policy receives a job seed, target matching, or the partner mask.
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

from .actions import FinishAction, SetAction, UnsetAction, WaitAction, WorldAction, WriteAction
from .canonical import stable_hash
from .generator import generator_conditioned_map, is_perfect_matching, perfect_matchings
from .models import Pair, Station
from .world import Observation, Policy

WRITE_CHUNK_COUNT = 512
TIMING_ROUNDS = tuple(combinations(range(1, 8), 3))
CODE_CAPACITY = WRITE_CHUNK_COUNT * len(TIMING_ROUNDS)


def _mask_key(mask: Iterable[tuple[int, int]]) -> tuple[Pair, ...]:
    return tuple((int(item), int(target)) for item, target in sorted(mask))


class MaskCodebook:
    """Finite generator-aware public codebook for role-local private masks."""

    def __init__(self, masks: Iterable[Iterable[tuple[int, int]]]) -> None:
        unique = sorted({_mask_key(mask) for mask in masks})
        if len(unique) > CODE_CAPACITY:
            raise ValueError(
                f"{len(unique)} masks exceed the three-write public code capacity "
                f"of {CODE_CAPACITY}"
            )
        self.masks = tuple(unique)
        self._encode = {mask: code for code, mask in enumerate(self.masks)}
        self._decode = {code: mask for mask, code in self._encode.items()}
        self._signature_index: dict[tuple[int, tuple[tuple[int, int, int], ...]], set[int]] = {}
        for style in (0, 1):
            for code in self._decode:
                selected_events = self.events_for_code(code, style=style)
                expected = tuple(
                    (round_number + 1, register, symbol)
                    for round_number, register, symbol in selected_events
                )
                signatures = {
                    expected,
                    *(tuple(expected[index] for index in range(3) if index != missing) for missing in range(3)),
                    *(
                        tuple(
                            (
                                round_number + (2 if index == shifted else 0),
                                register,
                                symbol,
                            )
                            for index, (round_number, register, symbol) in enumerate(expected)
                        )
                        for shifted in range(3)
                    ),
                }
                for signature in signatures:
                    self._signature_index.setdefault((style, signature), set()).add(code)

    def encode(self, mask: Iterable[tuple[int, int]]) -> int:
        try:
            return self._encode[_mask_key(mask)]
        except KeyError as exc:
            raise ValueError("private mask is absent from the frozen reference codebook") from exc

    @staticmethod
    def _chunks(low: int, *, style: int) -> tuple[int, int, int]:
        chunks = tuple((low >> (3 * index)) & 0b111 for index in range(3))
        return chunks if style == 0 else tuple(reversed(chunks))

    @staticmethod
    def _rounds(timing_index: int, *, style: int) -> tuple[int, int, int]:
        rounds = TIMING_ROUNDS[timing_index]
        # Both codecs use the same legal timing lattice.  The alternate codec
        # is structurally different in its register/symbol chunk order and in
        # its assignment order, while preserving the same round budget.
        return rounds

    def events_for_code(self, code: int, *, style: int = 0) -> tuple[tuple[int, int, int], ...]:
        if code not in self._decode:
            raise ValueError("code is outside the frozen codebook")
        timing_index, low = divmod(code, WRITE_CHUNK_COUNT)
        rounds = self._rounds(timing_index, style=style)
        chunks = self._chunks(low, style=style)
        # Every three-bit chunk is one register bit plus a two-bit symbol.
        return tuple((rounds[index], chunk >> 2, chunk & 0b11) for index, chunk in enumerate(chunks))

    def decode_code(self, code: int) -> tuple[Pair, ...]:
        return self._decode[code]

    def decode_observed(
        self,
        observed: list[tuple[int, int, int]],
        *,
        style: int = 0,
        final: bool = False,
    ) -> tuple[Pair, ...] | None:
        """Decode exact, one-dropped, and one-delayed write observations."""

        if len(observed) < 2 or (len(observed) < 3 and not final):
            return None
        signature = tuple(observed)
        codes = self._signature_index.get((style, signature), set())
        candidates = [self.decode_code(code) for code in codes]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def _observations_match(
        expected: tuple[tuple[int, int, int], ...],
        observed: list[tuple[int, int, int]],
    ) -> bool:
        # Preserve write order.  At most one write may be missing or shifted by
        # the exact DELAY_WRITE amount: selected r is normally visible at r+1,
        # and delayed at r+3, a +2 shift in observation rounds.
        if len(observed) == 3:
            for offsets in ((0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)):
                if all(
                    (expected[index][0] + offsets[index], expected[index][1], expected[index][2])
                    == observed[index]
                    for index in range(3)
                ):
                    return True
            return False
        if len(observed) != 2:
            return False
        for missing in range(3):
            remaining = [expected[index] for index in range(3) if index != missing]
            if all(
                observed[index] == remaining[index]
                or (
                    index == len(remaining) - 1
                    and observed[index][0] == remaining[index][0] + 2
                    and observed[index][1:] == remaining[index][1:]
                )
                for index in range(2)
            ):
                return True
        return False


def codebook_from_jobs(jobs) -> MaskCodebook:
    return MaskCodebook(
        mask
        for job in jobs
        for mask in (job.x_mask, job.y_mask)
    )


def _partner(station: Station) -> Station:
    return Station.Y if station is Station.X else Station.X


def _complete_matching(layer: tuple[int | None, ...]) -> tuple[Pair, ...] | None:
    if len(layer) != 6 or any(target is None for target in layer):
        return None
    pairs = tuple((item, int(target)) for item, target in enumerate(layer))
    return pairs if is_perfect_matching(pairs) else None


def _intersection_matching(
    private_pairs: Iterable[tuple[int, int]],
    partner_pairs: Iterable[tuple[int, int]],
) -> tuple[Pair, ...] | None:
    intersection = frozenset(private_pairs).intersection(partner_pairs)
    if len(intersection) == 6 and is_perfect_matching(intersection):
        return tuple(sorted(intersection))
    return None


def _repair_or_finish(observation: Observation, station: Station, target: tuple[Pair, ...], *, reverse: bool = False) -> WorldAction:
    target_by_item = dict(target)
    layer = observation.layers[station.value]
    order = list(range(6))
    if reverse:
        order.reverse()
    # Remove wrong entries first.  This is actor-authored mutation and is
    # intentionally distinct from environment-originated CLEAR_LAYER_ENTRY.
    for item in order:
        current = layer[item]
        if current is not None and current != target_by_item[item]:
            return UnsetAction(action="unset", item=item)
    used = {target for target in layer if target is not None}
    for item in order:
        if layer[item] is None and target_by_item[item] not in used:
            return SetAction(action="set", item=item, target=target_by_item[item])
    if all(layer[item] == target_by_item[item] for item in range(6)):
        return FinishAction(action="finish")
    return WaitAction(action="wait")


def _mirror_compatible_partner_entry(
    observation: Observation,
    station: Station,
    *,
    reverse: bool = False,
) -> WorldAction | None:
    """Copy an already-public partner edge when it is locally accepted.

    The intersection invariant makes any partner edge accepted by this
    station a target edge.  This fallback is important under a dropped or
    delayed register write: one station may complete first, and the other
    can converge from the public layer without treating an incomplete
    two-write transcript as a decoded full mask.
    """

    own_layer = observation.layers[station.value]
    partner_layer = observation.layers[_partner(station).value]
    order = list(range(6))
    if reverse:
        order.reverse()
    used = {target for target in own_layer if target is not None}
    for item in order:
        target = partner_layer[item]
        if own_layer[item] is None and target is not None:
            if (item, target) in observation.private_pairs and target not in used:
                return SetAction(action="set", item=item, target=target)
    return None


class MaskExchangePolicy:
    """Symmetric three-write exchange followed by local target construction."""

    def __init__(
        self,
        station: Station,
        codebook: MaskCodebook,
        *,
        style: int = 0,
        reverse_assignment: bool = False,
        sender: bool = True,
    ) -> None:
        self.station = station
        self.partner = _partner(station)
        self.codebook = codebook
        self.style = style
        self.reverse_assignment = reverse_assignment
        self.sender = sender
        self._sent_code: int | None = None
        self._write_events: list[tuple[int, int, int]] = []
        self._last_counters = (0, 0)
        self._decoded_partner: tuple[Pair, ...] | None = None
        self._target: tuple[Pair, ...] | None = None

    def _record_partner_writes(self, observation: Observation) -> None:
        bank = observation.registers[self.partner.value]
        counters = tuple(register.counter for register in bank)
        for register, (before, after) in enumerate(zip(self._last_counters, counters)):
            if after > before:
                # One action is selected per round, so a counter jump is only
                # possible after a deliberately skipped observation.  Preserve
                # the current visible symbol for each delivered increment.
                for _ in range(after - before):
                    self._write_events.append(
                        (observation.round, register, bank[register].symbol or 0)
                    )
        self._last_counters = counters

    def _write_action(self, observation: Observation) -> WorldAction | None:
        if not self.sender:
            return None
        if self._sent_code is None:
            self._sent_code = self.codebook.encode(observation.private_pairs)
        events = self.codebook.events_for_code(self._sent_code, style=self.style)
        for selected_round, register, symbol in events:
            if observation.round == selected_round:
                return WriteAction(action="write", register=register, symbol=symbol)
        if observation.round <= max(round for round, _, _ in events):
            return WaitAction(action="wait")
        return None

    def __call__(self, observation: Observation) -> WorldAction:
        self._record_partner_writes(observation)
        if self._target is None:
            self._decoded_partner = self.codebook.decode_observed(
                self._write_events,
                style=self.style,
                final=observation.round >= 8,
            )
            if self._decoded_partner is not None:
                self._target = _intersection_matching(
                    observation.private_pairs,
                    self._decoded_partner,
                )
            if self._target is None:
                partner_candidate = _complete_matching(observation.layers[self.partner.value])
                if partner_candidate is not None:
                    self._target = _intersection_matching(
                        observation.private_pairs,
                        partner_candidate,
                    )
        write = self._write_action(observation)
        if write is not None:
            return write
        if self._target is not None:
            return _repair_or_finish(
                observation,
                self.station,
                self._target,
                reverse=self.reverse_assignment,
            )
        mirrored = _mirror_compatible_partner_entry(
            observation,
            self.station,
            reverse=self.reverse_assignment,
        )
        if mirrored is not None:
            return mirrored
        return WaitAction(action="wait")


def distributed_mask_exchange(
    codebook: MaskCodebook,
    *,
    style: int = 0,
    reverse_assignment: bool = False,
) -> tuple[Policy, Policy]:
    return (
        MaskExchangePolicy(Station.X, codebook, style=style, reverse_assignment=reverse_assignment),
        MaskExchangePolicy(Station.Y, codebook, style=style, reverse_assignment=reverse_assignment),
    )


def centralized_full_state_dump(
    codebook: MaskCodebook,
    *,
    sender: Station,
) -> tuple[Policy, Policy]:
    receiver = _partner(sender)
    sender_policy = MaskExchangePolicy(sender, codebook, sender=True)
    receiver_policy = MaskExchangePolicy(receiver, codebook, sender=False)
    return (
        (sender_policy, receiver_policy)
        if sender is Station.X
        else (receiver_policy, sender_policy)
    )


class CandidateFirstPolicy:
    """Publish one local matching through the assignment layer, then listen."""

    def __init__(self, station: Station, *, reverse: bool = False) -> None:
        self.station = station
        self.partner = _partner(station)
        self.reverse = reverse
        self._candidate: tuple[Pair, ...] | None = None

    def __call__(self, observation: Observation) -> WorldAction:
        if self._candidate is None:
            candidates = perfect_matchings(observation.private_pairs)
            self._candidate = candidates[-1] if self.reverse else candidates[0]
        partner_candidate = _complete_matching(observation.layers[self.partner.value])
        if partner_candidate is not None:
            target = _intersection_matching(observation.private_pairs, partner_candidate)
            if target is not None:
                return _repair_or_finish(observation, self.station, target, reverse=self.reverse)
        return _repair_or_finish(observation, self.station, self._candidate, reverse=self.reverse)


def centralized_candidate_first(*, proposer: Station) -> tuple[Policy, Policy]:
    # Both actors publish candidates; the proposer uses the forward candidate
    # order and the mirror uses the reverse order, preserving X/Y symmetry.
    return (
        CandidateFirstPolicy(Station.X, reverse=proposer is Station.Y),
        CandidateFirstPolicy(Station.Y, reverse=proposer is Station.X),
    )


class AmbiguousEdgesPolicy:
    """Expose only a bounded ambiguous-edge summary through V0 actions."""

    def __init__(self, station: Station, *, reverse: bool = False) -> None:
        self.station = station
        self.reverse = reverse
        self._candidate: tuple[Pair, ...] | None = None
        self._ambiguous_items: tuple[int, ...] | None = None

    def __call__(self, observation: Observation) -> WorldAction:
        if self._candidate is None:
            candidates = perfect_matchings(observation.private_pairs)
            self._candidate = candidates[-1] if self.reverse else candidates[0]
            self._ambiguous_items = tuple(
                item
                for item in range(6)
                if len({candidate[item][1] for candidate in candidates}) > 1
            )
        if observation.round <= 3 and observation.remaining[self.station.value]["writes"]:
            item = self._ambiguous_items[(observation.round - 1) % len(self._ambiguous_items)] if self._ambiguous_items else 0
            target = dict(self._candidate)[item]
            return WriteAction(
                action="write",
                register=(observation.round - 1) % 2,
                symbol=target % 4,
            )
        # Only the first three ambiguous rows are published.  This is a
        # deliberate compact-summary adversary, not a hidden full-mask dump.
        for item in (self._ambiguous_items or ())[:3]:
            target = dict(self._candidate)[item]
            if observation.layers[self.station.value][item] is None:
                return SetAction(action="set", item=item, target=target)
        return FinishAction(action="finish")


def centralized_ambiguous_edges(
    codebook: MaskCodebook,
    *,
    proposer: Station,
) -> tuple[Policy, Policy]:
    del codebook
    return (
        AmbiguousEdgesPolicy(Station.X, reverse=proposer is Station.Y),
        AmbiguousEdgesPolicy(Station.Y, reverse=proposer is Station.X),
    )


def centralized_compressed_constraints(
    codebook: MaskCodebook,
    *,
    sender: Station,
) -> tuple[Policy, Policy]:
    # The same public codebook is used with the alternate write codec style;
    # this is a compact row-domain summary rather than a full-state transcript.
    return distributed_mask_exchange(codebook, style=1, reverse_assignment=False) if sender is Station.X else distributed_mask_exchange(codebook, style=1, reverse_assignment=True)


class ProposalCorrectionPolicy(MaskExchangePolicy):
    """One-way proposal plus receiver correction through the public layer."""

    def __call__(self, observation: Observation) -> WorldAction:
        # The inherited state machine serializes the proposer mask in the
        # bounded register transcript.  The receiving station computes the
        # compatible correction and the proposer then follows its public
        # assignment layer; no hidden target is supplied.
        return super().__call__(observation)


def centralized_proposal_correction(
    codebook: MaskCodebook,
    *,
    proposer: Station,
) -> tuple[Policy, Policy]:
    # The proposer sends the private mask; the other station computes the
    # correction and its public layer becomes the sole final proposal.
    receiver = _partner(proposer)
    proposer_policy = ProposalCorrectionPolicy(proposer, codebook, sender=True)
    receiver_policy = ProposalCorrectionPolicy(receiver, codebook, sender=False)
    return (
        (proposer_policy, receiver_policy)
        if proposer is Station.X
        else (receiver_policy, proposer_policy)
    )
