"""Performance tests conftest."""
def pytest_configure(config):
    config.addinivalue_line("markers", "performance: performance benchmarks")
    config.addinivalue_line("markers", "slow: slow running tests")
