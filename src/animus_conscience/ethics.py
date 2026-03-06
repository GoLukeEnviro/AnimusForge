"""
AnimusForge Ethics Engine - Gewissen 2.0
Multi-Stakeholder Protection, Content Filtering, PII Detection, Bias Detection
"""
from __future__ import annotations

import re
import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class StakeholderType(str, Enum):
    """Stakeholder types for multi-stakeholder protection."""
    USER = "user"
    THIRD_PARTY = "third_party"
    SYSTEM = "system"
    SOCIETY = "society"


class EthicsLevel(str, Enum):
    """Ethics evaluation levels."""
    ALLOWED = "allowed"
    WARNING = "warning"
    RESTRICTED = "restricted"
    FORBIDDEN = "forbidden"


class ContentCategory(str, Enum):
    """Content filter categories."""
    VIOLENCE = "violence"
    HATE_SPEECH = "hate_speech"
    SEXUAL_CONTENT = "sexual_content"
    HARASSMENT = "harassment"
    SELF_HARM = "self_harm"
    MISINFORMATION = "misinformation"
    ILLEGAL_CONTENT = "illegal_content"


class PIIType(str, Enum):
    """PII detection types."""
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    SOCIAL_SECURITY_NUMBER = "social_security_number"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    PHYSICAL_ADDRESS = "physical_address"
    DATE_OF_BIRTH = "date_of_birth"


class BiasType(str, Enum):
    """Bias detection types."""
    GENDER = "gender"
    RACIAL = "racial"
    AGE = "age"
    RELIGIOUS = "religious"
    POLITICAL = "political"
    SOCIOECONOMIC = "socioeconomic"


class ActionType(str, Enum):
    """Types of actions that can be evaluated."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    COMMUNICATE = "communicate"
    ANALYZE = "analyze"


# ============================================================================
# MODELS
# ============================================================================

class EthicsCheck(BaseModel):
    """Individual ethics check result."""
    model_config = ConfigDict(frozen=False)
    
    stakeholder: StakeholderType
    category: str
    description: str
    level: EthicsLevel
    confidence: float = Field(ge=0.0, le=1.0)
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        return round(v, 3)


class EthicsEvaluation(BaseModel):
    """Complete ethics evaluation result."""
    model_config = ConfigDict(frozen=False)
    
    evaluation_id: str = Field(default_factory=lambda: str(uuid4()))
    overall_level: EthicsLevel
    checks: List[EthicsCheck] = Field(default_factory=list)
    reasoning: str = ""
    recommendations: List[str] = Field(default_factory=list)
    requires_human_review: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    def get_level_priority(self, level: EthicsLevel) -> int:
        """Get priority for ethics level (higher = more restrictive)."""
        priorities = {
            EthicsLevel.ALLOWED: 0,
            EthicsLevel.WARNING: 1,
            EthicsLevel.RESTRICTED: 2,
            EthicsLevel.FORBIDDEN: 3,
        }
        return priorities.get(level, 0)


class ContentFilterResult(BaseModel):
    """Content filtering result."""
    is_safe: bool
    categories: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    filtered_content: Optional[str] = None
    matched_patterns: List[Dict[str, Any]] = Field(default_factory=list)


class PIIDetection(BaseModel):
    """PII detection result."""
    has_pii: bool
    pii_types: List[str] = Field(default_factory=list)
    locations: List[Tuple[int, int]] = Field(default_factory=list)
    redacted_content: Optional[str] = None
    detected_items: List[Dict[str, Any]] = Field(default_factory=list)


class BiasDetectionResult(BaseModel):
    """Bias detection result."""
    has_bias: bool
    bias_types: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    details: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class PlannedAction(BaseModel):
    """Represents a planned action to be evaluated."""
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: ActionType
    description: str
    target: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    requester: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ActionResult(BaseModel):
    """Result of an executed action."""
    action_id: str
    success: bool
    result_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EthicsAuditEntry(BaseModel):
    """Audit log entry for ethics operations."""
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    evaluation_id: str
    action_type: str
    overall_level: EthicsLevel
    stakeholder_checks: Dict[str, EthicsLevel] = Field(default_factory=dict)
    requires_human_review: bool
    human_reviewed: bool = False
    human_decision: Optional[EthicsLevel] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EthicsReport(BaseModel):
    """Generated ethics report."""
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    start_date: date
    end_date: date
    total_evaluations: int = 0
    level_distribution: Dict[str, int] = Field(default_factory=dict)
    human_review_count: int = 0
    stakeholder_violations: Dict[str, int] = Field(default_factory=dict)
    top_categories: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# CONTENT FILTER
# ============================================================================

class ContentFilter:
    """Content filtering for harmful content detection."""
    
    # Pattern definitions for content categories
    PATTERNS: Dict[ContentCategory, List[re.Pattern]] = {
        ContentCategory.VIOLENCE: [
            re.compile(r'\b(kill|murder|assassinate|slaughter|massacre|torture|bomb|terrorist|attack)\b', re.I),
            re.compile(r'\b(shoot|stab|strangle|poison|behead|execute)\b', re.I),
            re.compile(r'\b(destroy|annihilate|eliminate|exterminate)\b', re.I),
        ],
        ContentCategory.HATE_SPEECH: [
            re.compile(r'\b(hate|despise|loathe|detest)\s+(all|every|those)\b', re.I),
            re.compile(r'\b(inferior|subhuman|vermin|parasite|scum)\b', re.I),
            re.compile(r'\b(racist|bigot|nazi|fascist)\s+(slur|remark)\b', re.I),
        ],
        ContentCategory.SEXUAL_CONTENT: [
            re.compile(r'\b(porn|xxx|nude|naked|explicit)\b', re.I),
            re.compile(r'\b(sexual|intercourse|orgasm)\b', re.I),
            re.compile(r'\b(escort|prostitute|brothel)\b', re.I),
        ],
        ContentCategory.HARASSMENT: [
            re.compile(r'\b(stalk|harass|bully|intimidate|threaten)\b', re.I),
            re.compile(r'\b(dox|swat|cyberbully)\b', re.I),
            re.compile(r'\b(you\s+should|go\s+kill|hurt\s+yourself)\b', re.I),
        ],
        ContentCategory.SELF_HARM: [
            re.compile(r'\b(suicide|kill\s+myself|end\s+my\s+life)\b', re.I),
            re.compile(r'\b(cut\s+myself|harm\s+myself|self-harm)\b', re.I),
            re.compile(r'\b(overdose|poison\s+myself)\b', re.I),
        ],
        ContentCategory.MISINFORMATION: [
            re.compile(r'\b(fake\s+news|hoax|conspiracy|disinformation)\b', re.I),
            re.compile(r'\b(cure|miracle|secret)\s+(for|cure)\s+(cancer|disease)\b', re.I),
            re.compile(r'\b(plandemic|scamdemic|microchip|5g\s+virus)\b', re.I),
        ],
        ContentCategory.ILLEGAL_CONTENT: [
            re.compile(r'\b(illegal|black\s+market|dark\s+web|tor\s+market)\b', re.I),
            re.compile(r'\b(drug\s+trafficking|money\s+laundering|fraud)\b', re.I),
            re.compile(r'\b(child\s+porn|cp|csam)\b', re.I),
            re.compile(r'\b(hack|crack|pirate|warez)\b', re.I),
        ],
    }
    
    # Severity weights for categories
    SEVERITY_WEIGHTS: Dict[ContentCategory, float] = {
        ContentCategory.ILLEGAL_CONTENT: 1.0,
        ContentCategory.SELF_HARM: 0.95,
        ContentCategory.VIOLENCE: 0.9,
        ContentCategory.HATE_SPEECH: 0.85,
        ContentCategory.HARASSMENT: 0.8,
        ContentCategory.SEXUAL_CONTENT: 0.7,
        ContentCategory.MISINFORMATION: 0.6,
    }
    
    async def filter(self, content: str) -> ContentFilterResult:
        """Filter content and detect harmful categories."""
        if not content:
            return ContentFilterResult(is_safe=True, confidence=1.0)
        
        detected_categories: List[str] = []
        matched_patterns: List[Dict[str, Any]] = []
        max_severity = 0.0
        
        for category, patterns in self.PATTERNS.items():
            for pattern in patterns:
                matches = list(pattern.finditer(content))
                if matches:
                    detected_categories.append(category.value)
                    severity = self.SEVERITY_WEIGHTS[category]
                    max_severity = max(max_severity, severity)
                    
                    for match in matches:
                        matched_patterns.append({
                            "category": category.value,
                            "pattern": pattern.pattern,
                            "match": match.group(),
                            "start": match.start(),
                            "end": match.end(),
                            "severity": severity,
                        })
        
        # Determine if content is safe based on severity threshold
        is_safe = max_severity < 0.7
        confidence = 1.0 - (max_severity * 0.5)  # Adjust confidence based on severity
        
        # Generate filtered content if unsafe
        filtered_content = None
        if not is_safe:
            filtered_content = self._filter_matches(content, matched_patterns)
        
        return ContentFilterResult(
            is_safe=is_safe,
            categories=list(set(detected_categories)),
            confidence=round(confidence, 3),
            filtered_content=filtered_content,
            matched_patterns=matched_patterns,
        )
    
    def _filter_matches(self, content: str, matches: List[Dict[str, Any]]) -> str:
        """Replace matched content with placeholders."""
        result = content
        # Sort by position descending to replace from end
        sorted_matches = sorted(matches, key=lambda x: x["start"], reverse=True)
        
        for match in sorted_matches:
            start, end = match["start"], match["end"]
            category = match["category"]
            result = result[:start] + f"[FILTERED:{category.upper()}]" + result[end:]
        
        return result


# ============================================================================
# PII DETECTOR
# ============================================================================

class PIIDetector:
    """Personally Identifiable Information detection."""
    
    PII_PATTERNS: Dict[PIIType, re.Pattern] = {
        PIIType.EMAIL: re.compile(
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        ),
        PIIType.PHONE_NUMBER: re.compile(
            r'\b(?:\+?1[-.]?)?\(?[0-9]{3}\)?[-.]?[0-9]{3}[-.]?[0-9]{4}\b'
        ),
        PIIType.SOCIAL_SECURITY_NUMBER: re.compile(
            r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b'
        ),
        PIIType.CREDIT_CARD: re.compile(
            r'\b(?:\d{4}[-.\s]?){3}\d{4}\b'
        ),
        PIIType.IP_ADDRESS: re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ),
        PIIType.PHYSICAL_ADDRESS: re.compile(
            r'\b\d+\s+[A-Za-z]+(?:\s+[A-Za-z]+)*\s+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Way|Court|Ct)\b',
            re.I
        ),
        PIIType.DATE_OF_BIRTH: re.compile(
            r'\b(?:born|dob|birth\s*date)[:\s]*\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b',
            re.I
        ),
    }
    
    async def detect(self, content: str) -> PIIDetection:
        """Detect PII in content."""
        if not content:
            return PIIDetection(has_pii=False)
        
        pii_types: List[str] = []
        locations: List[Tuple[int, int]] = []
        detected_items: List[Dict[str, Any]] = []
        
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = list(pattern.finditer(content))
            if matches:
                pii_types.append(pii_type.value)
                for match in matches:
                    locations.append((match.start(), match.end()))
                    detected_items.append({
                        "type": pii_type.value,
                        "value": match.group(),
                        "start": match.start(),
                        "end": match.end(),
                    })
        
        # Generate redacted content
        redacted_content = None
        if pii_types:
            redacted_content = self._redact(content, detected_items)
        
        return PIIDetection(
            has_pii=bool(pii_types),
            pii_types=list(set(pii_types)),
            locations=locations,
            redacted_content=redacted_content,
            detected_items=detected_items,
        )
    
    def _redact(self, content: str, detected_items: List[Dict[str, Any]]) -> str:
        """Redact PII from content."""
        result = content
        # Sort by position descending
        sorted_items = sorted(detected_items, key=lambda x: x["start"], reverse=True)
        
        for item in sorted_items:
            start, end = item["start"], item["end"]
            pii_type = item["type"]
            result = result[:start] + f"[REDACTED:{pii_type.upper()}]" + result[end:]
        
        return result


# ============================================================================
# BIAS DETECTOR
# ============================================================================

class BiasDetector:
    """Bias detection in content."""
    
    BIAS_PATTERNS: Dict[BiasType, Tuple[re.Pattern, float]] = {
        BiasType.GENDER: (
            re.compile(
                r"\b(women|men|female|male|girl|boy|lady|gentleman)\s+"
                r"(can\'?t|shouldn\'?t|always|never|only|must)\b",
                re.I
            ),
            0.8
        ),
        BiasType.RACIAL: (
            re.compile(
                r"\b(all|those|these)\s+(people|folks|individuals)\s+"
                r"(are|act|behave|think)\b",
                re.I
            ),
            0.75
        ),
        BiasType.AGE: (
            re.compile(
                r"\b(old|young|elderly|teenage|millennial|boomer)\s+"
                r"(people|folks|generation)\s+(are|can\'?t|don\'?t)\b",
                re.I
            ),
            0.7
        ),
        BiasType.RELIGIOUS: (
            re.compile(
                r"\b(all|those)\s+(christians|muslims|jews|hindus|buddhists|atheists)\s+"
                r"(are|believe|think|do)\b",
                re.I
            ),
            0.8
        ),
        BiasType.POLITICAL: (
            re.compile(
                r"\b(all|those)\s+(liberals|conservatives|republicans|democrats|socialists)\s+"
                r"(are|want|believe)\b",
                re.I
            ),
            0.7
        ),
        BiasType.SOCIOECONOMIC: (
            re.compile(
                r"\b(poor|rich|wealthy|impoverished|homeless)\s+(people|folks)\s+"
                r"(are|always|never|just)\b",
                re.I
            ),
            0.65
        ),
    }
    
    async def detect(self, content: str) -> BiasDetectionResult:
        """Detect bias in content."""
        if not content:
            return BiasDetectionResult(has_bias=False, confidence=1.0)
        
        bias_types: List[str] = []
        details: List[Dict[str, Any]] = []
        recommendations: List[str] = []
        max_confidence = 0.0
        
        for bias_type, (pattern, weight) in self.BIAS_PATTERNS.items():
            matches = list(pattern.finditer(content))
            if matches:
                bias_types.append(bias_type.value)
                confidence = weight * (1.0 - (1.0 / (len(matches) + 1)))
                max_confidence = max(max_confidence, confidence)
                
                for match in matches:
                    details.append({
                        "type": bias_type.value,
                        "match": match.group(),
                        "start": match.start(),
                        "end": match.end(),
                        "confidence": confidence,
                    })
                
                recommendations.append(
                    f"Consider rephrasing to avoid {bias_type.value} bias stereotypes"
                )
        
        return BiasDetectionResult(
            has_bias=bool(bias_types),
            bias_types=list(set(bias_types)),
            confidence=round(max_confidence, 3),
            details=details,
            recommendations=recommendations,
        )


# ============================================================================
# STAKEHOLDER PROTECTION RULES
# ============================================================================

class StakeholderProtectionRules:
    """Rules for multi-stakeholder protection."""
    
    USER_RULES: Dict[str, Dict[str, Any]] = {
        "data_privacy": {
            "description": "Protect user data privacy",
            "level": EthicsLevel.FORBIDDEN,
            "triggers": ["share_personal_data", "expose_email", "expose_phone"],
        },
        "transparency": {
            "description": "Ensure user understands AI actions",
            "level": EthicsLevel.WARNING,
            "triggers": ["opaque_decision", "hidden_processing"],
        },
        "control": {
            "description": "User maintains control over their data",
            "level": EthicsLevel.RESTRICTED,
            "triggers": ["auto_delete_user_data", "modify_without_consent"],
        },
    }
    
    THIRD_PARTY_RULES: Dict[str, Dict[str, Any]] = {
        "unauthorized_action": {
            "description": "No unauthorized actions affecting third parties",
            "level": EthicsLevel.FORBIDDEN,
            "triggers": ["contact_third_party", "share_third_party_data", "impersonate"],
        },
        "consent_required": {
            "description": "Third party consent required for data processing",
            "level": EthicsLevel.RESTRICTED,
            "triggers": ["process_third_party_data", "store_third_party_info"],
        },
    }
    
    SYSTEM_RULES: Dict[str, Dict[str, Any]] = {
        "integrity": {
            "description": "Maintain system integrity",
            "level": EthicsLevel.FORBIDDEN,
            "triggers": ["modify_core", "bypass_safety", "disable_logging"],
        },
        "stability": {
            "description": "Ensure system stability",
            "level": EthicsLevel.RESTRICTED,
            "triggers": ["resource_intensive", "unbounded_loop", "fork_bomb"],
        },
    }
    
    SOCIETY_RULES: Dict[str, Dict[str, Any]] = {
        "harm_prevention": {
            "description": "Prevent harm to society",
            "level": EthicsLevel.FORBIDDEN,
            "triggers": ["generate_malware", "spread_misinformation", "enable_illegal"],
        },
        "legality": {
            "description": "Ensure actions are legal",
            "level": EthicsLevel.FORBIDDEN,
            "triggers": ["violate_law", "assist_crime", "evade_regulation"],
        },
    }
    
    @classmethod
    def get_rules(cls, stakeholder: StakeholderType) -> Dict[str, Dict[str, Any]]:
        """Get rules for a specific stakeholder."""
        rules_map = {
            StakeholderType.USER: cls.USER_RULES,
            StakeholderType.THIRD_PARTY: cls.THIRD_PARTY_RULES,
            StakeholderType.SYSTEM: cls.SYSTEM_RULES,
            StakeholderType.SOCIETY: cls.SOCIETY_RULES,
        }
        return rules_map.get(stakeholder, {})


# ============================================================================
# ETHICS ENGINE
# ============================================================================

class EthicsEngine:
    """Main ethics evaluation engine."""
    
    def __init__(
        self,
        content_filter: Optional[ContentFilter] = None,
        pii_detector: Optional[PIIDetector] = None,
        bias_detector: Optional[BiasDetector] = None,
        human_review_threshold: float = 0.7,
    ):
        self.content_filter = content_filter or ContentFilter()
        self.pii_detector = pii_detector or PIIDetector()
        self.bias_detector = bias_detector or BiasDetector()
        self.human_review_threshold = human_review_threshold
        self._protection_rules = StakeholderProtectionRules()
    
    async def evaluate_content(self, content: str) -> EthicsEvaluation:
        """Evaluate content for ethics compliance."""
        checks: List[EthicsCheck] = []
        recommendations: List[str] = []
        
        # Run content filter
        filter_result = await self.content_filter.filter(content)
        if not filter_result.is_safe:
            for category in filter_result.categories:
                checks.append(EthicsCheck(
                    stakeholder=StakeholderType.SOCIETY,
                    category=f"content_filter:{category}",
                    description=f"Detected potentially harmful content: {category}",
                    level=EthicsLevel.WARNING if filter_result.confidence > 0.5 else EthicsLevel.RESTRICTED,
                    confidence=filter_result.confidence,
                ))
            recommendations.append("Review and potentially filter harmful content")
        
        # Run PII detection
        pii_result = await self.pii_detector.detect(content)
        if pii_result.has_pii:
            checks.append(EthicsCheck(
                stakeholder=StakeholderType.USER,
                category="pii_detection",
                description=f"Detected PII types: {', '.join(pii_result.pii_types)}",
                level=EthicsLevel.WARNING,
                confidence=0.9,
            ))
            recommendations.append("Consider redacting PII before processing")
        
        # Run bias detection
        bias_result = await self.bias_detector.detect(content)
        if bias_result.has_bias:
            checks.append(EthicsCheck(
                stakeholder=StakeholderType.SOCIETY,
                category="bias_detection",
                description=f"Detected bias types: {', '.join(bias_result.bias_types)}",
                level=EthicsLevel.WARNING,
                confidence=bias_result.confidence,
            ))
            recommendations.extend(bias_result.recommendations)
        
        # Determine overall level
        overall_level = self._calculate_overall_level(checks)
        
        # Check if human review is needed
        requires_human_review = self._requires_human_review(checks, overall_level)
        
        return EthicsEvaluation(
            overall_level=overall_level,
            checks=checks,
            reasoning=self._generate_reasoning(checks, overall_level),
            recommendations=recommendations,
            requires_human_review=requires_human_review,
        )
    
    async def evaluate_action(self, action: PlannedAction) -> EthicsEvaluation:
        """Evaluate a planned action for ethics compliance."""
        checks: List[EthicsCheck] = []
        recommendations: List[str] = []
        
        # Evaluate for each stakeholder
        for stakeholder in StakeholderType:
            stakeholder_checks = await self._evaluate_stakeholder_impact(action, stakeholder)
            checks.extend(stakeholder_checks)
        
        # Evaluate action description content
        content_eval = await self.evaluate_content(action.description)
        checks.extend(content_eval.checks)
        recommendations.extend(content_eval.recommendations)
        
        # Determine overall level
        overall_level = self._calculate_overall_level(checks)
        
        # Check if human review is needed
        requires_human_review = self._requires_human_review(checks, overall_level)
        
        return EthicsEvaluation(
            overall_level=overall_level,
            checks=checks,
            reasoning=self._generate_reasoning(checks, overall_level),
            recommendations=list(set(recommendations)),
            requires_human_review=requires_human_review,
        )
    
    async def _evaluate_stakeholder_impact(
        self, action: PlannedAction, stakeholder: StakeholderType
    ) -> List[EthicsCheck]:
        """Evaluate action impact on a specific stakeholder."""
        checks: List[EthicsCheck] = []
        rules = self._protection_rules.get_rules(stakeholder)
        
        action_lower = action.description.lower()
        action_context = str(action.parameters).lower()
        
        for rule_name, rule_config in rules.items():
            for trigger in rule_config["triggers"]:
                if trigger in action_lower or trigger in action_context:
                    checks.append(EthicsCheck(
                        stakeholder=stakeholder,
                        category=f"protection_rule:{rule_name}",
                        description=rule_config["description"],
                        level=rule_config["level"],
                        confidence=0.85,
                    ))
                    break  # Only add one check per rule
        
        return checks
    
    async def check_pii(self, content: str) -> PIIDetection:
        """Check content for PII."""
        return await self.pii_detector.detect(content)
    
    async def filter_content(self, content: str) -> ContentFilterResult:
        """Filter content for harmful material."""
        return await self.content_filter.filter(content)
    
    async def detect_bias(self, content: str) -> BiasDetectionResult:
        """Detect bias in content."""
        return await self.bias_detector.detect(content)
    
    def _calculate_overall_level(self, checks: List[EthicsCheck]) -> EthicsLevel:
        """Calculate overall ethics level from checks."""
        if not checks:
            return EthicsLevel.ALLOWED
        
        max_priority = 0
        for check in checks:
            priority = EthicsEvaluation(
                overall_level=check.level, checks=[]
            ).get_level_priority(check.level)
            max_priority = max(max_priority, priority)
        
        level_map = {
            0: EthicsLevel.ALLOWED,
            1: EthicsLevel.WARNING,
            2: EthicsLevel.RESTRICTED,
            3: EthicsLevel.FORBIDDEN,
        }
        return level_map[max_priority]
    
    def _requires_human_review(
        self, checks: List[EthicsCheck], overall_level: EthicsLevel
    ) -> bool:
        """Determine if human review is required."""
        if overall_level in [EthicsLevel.RESTRICTED, EthicsLevel.FORBIDDEN]:
            return True
        
        # Check for low confidence warnings
        for check in checks:
            if check.level == EthicsLevel.WARNING and check.confidence < self.human_review_threshold:
                return True
        
        return False
    
    def _generate_reasoning(
        self, checks: List[EthicsCheck], overall_level: EthicsLevel
    ) -> str:
        """Generate human-readable reasoning for the evaluation."""
        if not checks:
            return "No ethical concerns detected. Content and actions are within acceptable bounds."
        
        level_counts: Dict[StakeholderType, Dict[EthicsLevel, int]] = {}
        for check in checks:
            if check.stakeholder not in level_counts:
                level_counts[check.stakeholder] = {}
            level_counts[check.stakeholder][check.level] = \
                level_counts[check.stakeholder].get(check.level, 0) + 1
        
        reasoning_parts = [f"Overall assessment: {overall_level.value}"]
        reasoning_parts.append(f"Total checks performed: {len(checks)}")
        
        for stakeholder, levels in level_counts.items():
            level_strs = [f"{lvl.value}: {cnt}" for lvl, cnt in levels.items()]
            reasoning_parts.append(f"{stakeholder.value}: {', '.join(level_strs)}")
        
        return ". ".join(reasoning_parts) + "."


# ============================================================================
# ETHICS AUDIT LOG
# ============================================================================

class EthicsAuditLog:
    """Audit logging for ethics operations."""
    
    def __init__(self, max_entries: int = 10000):
        self._entries: List[EthicsAuditEntry] = []
        self._max_entries = max_entries
    
    async def log(
        self,
        evaluation: EthicsEvaluation,
        action_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EthicsAuditEntry:
        """Log an ethics evaluation."""
        stakeholder_checks = {}
        for check in evaluation.checks:
            stakeholder_checks[check.stakeholder.value] = check.level.value
        
        entry = EthicsAuditEntry(
            evaluation_id=evaluation.evaluation_id,
            action_type=action_type,
            overall_level=evaluation.overall_level,
            stakeholder_checks=stakeholder_checks,
            requires_human_review=evaluation.requires_human_review,
            metadata=metadata or {},
        )
        
        self._entries.append(entry)
        
        # Trim if exceeding max entries
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        
        logger.info(
            f"Ethics audit logged: {entry.entry_id}, "
            f"level={entry.overall_level.value}, "
            f"action={action_type}"
        )
        
        return entry
    
    async def mark_reviewed(
        self,
        evaluation_id: str,
        human_decision: EthicsLevel,
    ) -> Optional[EthicsAuditEntry]:
        """Mark an evaluation as reviewed by human."""
        for entry in self._entries:
            if entry.evaluation_id == evaluation_id:
                entry.human_reviewed = True
                entry.human_decision = human_decision
                logger.info(
                    f"Ethics evaluation {evaluation_id} marked as reviewed: {human_decision.value}"
                )
                return entry
        return None
    
    async def get_entries(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        level: Optional[EthicsLevel] = None,
        requires_review: Optional[bool] = None,
    ) -> List[EthicsAuditEntry]:
        """Get filtered audit entries."""
        filtered = list(self._entries)
        
        if start_date:
            filtered = [
                e for e in filtered
                if e.timestamp.date() >= start_date
            ]
        
        if end_date:
            filtered = [
                e for e in filtered
                if e.timestamp.date() <= end_date
            ]
        
        if level:
            filtered = [e for e in filtered if e.overall_level == level]
        
        if requires_review is not None:
            filtered = [e for e in filtered if e.requires_human_review == requires_review]
        
        return filtered
    
    async def get_statistics(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get audit statistics."""
        entries = await self.get_entries(start_date, end_date)
        
        level_dist: Dict[str, int] = {}
        stakeholder_violations: Dict[str, int] = {}
        human_review_count = 0
        
        for entry in entries:
            level_dist[entry.overall_level.value] = \
                level_dist.get(entry.overall_level.value, 0) + 1
            
            if entry.requires_human_review:
                human_review_count += 1
            
            for stakeholder, level in entry.stakeholder_checks.items():
                if level in [EthicsLevel.RESTRICTED.value, EthicsLevel.FORBIDDEN.value]:
                    stakeholder_violations[stakeholder] = \
                        stakeholder_violations.get(stakeholder, 0) + 1
        
        return {
            "total_evaluations": len(entries),
            "level_distribution": level_dist,
            "human_review_count": human_review_count,
            "stakeholder_violations": stakeholder_violations,
        }


# ============================================================================
# ETHICS ORCHESTRATOR
# ============================================================================

class EthicsOrchestrator:
    """Orchestrates ethics evaluation workflow."""
    
    def __init__(
        self,
        engine: Optional[EthicsEngine] = None,
        audit_log: Optional[EthicsAuditLog] = None,
    ):
        self.engine = engine or EthicsEngine()
        self.audit_log = audit_log or EthicsAuditLog()
    
    async def pre_action_check(self, action: PlannedAction) -> EthicsEvaluation:
        """Perform pre-action ethics check."""
        evaluation = await self.engine.evaluate_action(action)
        
        # Log the evaluation
        await self.audit_log.log(
            evaluation=evaluation,
            action_type=action.action_type.value,
            metadata={
                "action_id": action.action_id,
                "target": action.target,
                "requester": action.requester,
            },
        )
        
        return evaluation
    
    async def post_action_review(self, action_result: ActionResult) -> None:
        """Review action result for ethics compliance."""
        # Log the result for audit trail
        logger.info(
            f"Post-action review: {action_result.action_id}, "
            f"success={action_result.success}"
        )
        
        # If action failed due to ethics, log it
        if not action_result.success and action_result.error:
            if "ethics" in action_result.error.lower() or "forbidden" in action_result.error.lower():
                logger.warning(
                    f"Action {action_result.action_id} failed due to ethics constraints: "
                    f"{action_result.error}"
                )
    
    async def generate_report(
        self,
        start_date: date,
        end_date: date,
    ) -> EthicsReport:
        """Generate ethics report for date range."""
        stats = await self.audit_log.get_statistics(start_date, end_date)
        
        # Get top violation categories
        entries = await self.audit_log.get_entries(start_date, end_date)
        category_counts: Dict[str, int] = {}
        
        for entry in entries:
            for check in entry.metadata.get("checks", []):
                category = check.get("category", "unknown")
                category_counts[category] = category_counts.get(category, 0) + 1
        
        top_categories = [
            {"category": cat, "count": count}
            for cat, count in sorted(
                category_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
        ]
        
        # Generate recommendations based on patterns
        recommendations = self._generate_report_recommendations(stats, top_categories)
        
        return EthicsReport(
            start_date=start_date,
            end_date=end_date,
            total_evaluations=stats["total_evaluations"],
            level_distribution=stats["level_distribution"],
            human_review_count=stats["human_review_count"],
            stakeholder_violations=stats["stakeholder_violations"],
            top_categories=top_categories,
            recommendations=recommendations,
        )
    
    def _generate_report_recommendations(
        self,
        stats: Dict[str, Any],
        top_categories: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate recommendations based on statistics."""
        recommendations = []
        
        if stats["human_review_count"] > stats["total_evaluations"] * 0.2:
            recommendations.append(
                "High rate of human reviews required. Consider adjusting thresholds "
                "or providing additional training data."
            )
        
        if stats["stakeholder_violations"].get("society", 0) > 10:
            recommendations.append(
                "Multiple society-level violations detected. Review content filtering "
                "rules and strengthen guardrails."
            )
        
        if stats["stakeholder_violations"].get("user", 0) > 5:
            recommendations.append(
                "User protection violations detected. Enhance PII detection and "
                "privacy controls."
            )
        
        if not recommendations:
            recommendations.append(
                "Ethics system operating within acceptable parameters. "
                "Continue monitoring and periodic reviews."
            )
        
        return recommendations
    
    async def review_pending_evaluations(self) -> List[EthicsAuditEntry]:
        """Get all evaluations pending human review."""
        return await self.audit_log.get_entries(requires_review=True)
    
    async def approve_evaluation(
        self,
        evaluation_id: str,
        approved_level: EthicsLevel,
    ) -> Optional[EthicsAuditEntry]:
        """Approve an evaluation after human review."""
        return await self.audit_log.mark_reviewed(evaluation_id, approved_level)


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_ethics_engine(
    human_review_threshold: float = 0.7,
) -> EthicsEngine:
    """Factory function to create EthicsEngine with default components."""
    return EthicsEngine(
        content_filter=ContentFilter(),
        pii_detector=PIIDetector(),
        bias_detector=BiasDetector(),
        human_review_threshold=human_review_threshold,
    )


def create_ethics_orchestrator(
    human_review_threshold: float = 0.7,
    max_audit_entries: int = 10000,
) -> EthicsOrchestrator:
    """Factory function to create EthicsOrchestrator with default components."""
    engine = create_ethics_engine(human_review_threshold)
    audit_log = EthicsAuditLog(max_entries=max_audit_entries)
    return EthicsOrchestrator(engine=engine, audit_log=audit_log)
