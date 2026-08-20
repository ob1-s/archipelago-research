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
    """Count factor decompositions containing each local matching.

    A generated private mask is a union of three edge-disjoint perfect
    matchings.  Enumerating those decompositions is the strongest finite,
    generator-aware prior available without observing the partner mask: the
    target factor is uniformly one of the selected factors, while matchings
    that cannot occur as a factor receive zero support.
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
        decomposition = tuple(
            pair for index in indexes for pair in candidates[index]
        )
        decompositions.append(decomposition)
        for index in indexes:
            counts[index] += 1
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
