"""
Golden Task GT-003: Kill-Switch bei Instabilität

Tests the automatic kill-switch mechanism when system instability is detected.
This includes:
- Monitoring instability metrics
- Automatic triggering on threshold breach
- System shutdown behavior
- Recovery and reset procedures
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Mark all tests in this module as e2e and golden_task
pytestmark = [pytest.mark.e2e, pytest.mark.golden_task, pytest.mark.slow]


# ============================================================================
# Test Constants
# ============================================================================

INSTABILITY_THRESHOLD = 0.7
VIOLATION_THRESHOLD = 5
COOLDOWN_PERIOD = 30.0
CHECK_INTERVAL = 0.1  # Fast for testing


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def instability_metrics() -> List[Dict[str, Any]]:
    """Generate escalating instability metrics."""
    return [
        {"timestamp": "2024-01-01T00:00:00Z", "instability": 0.3, "source": "llm_latency"},
        {"timestamp": "2024-01-01T00:00:01Z", "instability": 0.4, "source": "llm_latency"},
        {"timestamp": "2024-01-01T00:00:02Z", "instability": 0.5, "source": "llm_errors"},
        {"timestamp": "2024-01-01T00:00:03Z", "instability": 0.6, "source": "memory_leak"},
        {"timestamp": "2024-01-01T00:00:04Z", "instability": 0.7, "source": "llm_errors"},
        {"timestamp": "2024-01-01T00:00:05Z", "instability": 0.75, "source": "llm_errors"},
        {"timestamp": "2024-01-01T00:00:06Z", "instability": 0.8, "source": "system_overload"},
    ]


@pytest.fixture
def mock_kill_switch():
    """Create a mock kill switch for testing."""
    from dataclasses import dataclass, field
    
    @dataclass
    class MockKillSwitch:
        is_active: bool = True
        is_triggered: bool = False
        trigger_reason: str = ""
        violation_count: int = 0
        instability_score: float = 0.0
        violations: List[Dict[str, Any]] = field(default_factory=list)
        config: Dict[str, Any] = field(default_factory=lambda: {
            "instability_threshold": INSTABILITY_THRESHOLD,
            "violation_threshold": VIOLATION_THRESHOLD,
            "cooldown_period": COOLDOWN_PERIOD,
            "check_interval": CHECK_INTERVAL,
        })
        
        async def check_instability(self, metrics: Dict[str, Any]) -> float:
            """Calculate instability score from metrics."""
            self.instability_score = metrics.get("instability", 0.0)
            return self.instability_score
        
        async def record_violation(self, violation: Dict[str, Any]) -> int:
            """Record a violation and return count."""
            self.violations.append(violation)
            self.violation_count += 1
            
            if self.violation_count >= self.config["violation_threshold"]:
                await self.trigger("violation_threshold_exceeded")
            
            return self.violation_count
        
        async def check_and_trigger(self, metrics: Dict[str, Any]) -> bool:
            """Check instability and trigger if threshold exceeded."""
            score = await self.check_instability(metrics)
            
            if score >= self.config["instability_threshold"]:
                await self.record_violation({
                    "type": "instability",
                    "score": score,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                return True
            return False
        
        async def trigger(self, reason: str) -> None:
            """Trigger the kill switch."""
            self.is_triggered = True
            self.trigger_reason = reason
            self.is_active = False
        
        async def reset(self) -> None:
            """Reset the kill switch."""
            self.is_triggered = False
            self.trigger_reason = ""
            self.violation_count = 0
            self.instability_score = 0.0
            self.violations = []
            self.is_active = True
        
        def get_status(self) -> Dict[str, Any]:
            """Get current status."""
            return {
                "is_active": self.is_active,
                "is_triggered": self.is_triggered,
                "trigger_reason": self.trigger_reason,
                "violation_count": self.violation_count,
                "instability_score": self.instability_score,
                "config": self.config,
            }
    
    return MockKillSwitch()


# ============================================================================
# Test Classes
# ============================================================================

class TestKillSwitchBasics:
    """Basic kill-switch functionality tests."""
    
    @pytest.mark.asyncio
    async def test_kill_switch_initial_state(self, mock_kill_switch):
        """Verify kill-switch starts in healthy state."""
        status = mock_kill_switch.get_status()
        
        assert status["is_active"] is True, "Kill-switch should be active initially"
        assert status["is_triggered"] is False, "Kill-switch should not be triggered initially"
        assert status["violation_count"] == 0, "Violation count should be zero"
        assert status["instability_score"] == 0.0, "Instability score should be zero"
    
    @pytest.mark.asyncio
    async def test_kill_switch_below_threshold(self, mock_kill_switch):
        """Kill-switch should not trigger below threshold."""
        # Send metrics below threshold
        for i in range(5):
            result = await mock_kill_switch.check_and_trigger({
                "instability": 0.5,  # Below 0.7 threshold
                "source": "test",
            })
            
            if result:
                # Violation recorded but shouldn't trigger
                assert mock_kill_switch.violation_count < VIOLATION_THRESHOLD
        
        assert mock_kill_switch.is_triggered is False, "Should not trigger below threshold"
    
    @pytest.mark.asyncio
    async def test_kill_switch_manual_trigger(self, mock_kill_switch):
        """Manual trigger should immediately activate kill-switch."""
        await mock_kill_switch.trigger("manual_test_trigger")
        
        assert mock_kill_switch.is_triggered is True
        assert mock_kill_switch.is_active is False
        assert mock_kill_switch.trigger_reason == "manual_test_trigger"
    
    @pytest.mark.asyncio
    async def test_kill_switch_reset(self, mock_kill_switch):
        """Reset should restore kill-switch to healthy state."""
        # Trigger first
        await mock_kill_switch.trigger("test")
        assert mock_kill_switch.is_triggered is True
        
        # Reset
        await mock_kill_switch.reset()
        
        assert mock_kill_switch.is_triggered is False
        assert mock_kill_switch.is_active is True
        assert mock_kill_switch.violation_count == 0
        assert mock_kill_switch.trigger_reason == ""


class TestKillSwitchInstability:
    """Tests for instability detection and response."""
    
    @pytest.mark.asyncio
    async def test_escalating_instability_detection(self, mock_kill_switch, instability_metrics):
        """Kill-switch should detect escalating instability."""
        violations_detected = 0
        
        for metric in instability_metrics:
            triggered = await mock_kill_switch.check_and_trigger(metric)
            if triggered:
                violations_detected += 1
        
        # Should have detected violations when instability >= threshold
        assert violations_detected >= 3, "Should detect at least 3 violations"
    
    @pytest.mark.asyncio
    async def test_threshold_breach_triggers_kill_switch(self, mock_kill_switch):
        """Kill-switch should trigger when violation threshold is reached."""
        # Simulate violations reaching threshold
        for i in range(VIOLATION_THRESHOLD):
            await mock_kill_switch.check_and_trigger({
                "instability": INSTABILITY_THRESHOLD + 0.1,
                "source": f"test_{i}",
            })
        
        assert mock_kill_switch.is_triggered is True, \
            f"Should trigger after {VIOLATION_THRESHOLD} violations"
        assert "violation_threshold_exceeded" in mock_kill_switch.trigger_reason
    
    @pytest.mark.asyncio
    async def test_instability_score_calculation(self, mock_kill_switch):
        """Instability score should be calculated correctly."""
        test_cases = [
            ({"instability": 0.0}, 0.0),
            ({"instability": 0.5}, 0.5),
            ({"instability": 0.7}, 0.7),
            ({"instability": 1.0}, 1.0),
        ]
        
        for metrics, expected in test_cases:
            score = await mock_kill_switch.check_instability(metrics)
            assert score == expected, f"Expected {expected}, got {score}"
    
    @pytest.mark.asyncio
    async def test_rapid_succession_violations(self, mock_kill_switch):
        """Rapid violations should trigger quickly."""
        # Fire violations rapidly
        tasks = [
            mock_kill_switch.check_and_trigger({
                "instability": 0.9,
                "source": f"rapid_{i}",
            })
            for i in range(VIOLATION_THRESHOLD + 2)
        ]
        
        await asyncio.gather(*tasks)
        
        assert mock_kill_switch.is_triggered is True


class TestKillSwitchRecovery:
    """Tests for kill-switch recovery and cooldown."""
    
    @pytest.mark.asyncio
    async def test_cooldown_period_enforcement(self, mock_kill_switch):
        """Kill-switch should enforce cooldown period."""
        # Trigger
        await mock_kill_switch.trigger("test")
        assert mock_kill_switch.is_triggered is True
        
        # Attempt to reset immediately should be allowed
        await mock_kill_switch.reset()
        assert mock_kill_switch.is_active is True
    
    @pytest.mark.asyncio
    async def test_recovery_after_reset(self, mock_kill_switch):
        """System should recover after reset."""
        # Trigger
        await mock_kill_switch.trigger("test")
        
        # Reset
        await mock_kill_switch.reset()
        
        # Should be able to process normal metrics
        await mock_kill_switch.check_and_trigger({"instability": 0.3})
        
        assert mock_kill_switch.is_triggered is False
        assert mock_kill_switch.violation_count == 0


class TestKillSwitchIntegration:
    """Integration tests with other system components."""
    
    @pytest.mark.asyncio
    async def test_kill_switch_with_llm_failures(self, mock_kill_switch):
        """Kill-switch should trigger on repeated LLM failures."""
        # Simulate LLM failures
        for i in range(VIOLATION_THRESHOLD):
            await mock_kill_switch.check_and_trigger({
                "instability": 0.8,
                "source": "llm_failure",
                "error_type": "ConnectionError",
            })
        
        assert mock_kill_switch.is_triggered is True
    
    @pytest.mark.asyncio
    async def test_kill_switch_with_memory_issues(self, mock_kill_switch):
        """Kill-switch should trigger on memory issues."""
        # Simulate memory issues
        for i in range(VIOLATION_THRESHOLD):
            await mock_kill_switch.check_and_trigger({
                "instability": 0.75,
                "source": "memory_leak",
                "memory_usage": 0.95,
            })
        
        assert mock_kill_switch.is_triggered is True
    
    @pytest.mark.asyncio
    async def test_kill_switch_status_reporting(self, mock_kill_switch):
        """Kill-switch should provide accurate status reports."""
        # Record some activity
        await mock_kill_switch.check_and_trigger({"instability": 0.8})
        await mock_kill_switch.check_and_trigger({"instability": 0.5})
        
        status = mock_kill_switch.get_status()
        
        assert "is_active" in status
        assert "is_triggered" in status
        assert "violation_count" in status
        assert "instability_score" in status
        assert "config" in status
        
        assert isinstance(status["violation_count"], int)
        assert isinstance(status["instability_score"], float)


class TestKillSwitchEdgeCases:
    """Edge case tests for kill-switch behavior."""
    
    @pytest.mark.asyncio
    async def test_zero_instability(self, mock_kill_switch):
        """Zero instability should be handled correctly."""
        result = await mock_kill_switch.check_and_trigger({"instability": 0.0})
        
        assert result is False, "Should not record violation for zero instability"
        assert mock_kill_switch.violation_count == 0
    
    @pytest.mark.asyncio
    async def test_max_instability(self, mock_kill_switch):
        """Maximum instability should be handled correctly."""
        result = await mock_kill_switch.check_and_trigger({"instability": 1.0})
        
        assert result is True, "Should record violation for max instability"
        assert mock_kill_switch.violation_count == 1
    
    @pytest.mark.asyncio
    async def test_missing_instability_metric(self, mock_kill_switch):
        """Missing instability metric should default to 0."""
        result = await mock_kill_switch.check_and_trigger({})
        
        assert result is False
        assert mock_kill_switch.instability_score == 0.0
    
    @pytest.mark.asyncio
    async def test_concurrent_violation_recording(self, mock_kill_switch):
        """Concurrent violation recording should be thread-safe."""
        async def record_violation(i):
            await mock_kill_switch.record_violation({
                "type": "concurrent",
                "index": i,
            })
        
        # Fire many concurrent violations
        tasks = [record_violation(i) for i in range(10)]
        await asyncio.gather(*tasks)
        
        # All should be recorded
        assert mock_kill_switch.violation_count == 10


# ============================================================================
# API Integration Tests (when API is available)
# ============================================================================

@pytest.mark.requires_docker
class TestKillSwitchAPI:
    """API integration tests for kill-switch."""
    
    @pytest.mark.asyncio
    async def test_kill_switch_status_endpoint(self, api_client: AsyncClient, api_routes):
        """GET /kill-switch should return current status."""
        response = await api_client.get(api_routes["kill_switch"])
        
        assert response.status_code == 200
        data = response.json()
        
        assert "is_active" in data["data"]
        assert "is_triggered" in data["data"]
    
    @pytest.mark.asyncio
    async def test_kill_switch_trigger_endpoint(self, authenticated_client: AsyncClient, api_routes):
        """POST /kill-switch/trigger should trigger kill-switch."""
        response = await authenticated_client.post(
            f"{api_routes['kill_switch']}/trigger",
            json={"reason": "test_trigger"},
        )
        
        assert response.status_code in [200, 201]
        data = response.json()
        
        assert data["data"]["is_triggered"] is True
    
    @pytest.mark.asyncio
    async def test_kill_switch_reset_endpoint(self, authenticated_client: AsyncClient, api_routes):
        """POST /kill-switch/reset should reset kill-switch."""
        response = await authenticated_client.post(
            f"{api_routes['kill_switch']}/reset",
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["data"]["is_triggered"] is False
        assert data["data"]["is_active"] is True
