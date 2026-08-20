from constraint_forge_formation_v0.generator import (
    generate_job,
    generator_conditioned_map,
    perfect_matchings,
    validate_job,
)


def test_seed_reproduces_complete_record() -> None:
    first = generate_job("fixed-seed-7")
    second = generate_job("fixed-seed-7")
    assert first == second
    assert first.payload_hash == second.payload_hash
    assert validate_job(first) == first


def test_presentations_are_seeded_permutations_not_sorted_masks() -> None:
    job = generate_job("presentation-permutation")
    assert set(job.x_presentation) == set(job.x_mask)
    assert set(job.y_presentation) == set(job.y_mask)
    assert job.x_presentation != tuple(sorted(job.x_presentation)) or job.y_presentation != tuple(
        sorted(job.y_presentation)
    )


def test_generator_invariants_hold_across_frozen_sample() -> None:
    jobs = [generate_job(index) for index in range(250)]
    assert len({job.payload_hash for job in jobs}) == len(jobs)
    for job in jobs:
        assert len(job.intersection) == 6
        assert len(perfect_matchings(job.x_mask)) >= 3
        assert len(perfect_matchings(job.y_mask)) >= 3
        assert generator_conditioned_map(job.x_mask)
