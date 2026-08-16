import pytest

from h1_live_runtime_adapter_v1.qualification import run_qualification


@pytest.fixture(scope="session")
def qualification_report():
    return run_qualification()

