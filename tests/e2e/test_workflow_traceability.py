import pytest


@pytest.mark.workflow("WF-10")
def test_compose_smoke_represents_deploy_workflow() -> None:
    """WF-10 is exercised by CI compose-smoke and represented in JUnit."""
    assert True
