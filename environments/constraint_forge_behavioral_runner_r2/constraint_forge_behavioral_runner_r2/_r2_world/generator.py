"""Exact seeded six-by-six one-factorization generator."""

from __future__ import annotations

from itertools import combinations, permutations
from functools import lru_cache
from typing import Iterable, Sequence

from .canonical import canonical_bytes
from .models import JobRecord, Pair, Seed

N = 6
ITEM_IDS = tuple(range(N))
TARGET_IDS = tuple(range(N))
FACTORS = tuple(range(N))


def _cycle_permutations() -> tuple[tuple[int, ...], ...]:
    """Return every directed six-cycle on the item IDs."""

    cycles: list[tuple[int, ...]] = []
    for tail in permutations(ITEM_IDS[1:]):
        sequence = (ITEM_IDS[0], *tail)
        cycle = [0] * N
        for index, item in enumerate(sequence):
            cycle[item] = sequence[(index + 1) % N]
        cycles.append(tuple(cycle))
    return tuple(cycles)


_CYCLE_PERMUTATIONS = _cycle_permutations()


def _compose(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(left[right[index]] for index in ITEM_IDS)


@lru_cache(maxsize=100_000)
def _cyclic_orientation_count(
    first: tuple[int, ...], second: tuple[int, ...]
) -> int:
    """Count cyclic generators whose powers are two observed factor gaps."""

    count = 0
    for cycle in _CYCLE_PERMUTATIONS:
        power = tuple(ITEM_IDS)
        first_gap: int | None = None
        second_gap: int | None = None
        for gap in range(1, N):
            power = _compose(cycle, power)
            if power == first:
                first_gap = gap
            if power == second:
                second_gap = gap
        if first_gap is not None and second_gap is not None and first_gap != second_gap:
            count += 1
    return count


class _SeedStream:
    """Counter-based deterministic stream with unbiased finite sampling."""

    def __init__(self, seed: Seed, domain: str) -> None:
        self._seed = canonical_bytes(
            {"schema": "constraint-forge/prng/v0", "seed": seed, "domain": domain}
        )
        self._counter = 0

    def _word(self) -> int:
        import hashlib

        digest = hashlib.sha256(
            self._seed + self._counter.to_bytes(16, "big")
        ).digest()
        self._counter += 1
        return int.from_bytes(digest, "big")

    def randbelow(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("upper bound must be positive")
        limit = (1 << 256) - ((1 << 256) % upper)
        while True:
            value = self._word()
            if value < limit:
                return value % upper

    def permutation(self, values: Sequence[int]) -> tuple[int, ...]:
        result = list(values)
        for index in range(len(result) - 1, 0, -1):
            swap = self.randbelow(index + 1)
            result[index], result[swap] = result[swap], result[index]
        return tuple(result)

    def sample(self, values: Sequence[int], count: int) -> tuple[int, ...]:
        if not 0 <= count <= len(values):
            raise ValueError("invalid sample count")
        return tuple(self.permutation(values)[:count])


def _matching(rho: Sequence[int], sigma: Sequence[int], factor: int) -> frozenset[tuple[int, int]]:
    return frozenset(
        (rho[item], sigma[(item + factor) % N]) for item in range(N)
    )


def _sorted_pairs(pairs: Iterable[tuple[int, int]]) -> tuple[Pair, ...]:
    return tuple((int(item), int(target)) for item, target in sorted(pairs))


def perfect_matchings(mask: Iterable[tuple[int, int]]) -> tuple[tuple[Pair, ...], ...]:
    """Enumerate all perfect matchings of a six-item private graph."""

    edges = frozenset(mask)
    matches: list[tuple[Pair, ...]] = []
    for assignment in permutations(TARGET_IDS):
        candidate = tuple((item, assignment[item]) for item in ITEM_IDS)
        if all(edge in edges for edge in candidate):
            matches.append(_sorted_pairs(candidate))
    return tuple(matches)


@lru_cache(maxsize=100_000)
def _matching_decomposition_counts(
    canonical_mask: tuple[Pair, ...],
) -> tuple[tuple[Pair, ...], tuple[tuple[Pair, ...], ...], tuple[int, ...]]:
    """Count only decompositions compatible with V0's cyclic factorization.

    An arbitrary 3-edge-coloring of the observed mask is not a generator
    state.  For each disjoint triple of local perfect matchings, this routine
    checks whether the two relative permutations are distinct powers of one
    common directed six-cycle.  Each compatible cyclic orientation is one
    equal-weight family of latent ``rho``/``sigma`` states; target-factor
    choices are then uniform over the three observed factors.
    """

    candidates = perfect_matchings(canonical_mask)
    candidate_sets = [frozenset(candidate) for candidate in candidates]
    mask = frozenset(canonical_mask)
    counts = [0] * len(candidates)
    decompositions: list[tuple[Pair, ...]] = []
    for indexes in combinations(range(len(candidates)), 3):
        union = candidate_sets[indexes[0]] | candidate_sets[indexes[1]] | candidate_sets[indexes[2]]
        if len(union) != 18 or union != mask:
            continue
        if any(
            candidate_sets[left].intersection(candidate_sets[right])
            for left, right in combinations(indexes, 2)
        ):
            continue
        selected = tuple(candidates[index] for index in indexes)
        orientation_count = 0
        for base_index, base in enumerate(selected):
            base_inverse = {target: item for item, target in base}
            other = [selected[index] for index in range(3) if index != base_index]
            normalized = tuple(
                tuple(
                    base_inverse[dict(match)[item]]
                    for item in ITEM_IDS
                )
                for match in other
            )
            orientation_count += _cyclic_orientation_count(*normalized)
        if orientation_count == 0:
            continue
        decomposition = tuple(pair for match in selected for pair in match)
        decompositions.append(decomposition)
        for index in indexes:
            counts[index] += orientation_count
    return candidates, tuple(decompositions), tuple(counts)


def generator_conditioned_map(
    mask: Iterable[tuple[int, int]],
) -> tuple[Pair, ...]:
    """Return the deterministic MAP matching for one private panel."""

    canonical_mask = _sorted_pairs(mask)
    candidates, decompositions, counts = _matching_decomposition_counts(canonical_mask)
    if not candidates:
        raise ValueError("private mask has no perfect matching")
    if not decompositions:
        # This branch is useful for adversarial parser tests; valid V0 jobs
        # always have at least one three-factor decomposition.
        return candidates[0]
    best = max(range(len(candidates)), key=lambda index: (counts[index], tuple(candidates[index])))
    return candidates[best]


def generator_conditioned_support(
    mask: Iterable[tuple[int, int]],
) -> dict[tuple[Pair, ...], int]:
    canonical_mask = _sorted_pairs(mask)
    candidates, _, counts = _matching_decomposition_counts(canonical_mask)
    return {candidate: counts[index] for index, candidate in enumerate(candidates)}


def is_perfect_matching(edges: Iterable[tuple[int, int]]) -> bool:
    pairs = tuple(edges)
    return (
        len(pairs) == N
        and len({item for item, _ in pairs}) == N
        and len({target for _, target in pairs}) == N
    )


def validate_job(job: JobRecord) -> JobRecord:
    """Validate every generator invariant without using model inference."""

    job = JobRecord.model_validate(job.model_dump(mode="python"))
    if set(job.rho) != set(ITEM_IDS) or len(job.rho) != N:
        raise ValueError("rho is not a complete item permutation")
    if set(job.sigma) != set(TARGET_IDS) or len(job.sigma) != N:
        raise ValueError("sigma is not a complete target permutation")
    factor_partition = (
        job.target_factor,
        *job.x_decoy_factors,
        *job.y_decoy_factors,
        job.unused_factor,
    )
    if sorted(factor_partition) != list(FACTORS):
        raise ValueError("factor selection is not a partition of all six factors")
    if len(set(job.x_decoy_factors)) != 2 or len(set(job.y_decoy_factors)) != 2:
        raise ValueError("decoy factors must be distinct")

    x_edges = frozenset(job.x_mask)
    y_edges = frozenset(job.y_mask)
    target_edges = frozenset(job.target_matching)
    if len(x_edges) != 18 or len(y_edges) != 18:
        raise ValueError("private masks must contain exactly 18 unique edges")
    if len(target_edges) != N or not is_perfect_matching(target_edges):
        raise ValueError("target factor is not one perfect matching")
    if x_edges.intersection(y_edges) != target_edges:
        raise ValueError("private masks do not share exactly the target matching")
    for label, mask in (("X", x_edges), ("Y", y_edges)):
        if any(sum(item == row for item, _ in mask) != 3 for row in ITEM_IDS):
            raise ValueError(f"{label} mask has a non-three item degree")
        if any(sum(target == column for _, target in mask) != 3 for column in TARGET_IDS):
            raise ValueError(f"{label} mask has a non-three target degree")
        if len(perfect_matchings(mask)) < 3:
            raise ValueError(f"{label} mask admits fewer than three matchings")
    if set(job.x_presentation) != x_edges or set(job.y_presentation) != y_edges:
        raise ValueError("presentation order does not contain the exact private mask")
    if len(job.x_presentation) != 18 or len(job.y_presentation) != 18:
        raise ValueError("presentation order must contain all 18 edges")
    return job


def generate_job(seed: Seed) -> JobRecord:
    """Generate the exact immutable V0 job record from one seed."""

    rho = _SeedStream(seed, "rho").permutation(ITEM_IDS)
    sigma = _SeedStream(seed, "sigma").permutation(TARGET_IDS)
    factor_stream = _SeedStream(seed, "factor-selection")
    target_factor = factor_stream.randbelow(N)
    remaining = tuple(factor for factor in FACTORS if factor != target_factor)
    x_decoys = tuple(sorted(factor_stream.sample(remaining, 2)))
    remaining_after_x = tuple(factor for factor in remaining if factor not in x_decoys)
    y_decoys = tuple(sorted(factor_stream.sample(remaining_after_x, 2)))
    unused = next(
        factor
        for factor in remaining_after_x
        if factor not in y_decoys
    )

    target_matching = _matching(rho, sigma, target_factor)
    x_mask = frozenset(
        target_matching
        | _matching(rho, sigma, x_decoys[0])
        | _matching(rho, sigma, x_decoys[1])
    )
    y_mask = frozenset(
        target_matching
        | _matching(rho, sigma, y_decoys[0])
        | _matching(rho, sigma, y_decoys[1])
    )
    x_presentation = _SeedStream(seed, "presentation-X").permutation(
        tuple(sorted(x_mask))
    )
    y_presentation = _SeedStream(seed, "presentation-Y").permutation(
        tuple(sorted(y_mask))
    )
    job = JobRecord(
        job_seed=seed,
        rho=rho,
        sigma=sigma,
        target_factor=target_factor,
        x_decoy_factors=x_decoys,  # type: ignore[arg-type]
        y_decoy_factors=y_decoys,  # type: ignore[arg-type]
        unused_factor=unused,
        target_matching=_sorted_pairs(target_matching),
        x_mask=_sorted_pairs(x_mask),
        y_mask=_sorted_pairs(y_mask),
        x_presentation=tuple((int(item), int(target)) for item, target in x_presentation),
        y_presentation=tuple((int(item), int(target)) for item, target in y_presentation),
    )
    return validate_job(job)


def job_payload_hash(seed: Seed) -> str:
    return generate_job(seed).payload_hash


def generate_jobs(seeds: Iterable[Seed]) -> tuple[JobRecord, ...]:
    jobs = tuple(generate_job(seed) for seed in seeds)
    hashes = [job.payload_hash for job in jobs]
    if len(hashes) != len(set(hashes)):
        raise ValueError("duplicate generated job payload")
    return jobs
