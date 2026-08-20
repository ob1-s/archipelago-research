from constraint_forge_formation_v0.generator import (
    generate_job,
    generator_conditioned_map,
    generator_conditioned_support,
    generate_jobs,
)
from constraint_forge_formation_v0.models import Station
from constraint_forge_formation_v0.policies import (
    CandidateFirstProposerPolicy,
    CandidateFirstReceiverPolicy,
    CompressedConstraintPolicy,
    ConstraintCodebook,
    MutualConsensusPolicy,
    ProposalCorrectionProposerPolicy,
    ProposalCorrectionReceiverPolicy,
    centralized_ambiguous_edges,
    centralized_candidate_first,
    centralized_compressed_constraints,
    centralized_proposal_correction,
    codebook_from_jobs,
    distributed_mask_exchange,
    distributed_mutual_consensus,
)
from constraint_forge_formation_v0.preflight import (
    binomial_upper_95,
    generator_and_solo_gate,
)
from constraint_forge_formation_v0.world import run_job


def test_generator_map_uses_only_cyclic_generator_support() -> None:
    job = generate_job("fixed-seed-7")
    support = generator_conditioned_support(job.x_mask)
    selected = generator_conditioned_map(job.x_mask)

    assert selected == ((0, 0), (1, 3), (2, 4), (3, 5), (4, 1), (5, 2))
    assert selected in support
    assert support[selected] == max(support.values())
    assert support[tuple(job.target_matching)] > 0
    assert sum(value > 0 for value in support.values()) < len(support)


def test_generator_conditioned_solo_gate_is_wired_to_exact_map() -> None:
    jobs = generate_jobs(f"policy-test/{index}" for index in range(80))
    report = generator_and_solo_gate(jobs)
    assert report["generator_invariants_passed"]
    assert report["duplicate_payloads"] is False
    assert report["solo_x"]["successes"] == sum(
        generator_conditioned_map(job.x_mask) == tuple(job.target_matching)
        for job in jobs
    )
    assert report["solo_y"]["successes"] == sum(
        generator_conditioned_map(job.y_mask) == tuple(job.target_matching)
        for job in jobs
    )
    assert binomial_upper_95(0, 80) < binomial_upper_95(1, 80)


def test_centralized_rows_are_role_directed_and_not_aliases() -> None:
    jobs = generate_jobs(f"policy-test/central/{index}" for index in range(12))
    codebook = codebook_from_jobs(jobs)

    candidate_x = centralized_candidate_first(proposer=Station.X)
    candidate_y = centralized_candidate_first(proposer=Station.Y)
    assert isinstance(candidate_x[0], CandidateFirstProposerPolicy)
    assert isinstance(candidate_x[1], CandidateFirstReceiverPolicy)
    assert isinstance(candidate_y[0], CandidateFirstReceiverPolicy)
    assert isinstance(candidate_y[1], CandidateFirstProposerPolicy)

    compressed = centralized_compressed_constraints(codebook, sender=Station.X)
    assert isinstance(compressed[0], CompressedConstraintPolicy)
    assert isinstance(compressed[1], CompressedConstraintPolicy)
    assert compressed[0].sender is True
    assert compressed[1].sender is False
    assert not isinstance(compressed[0], type(distributed_mask_exchange(codebook)[0]))

    proposal = centralized_proposal_correction(codebook, proposer=Station.X)
    assert isinstance(proposal[0], ProposalCorrectionProposerPolicy)
    assert isinstance(proposal[1], ProposalCorrectionReceiverPolicy)

    ambiguous = centralized_ambiguous_edges(codebook, proposer=Station.X)
    assert type(ambiguous[0]).__name__ == "AmbiguousEdgesProposerPolicy"
    assert type(ambiguous[1]).__name__ == "AmbiguousEdgesReceiverPolicy"


def test_distributed_witnesses_have_distinct_protocol_types_and_run() -> None:
    jobs = generate_jobs(f"policy-test/witness/{index}" for index in range(24))
    codebook = codebook_from_jobs(jobs)
    first = distributed_mask_exchange(codebook)
    second = distributed_mutual_consensus(codebook)

    assert isinstance(second[0], MutualConsensusPolicy)
    assert isinstance(second[1], MutualConsensusPolicy)
    assert not isinstance(first[0], MutualConsensusPolicy)
    assert second[0].ASSIGNMENT_PHASES == ((0, 1, 2), (3, 4, 5))

    for index, job in enumerate(jobs[:4]):
        policies = distributed_mutual_consensus(codebook)
        result = run_job(
            job,
            run_id=f"policy-test:{index}",
            lineage_id="policy-test",
            job_id=f"policy-test:{index}",
            policy_x=policies[0],
            policy_y=policies[1],
            read_only_probe=True,
        )
        assert result.event_log.events


def test_constraint_codebook_round_trips_row_domain_summary() -> None:
    jobs = generate_jobs(f"policy-test/constraints/{index}" for index in range(8))
    codebook = ConstraintCodebook(tuple(job.x_mask for job in jobs))
    for job in jobs:
        code = codebook.encode(job.x_mask)
        assert codebook.decode_signature(code) == tuple(
            sum(1 << target for item, target in job.x_mask if item == row)
            for row in range(6)
        )
