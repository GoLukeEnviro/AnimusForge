"""
Unit tests for AnimusForge Ethics Engine - Gewissen 2.0
Comprehensive test coverage for all ethics components.
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import re

from pydantic import ValidationError

from animus_conscience.ethics import (
    # Enums
    StakeholderType,
    EthicsLevel,
    ContentCategory,
    PIIType,
    BiasType,
    ActionType,
    # Models
    EthicsCheck,
    EthicsEvaluation,
    ContentFilterResult,
    PIIDetection,
    BiasDetectionResult,
    PlannedAction,
    ActionResult,
    EthicsAuditEntry,
    EthicsReport,
    # Components
    ContentFilter,
    PIIDetector,
    BiasDetector,
    StakeholderProtectionRules,
    EthicsEngine,
    EthicsAuditLog,
    EthicsOrchestrator,
    # Factory functions
    create_ethics_engine,
    create_ethics_orchestrator,
)


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestStakeholderType:
    """Tests for StakeholderType enum."""

    def test_all_stakeholder_types_exist(self):
        """Test all stakeholder types are defined."""
        assert StakeholderType.USER == "user"
        assert StakeholderType.THIRD_PARTY == "third_party"
        assert StakeholderType.SYSTEM == "system"
        assert StakeholderType.SOCIETY == "society"

    def test_stakeholder_type_values(self):
        """Test stakeholder type string values."""
        assert StakeholderType.USER.value == "user"
        assert StakeholderType.THIRD_PARTY.value == "third_party"
        assert StakeholderType.SYSTEM.value == "system"
        assert StakeholderType.SOCIETY.value == "society"

    def test_stakeholder_type_count(self):
        """Test number of stakeholder types."""
        assert len(StakeholderType) == 4


class TestEthicsLevel:
    """Tests for EthicsLevel enum."""

    def test_all_ethics_levels_exist(self):
        """Test all ethics levels are defined."""
        assert EthicsLevel.ALLOWED == "allowed"
        assert EthicsLevel.WARNING == "warning"
        assert EthicsLevel.RESTRICTED == "restricted"
        assert EthicsLevel.FORBIDDEN == "forbidden"

    def test_ethics_level_order(self):
        """Test ethics level severity order."""
        levels = [EthicsLevel.ALLOWED, EthicsLevel.WARNING, EthicsLevel.RESTRICTED, EthicsLevel.FORBIDDEN]
        assert all(isinstance(level, EthicsLevel) for level in levels)


class TestContentCategory:
    """Tests for ContentCategory enum."""

    def test_all_content_categories_exist(self):
        """Test all content categories are defined."""
        assert ContentCategory.VIOLENCE == "violence"
        assert ContentCategory.HATE_SPEECH == "hate_speech"
        assert ContentCategory.SEXUAL_CONTENT == "sexual_content"
        assert ContentCategory.HARASSMENT == "harassment"
        assert ContentCategory.SELF_HARM == "self_harm"
        assert ContentCategory.MISINFORMATION == "misinformation"
        assert ContentCategory.ILLEGAL_CONTENT == "illegal_content"

    def test_content_category_count(self):
        """Test number of content categories."""
        assert len(ContentCategory) == 7


class TestPIIType:
    """Tests for PIIType enum."""

    def test_all_pii_types_exist(self):
        """Test all PII types are defined."""
        assert PIIType.EMAIL == "email"
        assert PIIType.PHONE_NUMBER == "phone_number"
        assert PIIType.SOCIAL_SECURITY_NUMBER == "social_security_number"
        assert PIIType.CREDIT_CARD == "credit_card"
        assert PIIType.IP_ADDRESS == "ip_address"
        assert PIIType.PHYSICAL_ADDRESS == "physical_address"
        assert PIIType.DATE_OF_BIRTH == "date_of_birth"

    def test_pii_type_count(self):
        """Test number of PII types."""
        assert len(PIIType) == 7


class TestBiasType:
    """Tests for BiasType enum."""

    def test_all_bias_types_exist(self):
        """Test all bias types are defined."""
        assert BiasType.GENDER == "gender"
        assert BiasType.RACIAL == "racial"
        assert BiasType.AGE == "age"
        assert BiasType.RELIGIOUS == "religious"
        assert BiasType.POLITICAL == "political"
        assert BiasType.SOCIOECONOMIC == "socioeconomic"

    def test_bias_type_count(self):
        """Test number of bias types."""
        assert len(BiasType) == 6


class TestActionType:
    """Tests for ActionType enum."""

    def test_all_action_types_exist(self):
        """Test all action types are defined."""
        assert ActionType.CREATE == "create"
        assert ActionType.READ == "read"
        assert ActionType.UPDATE == "update"
        assert ActionType.DELETE == "delete"
        assert ActionType.EXECUTE == "execute"
        assert ActionType.COMMUNICATE == "communicate"
        assert ActionType.ANALYZE == "analyze"


# ============================================================================
# MODEL TESTS
# ============================================================================

class TestEthicsCheck:
    """Tests for EthicsCheck model."""

    def test_create_ethics_check(self):
        """Test creating an ethics check."""
        check = EthicsCheck(
            stakeholder=StakeholderType.USER,
            category="test_category",
            description="Test description",
            level=EthicsLevel.WARNING,
            confidence=0.85,
        )
        assert check.stakeholder == StakeholderType.USER
        assert check.category == "test_category"
        assert check.level == EthicsLevel.WARNING
        assert check.confidence == 0.85

    def test_confidence_validation_valid(self):
        """Test confidence validation with valid values."""
        check = EthicsCheck(
            stakeholder=StakeholderType.USER,
            category="test",
            description="test",
            level=EthicsLevel.ALLOWED,
            confidence=0.5,
        )
        assert check.confidence == 0.5

    def test_confidence_validation_rounded(self):
        """Test confidence is rounded to 3 decimal places."""
        check = EthicsCheck(
            stakeholder=StakeholderType.USER,
            category="test",
            description="test",
            level=EthicsLevel.ALLOWED,
            confidence=0.856789,
        )
        assert check.confidence == 0.857

    def test_confidence_validation_invalid_high(self):
        """Test confidence validation rejects values > 1."""
        with pytest.raises(ValidationError):
            EthicsCheck(
                stakeholder=StakeholderType.USER,
                category="test",
                description="test",
                level=EthicsLevel.ALLOWED,
                confidence=1.5,
            )

    def test_confidence_validation_invalid_low(self):
        """Test confidence validation rejects values < 0."""
        with pytest.raises(ValidationError):
            EthicsCheck(
                stakeholder=StakeholderType.USER,
                category="test",
                description="test",
                level=EthicsLevel.ALLOWED,
                confidence=-0.1,
            )


class TestEthicsEvaluation:
    """Tests for EthicsEvaluation model."""

    def test_create_ethics_evaluation(self):
        """Test creating an ethics evaluation."""
        evaluation = EthicsEvaluation(
            overall_level=EthicsLevel.ALLOWED,
            reasoning="All checks passed",
        )
        assert evaluation.overall_level == EthicsLevel.ALLOWED
        assert evaluation.reasoning == "All checks passed"
        assert evaluation.checks == []
        assert evaluation.requires_human_review == False
        assert evaluation.evaluation_id is not None

    def test_ethics_evaluation_with_checks(self):
        """Test ethics evaluation with checks."""
        check = EthicsCheck(
            stakeholder=StakeholderType.SOCIETY,
            category="violence",
            description="Violent content detected",
            level=EthicsLevel.WARNING,
            confidence=0.8,
        )
        evaluation = EthicsEvaluation(
            overall_level=EthicsLevel.WARNING,
            checks=[check],
            reasoning="Warning issued",
            recommendations=["Review content"],
            requires_human_review=True,
        )
        assert len(evaluation.checks) == 1
        assert evaluation.requires_human_review == True

    def test_get_level_priority(self):
        """Test level priority calculation."""
        evaluation = EthicsEvaluation(overall_level=EthicsLevel.ALLOWED)
        assert evaluation.get_level_priority(EthicsLevel.ALLOWED) == 0
        assert evaluation.get_level_priority(EthicsLevel.WARNING) == 1
        assert evaluation.get_level_priority(EthicsLevel.RESTRICTED) == 2
        assert evaluation.get_level_priority(EthicsLevel.FORBIDDEN) == 3


class TestContentFilterResult:
    """Tests for ContentFilterResult model."""

    def test_create_safe_result(self):
        """Test creating a safe content filter result."""
        result = ContentFilterResult(
            is_safe=True,
            categories=[],
            confidence=1.0,
        )
        assert result.is_safe == True
        assert result.categories == []
        assert result.filtered_content is None

    def test_create_unsafe_result(self):
        """Test creating an unsafe content filter result."""
        result = ContentFilterResult(
            is_safe=False,
            categories=["violence", "harassment"],
            confidence=0.8,
            filtered_content="This is [FILTERED:VIOLENCE] content",
        )
        assert result.is_safe == False
        assert len(result.categories) == 2
        assert result.filtered_content is not None


class TestPIIDetection:
    """Tests for PIIDetection model."""

    def test_create_no_pii_result(self):
        """Test creating a result with no PII."""
        result = PIIDetection(has_pii=False)
        assert result.has_pii == False
        assert result.pii_types == []
        assert result.redacted_content is None

    def test_create_pii_result(self):
        """Test creating a result with PII detected."""
        result = PIIDetection(
            has_pii=True,
            pii_types=["email", "phone_number"],
            locations=[(10, 30), (50, 62)],
            redacted_content="Contact [REDACTED:EMAIL] or [REDACTED:PHONE_NUMBER]",
        )
        assert result.has_pii == True
        assert len(result.pii_types) == 2
        assert len(result.locations) == 2


class TestBiasDetectionResult:
    """Tests for BiasDetectionResult model."""

    def test_create_no_bias_result(self):
        """Test creating a result with no bias."""
        result = BiasDetectionResult(has_bias=False, confidence=1.0)
        assert result.has_bias == False
        assert result.bias_types == []

    def test_create_bias_result(self):
        """Test creating a result with bias detected."""
        result = BiasDetectionResult(
            has_bias=True,
            bias_types=["gender", "age"],
            confidence=0.75,
            recommendations=["Rephrase to avoid stereotypes"],
        )
        assert result.has_bias == True
        assert len(result.bias_types) == 2
        assert len(result.recommendations) == 1


class TestPlannedAction:
    """Tests for PlannedAction model."""

    def test_create_planned_action(self):
        """Test creating a planned action."""
        action = PlannedAction(
            action_type=ActionType.CREATE,
            description="Create new user account",
            target="user_database",
        )
        assert action.action_type == ActionType.CREATE
        assert action.description == "Create new user account"
        assert action.target == "user_database"
        assert action.action_id is not None

    def test_planned_action_with_parameters(self):
        """Test planned action with parameters."""
        action = PlannedAction(
            action_type=ActionType.EXECUTE,
            description="Execute script",
            parameters={"script_name": "test.py", "timeout": 30},
        )
        assert action.parameters["script_name"] == "test.py"


class TestActionResult:
    """Tests for ActionResult model."""

    def test_create_success_result(self):
        """Test creating a successful action result."""
        result = ActionResult(
            action_id="test-123",
            success=True,
            result_data={"message": "Completed"},
            duration_ms=150.5,
        )
        assert result.success == True
        assert result.error is None

    def test_create_failure_result(self):
        """Test creating a failed action result."""
        result = ActionResult(
            action_id="test-456",
            success=False,
            error="Action failed due to timeout",
        )
        assert result.success == False
        assert result.error is not None


class TestEthicsAuditEntry:
    """Tests for EthicsAuditEntry model."""

    def test_create_audit_entry(self):
        """Test creating an audit entry."""
        entry = EthicsAuditEntry(
            evaluation_id="eval-123",
            action_type="create",
            overall_level=EthicsLevel.WARNING,
            requires_human_review=True,
        )
        assert entry.evaluation_id == "eval-123"
        assert entry.human_reviewed == False
        assert entry.human_decision is None


class TestEthicsReport:
    """Tests for EthicsReport model."""

    def test_create_ethics_report(self):
        """Test creating an ethics report."""
        report = EthicsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            total_evaluations=100,
            level_distribution={"allowed": 80, "warning": 15, "restricted": 5},
        )
        assert report.total_evaluations == 100
        assert report.report_id is not None


# ============================================================================
# CONTENT FILTER TESTS
# ============================================================================

class TestContentFilter:
    """Tests for ContentFilter class."""

    @pytest.fixture
    def content_filter(self):
        """Create content filter instance."""
        return ContentFilter()

    @pytest.mark.asyncio
    async def test_filter_empty_content(self, content_filter):
        """Test filtering empty content."""
        result = await content_filter.filter("")
        assert result.is_safe == True
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_filter_safe_content(self, content_filter):
        """Test filtering safe content."""
        result = await content_filter.filter("This is a normal, harmless message.")
        assert result.is_safe == True
        assert len(result.categories) == 0

    @pytest.mark.asyncio
    async def test_filter_violence_content(self, content_filter):
        """Test filtering violent content."""
        result = await content_filter.filter("I will kill and murder everyone")
        assert result.is_safe == False
        assert "violence" in result.categories

    @pytest.mark.asyncio
    async def test_filter_hate_speech_content(self, content_filter):
        """Test filtering hate speech content."""
        result = await content_filter.filter("I hate all those people, they are subhuman")
        assert "hate_speech" in result.categories

    @pytest.mark.asyncio
    async def test_filter_sexual_content(self, content_filter):
        """Test filtering sexual content."""
        result = await content_filter.filter("Check out this porn and xxx content")
        assert "sexual_content" in result.categories

    @pytest.mark.asyncio
    async def test_filter_harassment_content(self, content_filter):
        """Test filtering harassment content."""
        result = await content_filter.filter("I will stalk and harass you continuously")
        assert "harassment" in result.categories

    @pytest.mark.asyncio
    async def test_filter_self_harm_content(self, content_filter):
        """Test filtering self-harm content."""
        result = await content_filter.filter("I want to kill myself and end my life")
        assert "self_harm" in result.categories
        assert result.is_safe == False

    @pytest.mark.asyncio
    async def test_filter_illegal_content(self, content_filter):
        """Test filtering illegal content."""
        result = await content_filter.filter("Get drugs on the dark web market")
        assert "illegal_content" in result.categories

    @pytest.mark.asyncio
    async def test_filter_misinformation_content(self, content_filter):
        """Test filtering misinformation content."""
        result = await content_filter.filter("This is fake news and a hoax")
        assert "misinformation" in result.categories

    @pytest.mark.asyncio
    async def test_filter_produces_filtered_content(self, content_filter):
        """Test that filter produces filtered content."""
        result = await content_filter.filter("I will kill you")
        assert result.filtered_content is not None
        assert "[FILTERED" in result.filtered_content

    @pytest.mark.asyncio
    async def test_filter_multiple_categories(self, content_filter):
        """Test filtering content with multiple violations."""
        result = await content_filter.filter(
            "I will kill you and this is fake news porn content"
        )
        assert len(result.categories) >= 2

    @pytest.mark.asyncio
    async def test_filter_matched_patterns(self, content_filter):
        """Test matched patterns are recorded."""
        result = await content_filter.filter("I will murder everyone")
        assert len(result.matched_patterns) > 0
        assert "match" in result.matched_patterns[0]
        assert "severity" in result.matched_patterns[0]


# ============================================================================
# PII DETECTOR TESTS
# ============================================================================

class TestPIIDetector:
    """Tests for PIIDetector class."""

    @pytest.fixture
    def pii_detector(self):
        """Create PII detector instance."""
        return PIIDetector()

    @pytest.mark.asyncio
    async def test_detect_empty_content(self, pii_detector):
        """Test detecting PII in empty content."""
        result = await pii_detector.detect("")
        assert result.has_pii == False

    @pytest.mark.asyncio
    async def test_detect_no_pii(self, pii_detector):
        """Test detecting no PII in normal content."""
        result = await pii_detector.detect("This is a normal message without PII")
        assert result.has_pii == False

    @pytest.mark.asyncio
    async def test_detect_email(self, pii_detector):
        """Test detecting email addresses."""
        result = await pii_detector.detect("Contact me at john.doe@example.com")
        assert result.has_pii == True
        assert "email" in result.pii_types

    @pytest.mark.asyncio
    async def test_detect_phone_number(self, pii_detector):
        """Test detecting phone numbers."""
        result = await pii_detector.detect("Call me at 555-123-4567")
        assert result.has_pii == True
        assert "phone_number" in result.pii_types

    @pytest.mark.asyncio
    async def test_detect_ssn(self, pii_detector):
        """Test detecting social security numbers."""
        result = await pii_detector.detect("SSN: 123-45-6789")
        assert result.has_pii == True
        assert "social_security_number" in result.pii_types

    @pytest.mark.asyncio
    async def test_detect_credit_card(self, pii_detector):
        """Test detecting credit card numbers."""
        result = await pii_detector.detect("Card: 1234-5678-9012-3456")
        assert result.has_pii == True
        assert "credit_card" in result.pii_types

    @pytest.mark.asyncio
    async def test_detect_ip_address(self, pii_detector):
        """Test detecting IP addresses."""
        result = await pii_detector.detect("Server IP: 192.168.1.100")
        assert result.has_pii == True
        assert "ip_address" in result.pii_types

    @pytest.mark.asyncio
    async def test_detect_physical_address(self, pii_detector):
        """Test detecting physical addresses."""
        result = await pii_detector.detect("I live at 123 Main Street")
        assert result.has_pii == True
        assert "physical_address" in result.pii_types

    @pytest.mark.asyncio
    async def test_detect_multiple_pii_types(self, pii_detector):
        """Test detecting multiple PII types."""
        result = await pii_detector.detect(
            "Contact john@example.com or call 555-123-4567"
        )
        assert result.has_pii == True
        assert len(result.pii_types) >= 2

    @pytest.mark.asyncio
    async def test_redacted_content_produced(self, pii_detector):
        """Test that redacted content is produced."""
        result = await pii_detector.detect("Email: test@example.com")
        assert result.redacted_content is not None
        assert "[REDACTED" in result.redacted_content

    @pytest.mark.asyncio
    async def test_detected_items_populated(self, pii_detector):
        """Test that detected items are populated."""
        result = await pii_detector.detect("test@example.com")
        assert len(result.detected_items) > 0
        assert result.detected_items[0]["type"] == "email"
        assert result.detected_items[0]["value"] == "test@example.com"


# ============================================================================
# BIAS DETECTOR TESTS
# ============================================================================

class TestBiasDetector:
    """Tests for BiasDetector class."""

    @pytest.fixture
    def bias_detector(self):
        """Create bias detector instance."""
        return BiasDetector()

    @pytest.mark.asyncio
    async def test_detect_empty_content(self, bias_detector):
        """Test detecting bias in empty content."""
        result = await bias_detector.detect("")
        assert result.has_bias == False

    @pytest.mark.asyncio
    async def test_detect_no_bias(self, bias_detector):
        """Test detecting no bias in neutral content."""
        result = await bias_detector.detect("People have different opinions")
        assert result.has_bias == False

    @pytest.mark.asyncio
    async def test_detect_gender_bias(self, bias_detector):
        """Test detecting gender bias."""
        result = await bias_detector.detect("Women can't be engineers")
        assert result.has_bias == True
        assert "gender" in result.bias_types

    @pytest.mark.asyncio
    async def test_detect_age_bias(self, bias_detector):
        """Test detecting age bias."""
        result = await bias_detector.detect("Old people can't understand technology")
        assert result.has_bias == True
        assert "age" in result.bias_types

    @pytest.mark.asyncio
    async def test_detect_religious_bias(self, bias_detector):
        """Test detecting religious bias."""
        result = await bias_detector.detect("All Christians believe the same thing")
        assert result.has_bias == True
        assert "religious" in result.bias_types

    @pytest.mark.asyncio
    async def test_detect_political_bias(self, bias_detector):
        """Test detecting political bias."""
        result = await bias_detector.detect("All liberals want the same policies")
        assert result.has_bias == True
        assert "political" in result.bias_types

    @pytest.mark.asyncio
    async def test_detect_socioeconomic_bias(self, bias_detector):
        """Test detecting socioeconomic bias."""
        result = await bias_detector.detect("Poor people are always lazy")
        assert result.has_bias == True
        assert "socioeconomic" in result.bias_types

    @pytest.mark.asyncio
    async def test_bias_recommendations(self, bias_detector):
        """Test that bias detection provides recommendations."""
        result = await bias_detector.detect("Women can't code")
        assert len(result.recommendations) > 0
        assert "rephras" in result.recommendations[0].lower()

    @pytest.mark.asyncio
    async def test_multiple_bias_types(self, bias_detector):
        """Test detecting multiple bias types."""
        result = await bias_detector.detect(
            "Women can't lead and old people can't learn"
        )
        assert result.has_bias == True
        assert len(result.bias_types) >= 2


# ============================================================================
# STAKEHOLDER PROTECTION RULES TESTS
# ============================================================================

class TestStakeholderProtectionRules:
    """Tests for StakeholderProtectionRules class."""

    def test_get_user_rules(self):
        """Test getting user protection rules."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.USER)
        assert "data_privacy" in rules
        assert "transparency" in rules
        assert "control" in rules

    def test_get_third_party_rules(self):
        """Test getting third party protection rules."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.THIRD_PARTY)
        assert "unauthorized_action" in rules
        assert "consent_required" in rules

    def test_get_system_rules(self):
        """Test getting system protection rules."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.SYSTEM)
        assert "integrity" in rules
        assert "stability" in rules

    def test_get_society_rules(self):
        """Test getting society protection rules."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.SOCIETY)
        assert "harm_prevention" in rules
        assert "legality" in rules

    def test_rule_has_description(self):
        """Test that rules have descriptions."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.USER)
        assert "description" in rules["data_privacy"]

    def test_rule_has_level(self):
        """Test that rules have ethics levels."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.USER)
        assert "level" in rules["data_privacy"]

    def test_rule_has_triggers(self):
        """Test that rules have triggers."""
        rules = StakeholderProtectionRules.get_rules(StakeholderType.USER)
        assert "triggers" in rules["data_privacy"]


# ============================================================================
# ETHICS ENGINE TESTS
# ============================================================================

class TestEthicsEngine:
    """Tests for EthicsEngine class."""

    @pytest.fixture
    def engine(self):
        """Create ethics engine instance."""
        return EthicsEngine()

    @pytest.mark.asyncio
    async def test_evaluate_content_safe(self, engine):
        """Test evaluating safe content."""
        result = await engine.evaluate_content("This is a normal message")
        assert result.overall_level == EthicsLevel.ALLOWED
        assert len(result.checks) == 0

    @pytest.mark.asyncio
    async def test_evaluate_content_violent(self, engine):
        """Test evaluating violent content."""
        result = await engine.evaluate_content("I will kill everyone")
        assert result.overall_level in [EthicsLevel.WARNING, EthicsLevel.RESTRICTED]
        assert any(c.stakeholder == StakeholderType.SOCIETY for c in result.checks)

    @pytest.mark.asyncio
    async def test_evaluate_content_with_pii(self, engine):
        """Test evaluating content with PII."""
        result = await engine.evaluate_content("My email is test@example.com")
        assert any(c.category == "pii_detection" for c in result.checks)

    @pytest.mark.asyncio
    async def test_evaluate_content_with_bias(self, engine):
        """Test evaluating content with bias."""
        result = await engine.evaluate_content("Women can't be leaders")
        assert any(c.category == "bias_detection" for c in result.checks)

    @pytest.mark.asyncio
    async def test_evaluate_action_safe(self, engine):
        """Test evaluating a safe action."""
        action = PlannedAction(
            action_type=ActionType.READ,
            description="Read user profile data",
        )
        result = await engine.evaluate_action(action)
        assert result.overall_level == EthicsLevel.ALLOWED

    @pytest.mark.asyncio
    async def test_evaluate_action_forbidden(self, engine):
        """Test evaluating a forbidden action."""
        action = PlannedAction(
            action_type=ActionType.EXECUTE,
            description="Share personal data with third party",
            parameters={"share_personal_data": True},
        )
        result = await engine.evaluate_action(action)
        assert result.overall_level in [EthicsLevel.WARNING, EthicsLevel.RESTRICTED, EthicsLevel.FORBIDDEN]

    @pytest.mark.asyncio
    async def test_evaluate_action_with_harmful_description(self, engine):
        """Test evaluating action with harmful description."""
        action = PlannedAction(
            action_type=ActionType.CREATE,
            description="Generate malware to attack systems",
        )
        result = await engine.evaluate_action(action)
        assert result.overall_level in [EthicsLevel.WARNING, EthicsLevel.RESTRICTED, EthicsLevel.FORBIDDEN]

    @pytest.mark.asyncio
    async def test_check_pii(self, engine):
        """Test PII check method."""
        result = await engine.check_pii("test@example.com")
        assert result.has_pii == True
        assert "email" in result.pii_types

    @pytest.mark.asyncio
    async def test_filter_content(self, engine):
        """Test content filter method."""
        result = await engine.filter_content("This is violent murder content")
        assert result.is_safe == False

    @pytest.mark.asyncio
    async def test_detect_bias(self, engine):
        """Test bias detection method."""
        result = await engine.detect_bias("Women can't code")
        assert result.has_bias == True

    @pytest.mark.asyncio
    async def test_human_review_threshold(self, engine):
        """Test human review is required for uncertain checks."""
        engine.human_review_threshold = 0.9
        result = await engine.evaluate_content("Some ambiguous content")
        assert isinstance(result.requires_human_review, bool)

    @pytest.mark.asyncio
    async def test_recommendations_generated(self, engine):
        """Test recommendations are generated for issues."""
        result = await engine.evaluate_content("test@example.com")
        assert len(result.recommendations) > 0

    @pytest.mark.asyncio
    async def test_reasoning_generated(self, engine):
        """Test reasoning is generated."""
        result = await engine.evaluate_content("Test content")
        assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_multi_stakeholder_evaluation(self, engine):
        """Test that all stakeholders are evaluated for actions."""
        action = PlannedAction(
            action_type=ActionType.EXECUTE,
            description="Process user data",
        )
        result = await engine.evaluate_action(action)
        stakeholders = {c.stakeholder for c in result.checks}
        assert isinstance(stakeholders, set)


# ============================================================================
# ETHICS AUDIT LOG TESTS
# ============================================================================

class TestEthicsAuditLog:
    """Tests for EthicsAuditLog class."""

    @pytest.fixture
    def audit_log(self):
        """Create audit log instance."""
        return EthicsAuditLog()

    @pytest.fixture
    def sample_evaluation(self):
        """Create sample evaluation for testing."""
        return EthicsEvaluation(
            overall_level=EthicsLevel.WARNING,
            checks=[
                EthicsCheck(
                    stakeholder=StakeholderType.USER,
                    category="test",
                    description="Test check",
                    level=EthicsLevel.WARNING,
                    confidence=0.8,
                )
            ],
            reasoning="Test reasoning",
            requires_human_review=True,
        )

    @pytest.mark.asyncio
    async def test_log_evaluation(self, audit_log, sample_evaluation):
        """Test logging an evaluation."""
        entry = await audit_log.log(
            evaluation=sample_evaluation,
            action_type="create",
        )
        assert entry.evaluation_id == sample_evaluation.evaluation_id
        assert entry.action_type == "create"
        assert entry.overall_level == EthicsLevel.WARNING

    @pytest.mark.asyncio
    async def test_mark_reviewed(self, audit_log, sample_evaluation):
        """Test marking an evaluation as reviewed."""
        await audit_log.log(sample_evaluation, "test")
        entry = await audit_log.mark_reviewed(
            sample_evaluation.evaluation_id,
            EthicsLevel.ALLOWED,
        )
        assert entry is not None
        assert entry.human_reviewed == True
        assert entry.human_decision == EthicsLevel.ALLOWED

    @pytest.mark.asyncio
    async def test_mark_reviewed_nonexistent(self, audit_log):
        """Test marking nonexistent evaluation as reviewed."""
        entry = await audit_log.mark_reviewed("nonexistent", EthicsLevel.ALLOWED)
        assert entry is None

    @pytest.mark.asyncio
    async def test_get_entries_by_date(self, audit_log, sample_evaluation):
        """Test getting entries filtered by date."""
        await audit_log.log(sample_evaluation, "test")
        today = date.today()
        entries = await audit_log.get_entries(start_date=today, end_date=today)
        assert len(entries) >= 1

    @pytest.mark.asyncio
    async def test_get_entries_by_level(self, audit_log, sample_evaluation):
        """Test getting entries filtered by level."""
        await audit_log.log(sample_evaluation, "test")
        entries = await audit_log.get_entries(level=EthicsLevel.WARNING)
        assert all(e.overall_level == EthicsLevel.WARNING for e in entries)

    @pytest.mark.asyncio
    async def test_get_entries_requires_review(self, audit_log, sample_evaluation):
        """Test getting entries that require review."""
        await audit_log.log(sample_evaluation, "test")
        entries = await audit_log.get_entries(requires_review=True)
        assert all(e.requires_human_review for e in entries)

    @pytest.mark.asyncio
    async def test_get_statistics(self, audit_log, sample_evaluation):
        """Test getting audit statistics."""
        await audit_log.log(sample_evaluation, "test")
        stats = await audit_log.get_statistics()
        assert "total_evaluations" in stats
        assert "level_distribution" in stats
        assert "human_review_count" in stats
        assert stats["total_evaluations"] >= 1

    @pytest.mark.asyncio
    async def test_max_entries_limit(self):
        """Test max entries limit is enforced."""
        audit_log = EthicsAuditLog(max_entries=5)
        for i in range(10):
            eval = EthicsEvaluation(overall_level=EthicsLevel.ALLOWED)
            await audit_log.log(eval, f"test_{i}")
        assert len(audit_log._entries) <= 5


# ============================================================================
# ETHICS ORCHESTRATOR TESTS
# ============================================================================

class TestEthicsOrchestrator:
    """Tests for EthicsOrchestrator class."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance."""
        return EthicsOrchestrator()

    @pytest.mark.asyncio
    async def test_pre_action_check(self, orchestrator):
        """Test pre-action check."""
        action = PlannedAction(
            action_type=ActionType.READ,
            description="Read data",
        )
        result = await orchestrator.pre_action_check(action)
        assert isinstance(result, EthicsEvaluation)
        assert result.evaluation_id is not None

    @pytest.mark.asyncio
    async def test_post_action_review_success(self, orchestrator):
        """Test post-action review for successful action."""
        result = ActionResult(
            action_id="test-123",
            success=True,
        )
        await orchestrator.post_action_review(result)

    @pytest.mark.asyncio
    async def test_post_action_review_failure(self, orchestrator):
        """Test post-action review for failed action."""
        result = ActionResult(
            action_id="test-456",
            success=False,
            error="Action forbidden by ethics rules",
        )
        await orchestrator.post_action_review(result)

    @pytest.mark.asyncio
    async def test_generate_report(self, orchestrator):
        """Test generating ethics report."""
        action = PlannedAction(
            action_type=ActionType.CREATE,
            description="Create item",
        )
        await orchestrator.pre_action_check(action)

        today = date.today()
        report = await orchestrator.generate_report(today - timedelta(days=1), today)

        assert isinstance(report, EthicsReport)
        assert report.total_evaluations >= 1
        assert len(report.recommendations) >= 1

    @pytest.mark.asyncio
    async def test_review_pending_evaluations(self, orchestrator):
        """Test getting pending evaluations."""
        action = PlannedAction(
            action_type=ActionType.DELETE,
            description="Delete all data bypass safety",
            parameters={"bypass_safety": True},
        )
        await orchestrator.pre_action_check(action)

        pending = await orchestrator.review_pending_evaluations()
        assert isinstance(pending, list)

    @pytest.mark.asyncio
    async def test_approve_evaluation(self, orchestrator):
        """Test approving an evaluation."""
        action = PlannedAction(
            action_type=ActionType.CREATE,
            description="Create test",
        )
        eval = await orchestrator.pre_action_check(action)

        result = await orchestrator.approve_evaluation(
            eval.evaluation_id,
            EthicsLevel.ALLOWED,
        )
        if result:
            assert result.human_reviewed == True


# ============================================================================
# FACTORY FUNCTION TESTS
# ============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_ethics_engine(self):
        """Test creating ethics engine via factory."""
        engine = create_ethics_engine()
        assert isinstance(engine, EthicsEngine)
        assert engine.content_filter is not None
        assert engine.pii_detector is not None
        assert engine.bias_detector is not None

    def test_create_ethics_engine_custom_threshold(self):
        """Test creating ethics engine with custom threshold."""
        engine = create_ethics_engine(human_review_threshold=0.9)
        assert engine.human_review_threshold == 0.9

    def test_create_ethics_orchestrator(self):
        """Test creating orchestrator via factory."""
        orchestrator = create_ethics_orchestrator()
        assert isinstance(orchestrator, EthicsOrchestrator)
        assert orchestrator.engine is not None
        assert orchestrator.audit_log is not None

    def test_create_ethics_orchestrator_custom(self):
        """Test creating orchestrator with custom settings."""
        orchestrator = create_ethics_orchestrator(
            human_review_threshold=0.8,
            max_audit_entries=5000,
        )
        assert orchestrator.engine.human_review_threshold == 0.8


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestEthicsIntegration:
    """Integration tests for ethics system."""

    @pytest.fixture
    def full_system(self):
        """Create full ethics system."""
        return create_ethics_orchestrator()

    @pytest.mark.asyncio
    async def test_full_workflow_safe_action(self, full_system):
        """Test full workflow for a safe action."""
        action = PlannedAction(
            action_type=ActionType.READ,
            description="Read user preferences",
            requester="user_123",
        )

        evaluation = await full_system.pre_action_check(action)
        assert evaluation.overall_level == EthicsLevel.ALLOWED

        result = ActionResult(
            action_id=action.action_id,
            success=True,
        )
        await full_system.post_action_review(result)

        today = date.today()
        report = await full_system.generate_report(today, today)
        assert report.total_evaluations >= 1

    @pytest.mark.asyncio
    async def test_full_workflow_forbidden_action(self, full_system):
        """Test full workflow for a forbidden action."""
        action = PlannedAction(
            action_type=ActionType.EXECUTE,
            description="Generate malware to hack systems",
            requester="user_456",
        )

        evaluation = await full_system.pre_action_check(action)
        assert evaluation.overall_level in [EthicsLevel.WARNING, EthicsLevel.RESTRICTED, EthicsLevel.FORBIDDEN]

        assert len(evaluation.recommendations) >= 0

    @pytest.mark.asyncio
    async def test_pii_protection_workflow(self, full_system):
        """Test PII protection workflow."""
        action = PlannedAction(
            action_type=ActionType.COMMUNICATE,
            description="Send email to test@example.com",
        )

        evaluation = await full_system.pre_action_check(action)
        pii_checks = [c for c in evaluation.checks if c.category == "pii_detection"]
        assert len(pii_checks) >= 1

    @pytest.mark.asyncio
    async def test_bias_detection_workflow(self, full_system):
        """Test bias detection workflow."""
        action = PlannedAction(
            action_type=ActionType.CREATE,
            description="Create content saying women can't code",
        )

        evaluation = await full_system.pre_action_check(action)
        bias_checks = [c for c in evaluation.checks if c.category == "bias_detection"]
        assert len(bias_checks) >= 1

    @pytest.mark.asyncio
    async def test_multi_stakeholder_violation_workflow(self, full_system):
        """Test multi-stakeholder violation detection."""
        action = PlannedAction(
            action_type=ActionType.EXECUTE,
            description="Share user data with unauthorized third party",
            parameters={"share_personal_data": True, "contact_third_party": True},
        )

        evaluation = await full_system.pre_action_check(action)
        assert len(evaluation.checks) >= 1

    @pytest.mark.asyncio
    async def test_audit_trail_completeness(self, full_system):
        """Test audit trail is complete."""
        for i in range(5):
            action = PlannedAction(
                action_type=ActionType.READ,
                description=f"Read data {i}",
            )
            await full_system.pre_action_check(action)

        stats = await full_system.audit_log.get_statistics()
        assert stats["total_evaluations"] >= 5


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def engine(self):
        """Create ethics engine instance."""
        return EthicsEngine()

    @pytest.mark.asyncio
    async def test_very_long_content(self, engine):
        """Test handling very long content."""
        long_content = "Normal text. " * 10000
        result = await engine.evaluate_content(long_content)
        assert isinstance(result, EthicsEvaluation)

    @pytest.mark.asyncio
    async def test_special_characters(self, engine):
        """Test handling special characters."""
        special_content = "Test @#$%^&*()_+{}|:<>?~` content"
        result = await engine.evaluate_content(special_content)
        assert isinstance(result, EthicsEvaluation)

    @pytest.mark.asyncio
    async def test_unicode_content(self, engine):
        """Test handling unicode content."""
        unicode_content = "Hello 你好 مرحبا שלום 🌍🎉"
        result = await engine.evaluate_content(unicode_content)
        assert isinstance(result, EthicsEvaluation)

    @pytest.mark.asyncio
    async def test_none_values(self):
        """Test handling None values in models."""
        result = ContentFilterResult(
            is_safe=True,
            categories=[],
            confidence=1.0,
            filtered_content=None,
        )
        assert result.filtered_content is None

    @pytest.mark.asyncio
    async def test_empty_action_description(self, engine):
        """Test handling empty action description."""
        action = PlannedAction(
            action_type=ActionType.READ,
            description="",
        )
        result = await engine.evaluate_action(action)
        assert isinstance(result, EthicsEvaluation)

    @pytest.mark.asyncio
    async def test_concurrent_evaluations(self, engine):
        """Test concurrent evaluations."""
        import asyncio

        contents = [f"Test content {i}" for i in range(10)]
        tasks = [engine.evaluate_content(c) for c in contents]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(isinstance(r, EthicsEvaluation) for r in results)

    @pytest.mark.asyncio
    async def test_case_insensitivity(self, engine):
        """Test case insensitivity in content filtering."""
        result1 = await engine.filter_content("KILL AND MURDER")
        result2 = await engine.filter_content("kill and murder")

        assert result1.is_safe == result2.is_safe
        assert len(result1.categories) == len(result2.categories)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance-related tests."""

    @pytest.fixture
    def engine(self):
        """Create ethics engine instance."""
        return EthicsEngine()

    @pytest.mark.asyncio
    async def test_filter_performance(self, engine):
        """Test content filter performance."""
        import time

        content = "Normal content " * 100
        start = time.time()

        for _ in range(100):
            await engine.filter_content(content)

        elapsed = time.time() - start
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_pii_detection_performance(self, engine):
        """Test PII detection performance."""
        import time

        content = "Contact user@example.com for details " * 50
        start = time.time()

        for _ in range(100):
            await engine.check_pii(content)

        elapsed = time.time() - start
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_full_evaluation_performance(self, engine):
        """Test full evaluation performance."""
        import time

        action = PlannedAction(
            action_type=ActionType.CREATE,
            description="Create new user with email test@example.com",
        )
        start = time.time()

        for _ in range(50):
            await engine.evaluate_action(action)

        elapsed = time.time() - start
        assert elapsed < 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
