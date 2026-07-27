"""Security tests conftest."""
def pytest_configure(config):
    config.addinivalue_line("markers", "security: security-focused tests")
