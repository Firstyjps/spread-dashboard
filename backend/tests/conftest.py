# file: backend/tests/conftest.py
"""Shared test fixtures."""
import pytest


@pytest.fixture(autouse=True)
def reset_alert_states():
    """Reset alert engine state before each test."""
    from app.alerts.alert_engine import reset_states
    from app.services.circuit_breaker import circuit_breaker
    reset_states()
    circuit_breaker.reset()
    yield
    reset_states()
    circuit_breaker.reset()
