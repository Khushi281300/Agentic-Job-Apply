"""Circuit breaker pattern — auto-disables failing services.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is down, requests fail immediately
- HALF_OPEN: Probing if service recovered (limited calls allowed)

Usage:
    from job_agent_services.resilience import circuit_registry

    breaker = circuit_registry.get("remoteok")
    async with breaker.protect():
        result = await do_request()
"""

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Tuning parameters for a circuit breaker."""
    failure_threshold: int = 5         # consecutive failures to trip
    recovery_timeout_secs: float = 60.0  # how long OPEN state lasts
    half_open_max_calls: int = 2       # probe calls allowed in HALF_OPEN
    success_threshold: int = 2         # successes needed to re-close


class CircuitBreaker:
    """Production circuit breaker with half-open probing and observability."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None,
                 on_state_change: Callable[[str, CircuitState], None] | None = None):
        self.name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._last_transition_time = time.time()
        self._on_state_change = on_state_change

    @property
    def state(self) -> CircuitState:
        """Current state (auto-transitions OPEN → HALF_OPEN after timeout)."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self._config.recovery_timeout_secs:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_available(self) -> bool:
        """True if requests can pass through."""
        return self.state != CircuitState.OPEN

    def _transition(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        self._last_transition_time = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0

        if old != new_state:
            logger.info("CircuitBreaker[%s]: %s → %s", self.name, old.value, new_state.value)
            if self._on_state_change:
                self._on_state_change(self.name, new_state)

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._config.success_threshold:
                self._transition(CircuitState.CLOSED)
                self._failure_count = 0
        else:
            self._failure_count = 0
            if self._state != CircuitState.CLOSED:
                self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self._failure_count >= self._config.failure_threshold:
            self._transition(CircuitState.OPEN)

    @asynccontextmanager
    async def protect(self) -> AsyncGenerator[None, None]:
        """Context manager enforcing circuit breaker logic.

        Raises CircuitOpenError if circuit is open.
        Automatically records success/failure.
        """
        if not self.is_available:
            raise CircuitOpenError(self.name, self._config.recovery_timeout_secs)

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls > self._config.half_open_max_calls:
                raise CircuitOpenError(self.name, self._config.recovery_timeout_secs)

        try:
            yield
            self.record_success()
        except Exception:
            self.record_failure()
            raise

    def health(self) -> dict:
        """Monitoring-friendly health snapshot."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure_ago_secs": (
                round(time.time() - self._last_failure_time, 1)
                if self._last_failure_time else None
            ),
            "config": {
                "failure_threshold": self._config.failure_threshold,
                "recovery_timeout_secs": self._config.recovery_timeout_secs,
            },
        }


class CircuitOpenError(Exception):
    """Raised when requests are blocked by an open circuit."""

    def __init__(self, source_name: str, recovery_secs: float):
        self.source_name = source_name
        self.recovery_secs = recovery_secs
        super().__init__(
            f"Circuit breaker '{source_name}' is OPEN. Recovery in ~{recovery_secs:.0f}s."
        )


class CircuitBreakerRegistry:
    """Centralized registry of circuit breakers for all services/sources."""

    def __init__(self, default_config: CircuitBreakerConfig | None = None):
        self._default = default_config or CircuitBreakerConfig()
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        """Get or create a circuit breaker by name."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config or self._default)
        return self._breakers[name]

    def health(self) -> dict[str, dict]:
        """Health status for all tracked breakers."""
        return {name: b.health() for name, b in self._breakers.items()}

    def all_available(self) -> dict[str, bool]:
        """Quick availability map."""
        return {name: b.is_available for name, b in self._breakers.items()}


# Module-level singleton
circuit_registry = CircuitBreakerRegistry()
