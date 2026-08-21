from constraint_forge_behavioral_runner_v0.harness import TEXT_PROGRAM_SOURCE


def test_embedded_harness_has_closed_pep723_script_metadata() -> None:
    lines = TEXT_PROGRAM_SOURCE.splitlines()
    assert lines[0] == "# /// script"
    assert "# dependencies = [\"openai\"]" in lines
    closing = lines.index("# ///", 1)
    assert closing > lines.index("# dependencies = [\"openai\"]")
    assert lines[closing + 1].startswith('"""One plain, non-streaming')
