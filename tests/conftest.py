import pytest

@pytest.fixture
def sample_fixture():
    return "sample data"

def pytest_configure(config):
    config.addinivalue_line("markers", "sample: mark test as sample")