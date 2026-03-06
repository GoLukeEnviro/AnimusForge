
# AnimusForge (ehemals OpenClaw Persona Genesis Engine)
## Phase 9: Fundamentale Infrastruktur-Resilienz

---

## 1. Executive Summary

Diese Phase adressiert die in Phase 6 identifizierten kritischen Schwachstellen und definiert konkrete Architektur-Entscheidungen für eine resiliente Infrastruktur. Der Fokus liegt auf der Beseitigung von Single-Points-of-Failure und der Implementierung robuster Failover-Mechanismen.

**Ziel:** Transformation von einer fragilen Single-Instance-Architektur zu einer hochverfügbaren, resilienten Produktionsumgebung.

**Zeithorizont:** Sprint 1-2 (Kritisch)

---

## 2. Architektur-Entscheidungen (ADRs)

### ADR-004: Multi-Provider LLM Gateway

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ADR-004: MULTI-PROVIDER LLM GATEWAY                   │
└─────────────────────────────────────────────��───────────────────────────┘

STATUS: ✅ APPROVED

KONTEXT:
┌─────────────────────────────────────────────────────────────────────────┐
│  Problem: LLM-Provider (OpenAI, Anthropic) sind kritische Single-Points │
│  of Failure. Ein Ausfall führt zu 100% Funktionsunfähigkeit.            │
│                                                                         │
│  Betroffene Komponenten:                                                │
│  ├── Soul Forge (Persona-Generierung)                                  │
│  ├── Persona Theater (Agentic Loop)                                    │
│  └── Gewissen 2.0 (Content-Analyse)                                    │
│                                                                         │
│  Risiken:                                                               │
│  ├── Service Outage (0.1-0.5% Verfügbarkeit)                           │
│  ├── Rate Limiting bei Lastspitzen                                     │
│  ├── API Changes / Deprecation                                         │
│  └── Content Policy Changes                                            │
└─────────────────────────────────────────────────────────────────────────┘

ENTSCHEIDUNG:
┌─────────────────────────────────────────────────────────────────────────┐
│  Implementierung eines zentralen LLM Gateway mit:                       │
│                                                                         │
│  1. MULTI-PROVIDER ABSTRACTION                                         │
│     ├── Einheitliches Interface für alle Provider                      │
│     ├── Provider-agnostische Request/Response-Modelle                  │
│     └── Automatische Format-Konvertierung                              │
│                                                                         │
│  2. INTELLIGENT ROUTING                                                │
│     ├── Priority-basierte Provider-Auswahl                             │
│     ├── Health-Check-basiertes Routing                                 │
│     ├── Cost-optimierte Routing-Entscheidungen                         │
│     └── Latency-basierte Lastverteilung                                │
│                                                                         │
│  3. GRACEFUL FAILOVER                                                  │
│     ├── Automatischer Wechsel bei Provider-Ausfall                     │
│     ├── Exponential Backoff bei Rate Limits                            │
│     ├── Circuit Breaker pro Provider                                   │
│     └── Emergency Fallback auf lokales LLM                             │
└─────────────────────────────────────────────────────────────────────────┘

KONSEQUENZEN:
┌─────────────────────────────────────────────────────────────────────────┐
│  POSITIV:                                                               │
│  ✅ Eliminiert Single-Point-of-Failure                                 │
│  ✅ Erhöht Verfügbarkeit auf 99.9%                                     │
│  ✅ Ermöglicht Cost-Optimierung                                        │
│  ✅ Unabhängigkeit von einzelnen Providern                             │
│                                                                         │
│  NEGATIV:                                                               │
│  ⚠️ Zusätzliche Komplexität (Gateway-Layer)                            │
│  ⚠️ Leicht erhöhte Latenz durch Abstraktion                           │
│  ⚠️ Konsistenz-Unterschiede zwischen Providern                         │
│  ⚠️ Höhere Betriebskosten (Multiple API-Keys)                          │
└─────────────────────────────────────────────────────────────────────────┘

IMPLEMENTIERUNGS-PRIORITÄT: 🔴 KRITISCH (Sprint 1)
```

### ADR-005: Database High-Availability Cluster

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ADR-005: DATABASE HIGH-AVAILABILITY CLUSTER           │
└─────────────────────────────────────────────────────────────────────────┘

STATUS: ✅ APPROVED

KONTEXT:
┌─────────────────────────────────────────────────────────────────────────┐
│  Problem: Neo4j und Qdrant als Single-Node-Instanzen sind kritische    │
│  SPOFs. Ausfall führt zu Datenverlust und System-Instabilität.         │
│                                                                         │
│  Aktuelle Konfiguration:                                                │
│  ├── Neo4j: Single Instance, keine Replikation                         │
│  ├── Qdrant: Single Instance, keine Replikation                        │
│  └── Redis: ⚠️ Sentinel möglich, aber nicht konfiguriert               │
└─────────────────────────────────────────────────────────────────────────┘

ENTSCHEIDUNG:
┌─────────────────────────────────────────────────────────────────────────┐
│  Implementierung einer Multi-Tier HA-Architektur:                       │
│                                                                         │
│  NEO4J CAUSAL CLUSTER:                                                  │
│  ├── 3 Core Nodes (Raft Consensus)                                     │
│  ├── 2 Read Replicas (Query Offloading)                                │
│  ├── Automatisches Failover (< 30s)                                    │
│  └── Causal Consistency für kritische Operationen                      │
│                                                                         │
│  QDRANT CLUSTER:                                                        │
│  ├── 3 Nodes mit Raft-based Replication                                │
│  ├── Sharding für horizontale Skalierung                               │
│  ├── Read Replicas für Such-Queries                                    │
│  └── Snapshot-Backups alle 6 Stunden                                   │
│                                                                         │
│  REDIS HIGH-AVAILABILITY:                                               │
│  ├── Redis Sentinel (3 Instanzen)                                      │
│  ├── Master-Slave Replikation                                          │
│  ├── Automatisches Failover (< 10s)                                    │
│  └── AOF + RDB Persistence                                             │
└─────────────────────────────────────────────────────────────────────────┘

KONSEQUENZEN:
┌─────────────────────────────────────────────────────────────────────────┐
│  POSITIV:                                                               │
│  ✅ Keine Single-Points-of-Failure mehr                                │
│  ✅ Automatisches Failover                                              │
│  ✅ Bessere Read-Performance durch Replicas                            │
│  ✅ Datensicherheit durch Replikation                                  │
│                                                                         │
│  NEGATIV:                                                               │
│  ⚠️ 3-5x höhere Infrastruktur-Kosten                                  │
│  ⚠️ Komplexeres Operations-Management                                  │
│  ⚠️ Write-Latency durch Consensus-Protokoll                            │
│  ⚠️ Erfordert erfahrene DBAs                                           │
└─────────────────────────────────────────────────────────────────────────┘

IMPLEMENTIERUNGS-PRIORITÄT: 🔴 KRITISCH (Sprint 1)
```

### ADR-006: 3-Level Kill-Switch Architektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ADR-006: 3-LEVEL KILL-SWITCH ARCHITEKTUR              │
└─────────────────────────────────────────────────────────────────────────┘

STATUS: ✅ APPROVED

KONTEXT:
┌─────────────────────────────────────────────────────────────────────────┐
│  Problem: Aktueller Kill-Switch unvollständig und nicht granular.      │
│  Keine Unterscheidung zwischen Graceful Shutdown und Emergency Kill.   │
│                                                                         │
│  Identifizierte Lücken:                                                 │
│  ├── Keine Resource-Limit-Überwachung                                  │
│  ├── Keine Anomalous Behavior Detection                                │
│  ├── Keine Graceful Degradation                                        │
│  └── Kein State-Snapshot bei Kill                                      │
└─────────────────────────────────────────────────────────────────────────┘

ENTSCHEIDUNG:
┌─────────────────────────────────────────────────────────────────────────┐
│  Implementierung einer 3-Level Kill-Switch Hierarchie:                  │
│                                                                         │
│  LEVEL 1: SOFT STOP (Graceful)                                          │
│  ├── Trigger: Max Iterations, Timeout, User-Request                    │
│  ├── Aktion: Aktuelle Iteration beenden, State persistieren            │
│  ├── Recovery: Automatischer Restart möglich                           │
│  └── Latenz: < 5s bis vollständiger Stopp                              │
│                                                                         │
│  LEVEL 2: HARD STOP (Immediate)                                         │
│  ├── Trigger: Resource-Limit, Token-Limit, Content-Filter              │
│  ├── Aktion: Sofortige Unterbrechung, State-Dump, Alert                │
│  ├── Recovery: Manuelle Prüfung erforderlich                           │
│  └── Latenz: < 1s bis vollständiger Stopp                              │
│                                                                         │
│  LEVEL 3: EMERGENCY KILL (Force)                                        │
│  ├── Trigger: Security Violation, Anomalous Behavior                   │
│  ├── Aktion: Prozess-Terminierung, Incident-Report                     │
│  ├── Recovery: Full Investigation erforderlich                          │
│  └── Latenz: Sofort (< 100ms)                                          │
└─────────────────────────────────────────────────────────────────────────┘

KONSEQUENZEN:
┌─────────────────────────────────────────────────────────────────────────┐
│  POSITIV:                                                               │
│  ✅ Granulare Kontrolle über Persona-Runtime                           │
│  ✅ Verhindert Ressourcen-Erschöpfung                                  │
│  ✅ Ermöglicht Graceful Degradation                                    │
│  ✅ Vollständige Auditierbarkeit                                       │
│                                                                         │
│  NEGATIV:                                                               │
│  ⚠️ Zusätzliche Monitoring-Infrastruktur                               │
│  ⚠️ Komplexere State-Management-Logik                                  │
│  ⚠️ Potentiell mehr False-Positives bei Anomaly Detection             │
└─────────────────────────────────────────────────────────────────────────┘

IMPLEMENTIERUNGS-PRIORITÄT: 🔴 KRITISCH (Sprint 1)
```

### ADR-007: API Gateway Load Balancing

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ADR-007: API GATEWAY LOAD BALANCING                   │
└─────────────────────────────────────────────────────────────────────────┘

STATUS: ✅ APPROVED

KONTEXT:
┌─────────────────────────────────────────────────────────────────────────┐
│  Problem: FastAPI als Single Instance ist SPOF für alle API-Calls.     │
│  Ausfall = 100% API-Unverfügbarkeit.                                   │
│                                                                         │
│  Aktuelle Konfiguration:                                                │
│  ├── 1x FastAPI Instance                                               │
│  ├── Kein Load Balancer                                                │
│  └── Keine Health-Check-basierte Routing                               │
└─────────────────────────────────────────────────────────────────────────┘

ENTSCHEIDUNG:
┌─────────────────────────────────────────────────────────────────────────┐
│  Implementierung einer Load-Balanced API Gateway Architektur:           │
│                                                                         │
│  KUBERNETES DEPLOYMENT:                                                 │
│  ├── Minimum 3 Replicas (Pod Anti-Affinity)                            │
│  ├── Horizontal Pod Autoscaler (HPA)                                   │
│  ├── Liveness/Readiness Probes                                         │
│  └── Rolling Updates mit Rollback                                      │
│                                                                         │
│  LOAD BALANCER:                                                         │
│  ├── NGINX Ingress Controller oder AWS ALB                             │
│  ├── Round-Robin mit Health-Checks                                     │
│  ├── Session Affinity für WebSocket-Verbindungen                       │
│  └── SSL Termination am Load Balancer                                  │
│                                                                         │
│  CIRCUIT BREAKER:                                                       │
│  ├── Pro-Service Circuit Breaker                                       │
│  ├── Fallback Responses bei Degradation                                │
│  └── Automatic Recovery nach Cool-Down                                 │
└─────────────────────────────────────────────────────────────────────────┘

KONSEQUENZEN:
┌─────────────────────────────────────────────────────────────────────────┐
│  POSITIV:                                                               │
│  ✅ Kein Single-Point-of-Failure mehr                                  │
│  ✅ Horizontale Skalierbarkeit                                         │
│  ✅ Zero-Downtime Deployments                                          │
│  ✅ Bessere Lastverteilung                                             │
│                                                                         │
│  NEGATIV:                                                               │
│  ⚠️ Kubernetes-Komplexität                                             │
│  ⚠️ State-Management für Sessions                                      │
│  ⚠️ WebSocket-Sticky-Sessions erforderlich                             │
└─────────────────────────────────────────────────────────────────────────┘

IMPLEMENTIERUNGS-PRIORITÄT: 🔴 KRITISCH (Sprint 1)
```

### ADR-008: Budget Management System

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ADR-008: BUDGET MANAGEMENT SYSTEM                     │
└─────────────────────────────────────────────────────────────────────────┘

STATUS: ✅ APPROVED

KONTEXT:
┌─────────────────────────────────────────────────────────────────────────┐
│  Problem: Keine Kontrolle über LLM-Kosten. Unbegrenzte API-Aufrufe    │
│  können zu unerwarteten Kostenexplosionen führen.                      │
│                                                                         │
│  Risiken:                                                               │
│  ├── Endlosschleifen in Agentic Loop                                   │
│  ├── Böswillige Persona-Generierung                                    │
│  ├── Unkontrollierte Tool-Aufrufe                                      │
│  └── Keine Kosten-Transparenz                                          │
└─────────────────────────────────────────────────────────────────────────┘

ENTSCHEIDUNG:
┌─────────────────────────────────────────────────────────────────────────┐
│  Implementierung eines mehrstufigen Budget-Management-Systems:          │
│                                                                         │
│  LEVEL 1: GLOBAL BUDGET                                                 │
│  ├── Tägliche/Limit pro Gesamtsystem                                   │
│  ├── Hard-Limit mit automatischer Drosselung                           │
│  └── Alert bei 80% Ausschöpfung                                        │
│                                                                         │
│  LEVEL 2: PER-PERSONA BUDGET                                            │
│  ├── Token-Limit pro Persona pro Tag                                   │
│  ├── Request-Limit pro Stunde                                          │
│  └── Graceful Degradation bei Limit-Erreichung                         │
│                                                                         │
│  LEVEL 3: PER-USER BUDGET                                               │
│  ├── Quota basierend auf User-Tier (Free/Pro/Enterprise)               │
│  ├── Roll-over für ungenutzte Quotas                                   │
│  └── Self-Service Dashboard für Verbrauch                              │
│                                                                         │
│  MONITORING & ALERTING:                                                 │
│  ├── Real-time Cost Dashboard                                          │
│  ├── Predictive Cost Alerts                                            │
│  └── Automated Budget Reports                                          │
└─────────────────────────────────────────────────────────────────────────┘

KONSEQUENZEN:
┌─────────────────────────────────────────────────────────────────────────┐
│  POSITIV:                                                               │
│  ✅ Kostenkontrolle und -transparenz                                   │
│  ✅ Schutz vor Kostenexplosionen                                       │
│  ✅ Fair-Use-Policy durchsetzbar                                       │
│  ✅ Business-Model-Grundlage (Tiered Pricing)                          │
│                                                                         │
│  NEGATIV:                                                               │
│  ⚠️ Zusätzliche Datenbank-Last (Budget-Tracking)                       │
│  ⚠️ Komplexere Request-Verarbeitung                                    │
│  ⚠️ User-Frustration bei Limits                                        │
└─────────────────────────────────────────────────────────────────────────┘

IMPLEMENTIERUNGS-PRIORITÄT: 🟡 HOCH (Sprint 2)
```

---

## 3. LLM Gateway Architektur

### 3.1 Komponenten-Übersicht

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LLM GATEWAY - KOMPONENTENÜBERSICHT                    │
└─────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────────┐
                           │         ANIMUSFORGE CORE          │
                           │   (Soul Forge, Theater, etc.)     │
                           └───────────────┬───────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           LLM GATEWAY                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                                                                     ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ ││
│  │  │   REQUEST   │  │   ROUTING   │  │  CIRCUIT    │  │  RESPONSE │ ││
│  │  │  VALIDATOR  │──▶│   ENGINE    │──▶│  BREAKER   │──▶│ TRANSFORM │ ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ ││
│  │         │                │                │                │        ││
│  │         ▼                ▼                ▼                ▼        ││
│  │  ┌─────────────────────────────────────────────────────────────┐  ││
│  │  │                    PROVIDER ABSTRACTION                      │  ││
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │  ││
│  │  │  │   OpenAI    │  │  Anthropic  │  │   Local     │         │  ││
│  │  │  │   Adapter   │  │   Adapter   │  │   Adapter   │         │  ││
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘         │  ││
│  │  └─────────────────────────────────────────────────────────────┘  ││
│  │                                                                     ││
│  │  ┌─────────────────────────────────────────────────────────────┐  ││
│  │  │                    CROSS-CUTTING CONCERNS                    │  ││
│  │  │  ├── Budget Tracker         ├── Metrics Collector            │  ││
│  │  │  ├── Rate Limiter           ├── Audit Logger                │  ││
│  │  │  └── Retry Logic            └── Cache Layer                 │  ││
│  │  └─────────────────────────────────────────────────────────────┘  ││
│  │                                                                     ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │    OPENAI     │      │  ANTHROPIC    │      │    OLLAMA     │
           │               │      │               │      │   (Local)     │
           │  GPT-4 Turbo  │      │  Claude 3.5   │      │  Llama 3      │
           │  GPT-4o       │      │  Claude 3     │      │  Mistral      │
           └───────────────┘      └───────────────┘      └───────────────┘
```

### 3.2 Multi-Provider Failover Konzept

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MULTI-PROVIDER FAILOVER FLOW                          │
└─────────────────────────────────────────────────────────────────────────┘

                    REQUEST EINGANG
                          │
                          ▼
              ┌───────────────────────┐
              │   BUDGET CHECK        │
              │   (Global + User)     │
              └───────────┬───────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌───────────┐           ┌───────────┐
        │   OK      │           │  DENIED   │──▶ 429 Response
        └─────┬─────┘           └───────────┘
              │
              ▼
              ┌───────────────────────┐
              │   PROVIDER SELECTION  │
              │   (Priority-based)    │
              └───────────┬───────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
  ┌───────────┐     ┌───────────┐     ┌───────────┐
  │  OPENAI   │     │ ANTHROPIC │     │  LOCAL    │
  │ Priority:1│     │ Priority:2│     │ Priority:3│
  │  ACTIVE   │     │  STANDBY  │     │ EMERGENCY │
  └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
        │                 │                 │
        │   ┌─────────────┘                 │
        │   │                               │
        ▼   ▼                               ▼
  ┌──────────────────────────────────────────────────┐
  │              CIRCUIT BREAKER CHECK               │
  │  ┌────────────────────────────────────────────���┐│
  │  │  State: CLOSED → Request allowed            ││
  │  │  State: OPEN   → Skip provider              ││
  │  │  State: HALF_OPEN → Test request            ││
  │  └─────────────────────────────────────────────┘│
  └──────────────────────┬───────────────────────────┘
                         │
                         ▼
              ┌───────────────────────┐
              │   EXECUTE REQUEST     │
              │   (with timeout)      │
              └───────────┬───────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
  ┌───────────┐     ┌───────────┐     ┌───────────┐
  │  SUCCESS  │     │  RETRY    │     │  FAIL     │
  │           │     │  (3x)     │     │  OVER     │
  └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
        │                 │                 │
        │                 └────────┬────────┘
        │                          │
        ▼                          ▼
  ┌───────────┐           ┌───────────────────┐
  │  RETURN   │           │  NEXT PROVIDER    │
  │  RESPONSE │           │  (Fallback)       │
  └───────────┘           └───────────────────┘
                                    │
                                    ▼
                          ┌───────────────────┐
                          │ ALL PROVIDERS     │
                          │ EXHAUSTED?        │
                          └─────────┬─────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
              ┌───────────┐  ┌───────────┐  ┌───────────┐
              │    NO     │  │   YES     │  │  ERROR    │
              │ (Continue)│  │ (Local)   │  │  Response │
              └───────────┘  └───────────┘  └───────────┘
```

### 3.3 Provider-Konfiguration

```python
# LLM Gateway Konfiguration

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class ProviderStatus(Enum):
    ACTIVE = "active"          # Vollständig verfügbar
    DEGRADED = "degraded"      # Teilweise eingeschränkt
    STANDBY = "standby"        # Backup, nicht aktiv
    UNAVAILABLE = "unavailable" # Nicht erreichbar

@dataclass
class LLMProviderConfig:
    """Konfiguration für einen LLM-Provider"""
    
    # Identifikation
    name: str
    provider_type: str  # "openai", "anthropic", "ollama"
    
    # Verbindung
    base_url: str
    api_key: str | None = None  # None für lokale Provider
    
    # Modelle
    models: list[str] = field(default_factory=list)
    default_model: str = ""
    
    # Routing
    priority: int = 1  # 1 = höchste Priorität
    weight: float = 1.0  # Für Load-Balancing
    
    # Limits
    max_tokens_per_request: int = 128000
    rate_limit_per_minute: int = 500
    timeout_seconds: float = 30.0
    
    # Kosten (USD pro 1M Tokens)
    cost_input_per_million: float = 10.0
    cost_output_per_million: float = 30.0
    
    # Circuit Breaker
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 300.0
    
    # Status
    status: ProviderStatus = ProviderStatus.ACTIVE

# Produktions-Konfiguration
PROVIDER_CONFIGS: dict[str, LLMProviderConfig] = {
    
    "openai_primary": LLMProviderConfig(
        name="openai_primary",
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key="${OPENAI_API_KEY}",
        models=["gpt-4-turbo", "gpt-4o", "gpt-4o-mini"],
        default_model="gpt-4o",
        priority=1,
        weight=0.7,
        max_tokens_per_request=128000,
        rate_limit_per_minute=500,
        timeout_seconds=30.0,
        cost_input_per_million=2.50,
        cost_output_per_million=10.00,
        circuit_breaker_threshold=5,
        circuit_breaker_timeout=300.0,
        status=ProviderStatus.ACTIVE
    ),
    
    "anthropic_fallback": LLMProviderConfig(
        name="anthropic_fallback",
        provider_type="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key="${ANTHROPIC_API_KEY}",
        models=["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
        default_model="claude-3-5-sonnet-20241022",
        priority=2,
        weight=0.3,
        max_tokens_per_request=200000,
        rate_limit_per_minute=400,
        timeout_seconds=45.0,
        cost_input_per_million=3.00,
        cost_output_per_million=15.00,
        circuit_breaker_threshold=5,
        circuit_breaker_timeout=300.0,
        status=ProviderStatus.STANDBY
    ),
    
    "ollama_emergency": LLMProviderConfig(
        name="ollama_emergency",
        provider_type="ollama",
        base_url="http://ollama:11434/api",
        api_key=None,
        models=["llama3.1:70b", "mistral-nemo:12b"],
        default_model="llama3.1:70b",
        priority=3,
        weight=0.0,  # Nur für Emergency
        max_tokens_per_request=32000,
        rate_limit_per_minute=100,
        timeout_seconds=60.0,
        cost_input_per_million=0.0,
        cost_output_per_million=0.0,
        circuit_breaker_threshold=10,
        circuit_breaker_timeout=600.0,
        status=ProviderStatus.STANDBY
    )
}
```

### 3.4 Routing-Strategien

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ROUTING STRATEGIES                                    │
└───────────────────────────────────────────��─────────────────────────────┘

STRATEGIE 1: PRIORITY-BASED (Default)
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Logik:                                                                 │
│  1. Versuche Provider mit Priority 1                                    │
│  2. Bei Fehler → Provider mit Priority 2                                │
│  3. Bei Fehler → Provider mit Priority 3                                │
│                                                                         │
│  Verwendung:                                                            │
│  ├── Kritische Operationen (Persona-Generierung)                        │
│  ├── Best-Quality erforderlich                                         │
│  └── Kosten zweitrangig                                                │
│                                                                         ��
│  Beispiel:                                                              │
│  OpenAI (P1) → Anthropic (P2) → Ollama (P3)                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

STRATEGIE 2: COST-OPTIMIZED
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Logik:                                                                 │
│  1. Berechne erwartete Kosten pro Provider                             │
│  2. Wähle günstigsten verfügbaren Provider                             │
│  3. Fallback bei Nichtverfügbarkeit                                    │
│                                                                         │
│  Verwendung:                                                            │
│  ├── Bulk-Operationen                                                   │
│  ├── Non-critical Tasks                                                │
│  └── Budget-constrained Szenarien                                      │
│                                                                         │
│  Beispiel:                                                              │
│  GPT-4o-mini ($0.15/1M) → Claude Haiku ($0.25/1M) → Llama (Free)       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

STRATEGIE 3: LATENCY-OPTIMIZED
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Logik:                                                                 │
│  1. Tracke durchschnittliche Latenz pro Provider                       │
│  2. Wähle Provider mit niedrigster Latenz                              │
│  3. Berücksichtige地理ische Nähe                                       │
│                                                                         │
│  Verwendung:                                                            │
│  ├── Real-time Interaktionen                                            │
│  ├── Streaming-Responses                                               │
│  └── User-facing Chat                                                  │
│                                                                         │
│  Beispiel:                                                              │
│  Lokale Latenz-Metriken → Schnellster Provider                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

STRATEGIE 4: WEIGHTED ROUND-ROBIN
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Logik:                                                                 │
│  1. Verteile Requests basierend auf Gewichtungen                       │
│  2. OpenAI: 70%, Anthropic: 30%                                        │
│  3. Automatische Rebalance bei Ausfall                                 │
│                                                                         │
│  Verwendung:                                                            │
│  ├── Lastverteilung                                                    │
│  ├── Rate-Limit-Vermeidung                                             │
│  └── Multi-Tenant Szenarien                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Datenbank High-Availability Architektur

### 4.1 Neo4j Cluster Konfiguration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    NEO4J CAUSAL CLUSTER ARCHITEKTUR                      │
└─────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────────┐
                           │         ANIMUSFORGE CORE          │
                           │      (Neo4j Driver)               │
                           └───────────────┬───────────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────────┐
                           │        NEO4J DRIVER               │
                           │   (Routing + Session Management)  │
                           └───────────────┬───────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │   CORE-1      │      │   CORE-2      │      │   CORE-3      │
           │   (Leader)    │◄────►│  (Follower)   │◄────►│  (Follower)   │
           │               │      │               │      │               │
           │  Write + Read │      │  Read Only    │      │  Read Only    │
           │  Port: 7687   │      │  Port: 7687   │      │  Port: 7687   │
           │               │      │               │      │               │
           │  Raft Port:   │      │  Raft Port:   │      │  Raft Port:   │
           │    7000       │      │    7000       │      │    7000       │
           └───────┬───────┘      └───────────────┘      └───────────────┘
                   │                      ▲                      ▲
                   │                      │                      │
                   │         ┌────────────┴────────────┐         │
                   │         │                         │         │
                   ▼         ▼                         ▼         ▼
           ┌───────────────┐                 ┌───────────────┐
           │  READ REPLICA │                 │  READ REPLICA │
           │     RR-1      │                 │     RR-2      │
           │               │                 │               │
           │  Read Only    │                 │  Read Only    │
           │  Port: 7687   │                 │  Port: 7687   │
           │               │                 │               │
           │  Für:         │                 │  Für:         │
           │  - Analytics  │                 │  - Suche      │
           │  - Reports    │                 │  - Backups    │
           └───────────────┘                 └───────────────┘

CLUSTER KONFIGURATION:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  # neo4j.conf (Core Nodes)                                              │
│                                                                         │
│  # Cluster Mode                                                         │
│  dbms.mode=CORE                                                         │
│                                                                         │
│  # Raft Configuration                                                   │
│  causal_clustering.discovery_type=DNS                                   │
│  causal_clustering.discovery_dns=neo4j-core.default.svc.cluster.local   │
│  causal_clustering.minimum_core_cluster_size_at_formation=3             │
│  causal_clustering.minimum_core_cluster_size_at_runtime=3               │
│  causal_clustering.raft_listen_address=0.0.0.0:7000                     │
│  causal_clustering.transaction_listen_address=0.0.0.0:6000              │
│  causal_clustering.raft_advertised_address=:7000                        │
│  causal_clustering.transaction_advertised_address=:6000                 │
│                                                                         │
│  # Performance                                                          │
│  dbms.memory.heap.initial_size=4G                                       │
│  dbms.memory.heap.max_size=4G                                           │
│  dbms.memory.pagecache.size=2G                                          │
│                                                                         │
│  # Backup                                                               │
│  dbms.backup.enabled=true                                               │
│  dbms.backup.listen_address=0.0.0.0:6362                                │
│                                                                         │
└─────────────────��───────────────────────────────────────────────────────┘

FAILOVER VERHALTEN:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Szenario: Leader-Ausfall                                               │
│                                                                         │
│  1. Core-1 (Leader) fällt aus                                          │
│     │                                                                   │
│     ▼                                                                   │
│  2. Raft Consensus erkennt Ausfall (< 2s)                               │
│     │                                                                   │
│     ▼                                                                   │
│  3. Neue Leader-Wahl: Core-2 oder Core-3                                │
│     │                                                                   │
│     ▼                                                                   │
│  4. Core-2 wird neuer Leader                                            │
│     │                                                                   │
│     ▼                                                                   │
│  5. Driver routet automatisch zu neuem Leader                           │
│     │                                                                   │
│     ▼                                                                   │
│  6. Core-1 rejoint als Follower (nach Recovery)                         │
│                                                                         │
│  Gesamtausfallzeit: < 30 Sekunden                                       │
│  Datenverlust: 0 (durch Raft Consensus)                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Qdrant Cluster Konfiguration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    QDRANT CLUSTER ARCHITEKTUR                            │
└─────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────────┐
                           │         ANIMUSFORGE CORE          │
                           │      (Qdrant Client)              │
                           └───────────────┬───────────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────────┐
                           │        QDRANT CLIENT              │
                           │   (Load Balanced Access)          │
                           └───────────────┬───────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │   QDRANT-1    │      │   QDRANT-2    │      │   QDRANT-3    │
           │   (Peer)      │◄────►│   (Peer)      │◄────►│   (Peer)      │
           │               │      │               │      │               │
           │  gRPC: 6334   │      │  gRPC: 6334   │      │  gRPC: 6334   │
           │  HTTP: 6333   │      │  HTTP: 6333   │      │  HTTP: 6333   │
           │               │      │               │      │               │
           │  Raft: 6335   │◄────►│  Raft: 6335   │◄────►│  Raft: 6335   │
           │               │      │               │      │               │
           │  Collections: │      │  Collections: │      │  Collections: │
           │  - personas   │      │  - personas   │      │  - personas   │
           │  - memories   │      │  - memories   │      │  - memories   │
           └───────────────┘      └───────────────┘      └───────────────┘

SHARDING STRATEGIE:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Collection: personas                                                   │
│  ├── Shard Count: 3                                                     │
│  ├── Replication Factor: 2                                              │
│  ├── Sharding Method: Auto-Sharding (by ID)                             │
│  └── Vector Size: 1536 (OpenAI Embeddings)                              │
│                                                                         │
│  Collection: memories                                                   │
│  ├── Shard Count: 6                                                     │
│  ├── Replication Factor: 2                                              │
│  ├── Sharding Method: Custom (by Persona ID)                            │
│  └── Vector Size: 1536                                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

KONFIGURATION:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  # config.yaml (Qdrant Cluster)                                         │
│                                                                         │
│  log_level: INFO                                                        │
│                                                                         │
│  storage:                                                               │
│    storage_path: ./storage                                              │
│    snapshots_path: ./snapshots                                          │
│    on_disk_payload: true                                                │
│                                                                         │
│  cluster:                                                               │
│    enabled: true                                                        │
│    p2p:                                                                 │
│      port: 6335                                                         │
│    consensus:                                                           │
│      tick_period_ms: 100                                                │
│                                                                         │
│  service:                                                               │
│    grpc_port: 6334                                                      │
│    http_port: 6333                                                      │
│                                                                         │
│  telemetry_disabled: true                                               │
│                                                                         │
└───────────────────────────────────────────────���─────────────────────────┘

BACKUP STRATEGIE:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Automatische Snapshots:                                                │
│  ├── Intervall: Alle 6 Stunden                                          │
│  ├── Retention: 7 Tage                                                  │
│  ├── Ziel: S3-kompatibler Object Storage                                │
│  └── Rücksicherung: < 30 Minuten                                        │
│                                                                         │
│  Backup-Command:                                                        │
│  curl -X POST "http://qdrant:6333/collections/personas/snapshots"      │
│                                                                         │
│  Restore-Command:                                                       │
│  curl -X PUT "http://qdrant:6333/collections/personas/snapshots/upload"\
│       -F "snapshot=@backup.tar"                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Redis Sentinel Konfiguration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    REDIS SENTINEL ARCHITEKTUR                            │
└─────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────┐
                    │            SENTINEL CLUSTER             │
                    │                                         │
                    │  ┌─────────┐  ┌─────────┐  ┌─────────┐│
                    │  │Sentinel1│  │Sentinel2│  │Sentinel3││
                    │  │ :26379  │  │ :26379  │  │ :26379  ││
                    │  └────┬────┘  └────┬────┘  └────┬────┘│
                    │       │            │            │      │
                    │       └────────────┼────────────┘      │
                    │                    │                   │
                    └────────────────────┼───────────────────┘
                                         │
                                         │ Monitoring
                                         │ & Failover
                                         ▼
           ┌───────────────────────────────────────────────────────┐
           │                   REDIS INSTANCES                      │
           │                                                        │
           │    ┌───────────────┐          ┌───────────────┐       │
           │    │    MASTER     │──────────▶│    REPLICA    │       │
           │    │   redis-m1    │  Sync    │   redis-r1    │       │
           │    │   Port: 6379  │          │   Port: 6379  │       │
           │    │               │          │               │       │
           │    │  Memory: 4GB  │          │  Memory: 4GB  │       │
           │    └───────────────┘          └───────────────┘       │
           │                                                        │
           └───────────────────────────────────────────────────────┘

SENTINEL KONFIGURATION:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  # sentinel.conf                                                        │
│                                                                         │
│  port 26379                                                             │
│  sentinel monitor animusforge redis-m1 6379 2                           │
│  sentinel down-after-milliseconds animusforge 5000                      │
│  sentinel failover-timeout animusforge 60000                            │
│  sentinel parallel-syncs animusforge 1                                  │
│                                                                         │
│  # Authentifizierung                                                    │
│  sentinel auth-pass animusforge ${REDIS_PASSWORD}                       │
│                                                                         │
└───────────────────────────────────────────��─────────────────────────────┘

REDIS MASTER KONFIGURATION:
┌─────────────────────────────────────────────���───────────────────────────┐
│                                                                         │
│  # redis.conf (Master)                                                  │
│                                                                         │
│  bind 0.0.0.0                                                           │
│  port 6379                                                              │
│  requirepass ${REDIS_PASSWORD}                                          │
│                                                                         │
│  # Persistence                                                          │
│  appendonly yes                                                         │
│  appendfsync everysec                                                   │
│  save 900 1                                                             │
│  save 300 10                                                            │
│  save 60 10000                                                          │
│                                                                         │
│  # Memory                                                               │
│  maxmemory 4gb                                                          │
│  maxmemory-policy allkeys-lru                                           │
│                                                                         │
│  # Replication                                                          │
│  replica-serve-stale-data yes                                           │
│  replica-read-only yes                                                  │
│                                                                         │
└───────────────────────────────────────────��─────────────────────────────┘

FAILOVER SZENARIO:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  1. Master (redis-m1) fällt aus                                        │
│     │                                                                   │
│     ▼                                                                   │
│  2. Sentinel-Cluster erkennt Ausfall (5s timeout)                       │
│     │                                                                   │
│     ▼                                                                   │
│  3. Sentinel-Wahl: Neuer Leader Sentinel                                │
│     │                                                                   │
│     ▼                                                                   │
│  4. Replica (redis-r1) wird zum Master promoted                         │
│     │                                                                   │
│     ▼                                                                   │
│  5. Clients werden über neuen Master informiert                         │
│     │                                                                   │
│     ▼                                                                   │
│  6. Alter Master rejoint als Replica (nach Recovery)                    │
│                                                                         │
│  Gesamtausfallzeit: < 10 Sekunden                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Kill-Switch Mechanismen

### 5.1 3-Level Architektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    KILL-SWITCH 3-LEVEL ARCHITEKTUR                       │
└─────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────────┐
                           │       KILL-SWITCH CONTROLLER      │
                           │      (Zentrale Entscheidung)      │
                           └───────────────┬───────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │   LEVEL 1     │      │   LEVEL 2     │      │   LEVEL 3     │
           │   SOFT STOP   │      │   HARD STOP   │      │  EMERGENCY    │
           │               │      │               │      │               │
           │   🟡 WARNUNG  │      │   🟠 KRITISCH │      │   🔴 NOTFALL  │
           └───────┬───────┘      └───────┬───────┘      └───────┬───────┘
                   │                      │                      │
                   ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │  GRACEFUL     │      │  IMMEDIATE    │      │  FORCE KILL   │
           │  SHUTDOWN     │      │  STOP         │      │               │
           │               │      │               │      │               │
           │ State: Save   │      │ State: Dump   │      │ State: Lost   │
           │ Recovery:Auto │      │ Recovery:Man  │      │ Recovery:Full │
           │ Alert: Info   │      │ Alert: Warn   │      │ Alert: Crit   │
           └───────────────┘      └───────────────┘      └───────────────┘

```

### 5.2 Level 1: Soft Stop (Graceful)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LEVEL 1: SOFT STOP                                    │
└─────────────────────────────────────────────────────────────────────────┘

TRIGGER:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  │ Trigger                    │ Threshold      │ Check Intervall       │
│  ├────────────────────────────┼────────────────┼───────────────────────│
│  │ Max Iterations             │ > 100          │ Jede Iteration        │
│  │ Runtime Timeout            │ > 300s         │ Jede 1s               │
│  │ User Request               │ Manuell        │ Sofort                │
│  │ Goal Achieved              │ Score = 1.0    │ Jede Iteration        │
│  │ Low Priority Task Complete │ Task Done      │ Jede Iteration        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

AKTIONEN:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  PHASE 1: SIGNAL (Sofort)                                               │
│  ├── Setze Persona-State = "STOPPING"                                   │
│  ├── Sende SoftStop Event an alle Listener                              │
│  └── Logge Stop-Reason                                                  │
│                                                                         │
│  PHASE 2: COMPLETION (< 5s)                                             │
│  ├── Beende aktuelle Iteration graceful                                 │
│  ├── Speichere partial Results                                          │
│  └── Schließe offene Connections                                        │
│                                                                         │
│  PHASE 3: STATE PERSIST (< 2s)                                          │
│  ├── Speichere kompletten Persona-State                                 │
│  ├── Update Memory (Episodic + Semantic)                                │
│  └── Speichere Checkpoint                                               │
│                                                                         │
│  PHASE 4: CLEANUP (< 1s)                                                │
│  ├── Release Resources                                                  │
│  ├── Update Metrics                                                     │
│  └── Setze Persona-State = "STOPPED"                                    │
│                                                                         │
│  PHASE 5: ALERT (< 1s)                                                  │
│  ├── Sende Info-Alert an Observability                                  │
│  ├── Update Dashboard                                                   │
│  └── Benachrichtige User (falls requested)                              │
│                                                                         │
│  GESAMTZEIT: < 10 Sekunden                                              │
│                                                                         │
└─────────────────��───────────────────────────────────────────────────────┘

RECOVERY:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Automatischer Restart MÖGLICH:                                         │
│  ├── State vollständig gespeichert                                      │
│  ├── Checkpoint verfügbar                                               │
│  ├── Memory konsistent                                                  │
│  └── Keine korrupten Daten                                              │
│                                                                         │
│  Recovery-Optionen:                                                     │
│  ├── AUTO_RESTART: Persona wird automatisch neu gestartet               │
│  ├── MANUAL_RESUME: User muss Restart initiieren                        │
│  └── DISCARD: Persona wird beendet, State bleibt erhalten               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

```

### 5.3 Level 2: Hard Stop (Immediate)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LEVEL 2: HARD STOP                                    │
└─────────────────────────────────────────────────────────────────────────┘

TRIGGER:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  │ Trigger                    │ Threshold        │ Check Intervall     │
│  ├────────────────────────────┼──────────────────┼─────────────────────│
│  │ Memory Usage               │ > 512MB          │ Jede 500ms          │
│  │ CPU Usage                  │ > 80% für 30s    │ Jede 1s             │
│  │ Token Limit                │ > 100,000        │ Jede Iteration      │
│  │ Consecutive Errors         │ > 3              │ Jede Iteration      │
│  │ Content Filter Violation   │ Severity >= 8    │ Sofort              │
│  │ Anomaly Score              │ > 0.8            │ Jede 5s             │
│  │ Tool Execution Timeout     │ > 60s            │ Jedes Tool          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

AKTIONEN:
┌───────────────────────────────────────────��─────────────────────────────┐
│                                                                         │
│  PHASE 1: INTERRUPT (Sofort)                                            │
│  ├── Unterbreche aktuelle Operation sofort                              │
│  ├── Setze Persona-State = "HARD_STOP"                                  │
│  └── Sende HardStop Event                                               │
│                                                                         │
│  PHASE 2: STATE DUMP (< 1s)                                             │
│  ├── Erzeuge Emergency State Dump                                       │
│  ├── Speichere in separater Collection                                  │
│  └── Markiere als "INCOMPLETE"                                          │
│                                                                         │
│  PHASE 3: RESOURCE CLEANUP (< 1s)                                       │
│  ├── Force-close alle Connections                                       │
│  ├── Release Memory sofort                                              │
│  └── Kill Child Processes                                               │
│                                                                         │
│  PHASE 4: ALERT (Sofort)                                                │
│  ├── Sende CRITICAL Alert                                               │
│  ├── Erzeuge Incident Report                                            │
│  └── Benachrichtige Ops-Team                                            │
│                                                                         │
│  GESAMTZEIT: < 3 Sekunden                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

RECOVERY:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Automatischer Restart NICHT MÖGLICH:                                   │
│  ├── State möglicherweise inkonsistent                                  │
│  ├── Partial Results nicht vertrauenswürdig                             │
│  └── Manuelle Prüfung erforderlich                                      │
│                                                                         │
│  Recovery-Prozess:                                                      │
│  1. Ops-Team prüft Incident Report                                      │
│  2. State Dump wird analysiert                                          │
│  3. Entscheidung:                                                       │
│     ├── ROLLBACK: Letzter stabiler State wird wiederhergestellt         │
│     ├── RESTART: Persona wird komplett neu gestartet                    │
│     └── DISCARD: Persona wird permanent beendet                         │
│  4. Root Cause wird dokumentiert                                        │
│  5. Ggf. neue Rules werden erstellt                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

```

### 5.4 Level 3: Emergency Kill (Force)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LEVEL 3: EMERGENCY KILL                               │
└─────────────────────────────────────────────────────────────────────────┘

TRIGGER:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  │ Trigger                    │ Threshold        │ Check Intervall     │
│  ├────────────────────────────┼──────────────────┼─────────────────────│
│  │ Security Violation         │ Detected         │ Sofort              │
│  │ Anomalous Behavior         │ Score > 0.95     │ Jede 1s             │
│  │ Potential Data Exfiltration│ Detected         │ Sofort              │
│  │ System Instability Risk    │ Critical         │ Sofort              │
│  │ Unauthorized Access        │ Detected         │ Sofort              │
│  │ Malicious Pattern          │ Detected         │ Sofort              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

AKTIONEN:
┌───────────────────────────────────────────��─────────────────────────────┐
│                                                                         │
│  PHASE 1: TERMINATE (Sofort, < 100ms)                                   │
│  ├── SIGKILL an Persona-Prozess                                         │
│  ├── Keine State-Persistierung                                          │
│  ├── Keine Graceful Operations                                          │
│  └── Prozess sofort beendet                                             │
│                                                                         │
│  PHASE 2: ISOLATE (Sofort)                                              │
│  ├── Blockiere alle Netzwerk-Zugriffe                                   │
│  ├── Isoliere Persona-Daten                                             │
│  └── Sperre zugehörige User-Account (falls nötig)                       │
│                                                                         │
│  PHASE 3: INVESTIGATE (< 1h)                                            │
│  ├── Erzeuge vollständigen Incident Report                              │
│  ├── Sammle alle verfügbaren Logs                                       │
│  ├── Analysiere Verhaltensmuster                                        │
│  └── Identifiziere Root Cause                                           │
│                                                                         │
│  PHASE 4: RESPONSE (< 24h)                                              │
│  ├── Security-Team Review                                               │
│  ├── Ggf. Patch/Hotfix implementieren                                   │
│  ├── System-weite Rules aktualisieren                                   │
│  └── Post-Mortem dokumentieren                                          │
│                                                                         │
└─────────────────────────────────────────────���───────────────────────────┘

RECOVERY:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  KEIN AUTOMATISCHER RESTART:                                            │
│  ├── Persona wird permanent deaktiviert                                 │
│  ├── State wird für Forensik aufbewahrt                                 │
│  └── User-Benachrichtigung erfolgt manuell                              │
│                                                                         │
│  Post-Incident:                                                         │
│  ├── Vollständige Security-Audit                                        │
│  ├── System-Review                                                      │
│  ├── Ggf. andere Personas mit ähnlichen Patterns prüfen                 │
│  └── System-weite Präventionsmaßnahmen                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

```

### 5.5 Kill-Switch Implementierung

```python
# Kill-Switch Controller Implementierung

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Any, Awaitable
import asyncio
import signal
import psutil

class KillLevel(Enum):
    SOFT = "soft"           # Graceful shutdown
    HARD = "hard"           # Immediate stop with state dump
    EMERGENCY = "emergency" # Force kill

class KillTrigger(Enum):
    MAX_ITERATIONS = "max_iterations"
    RUNTIME_TIMEOUT = "runtime_timeout"
    USER_REQUEST = "user_request"
    MEMORY_LIMIT = "memory_limit"
    CPU_LIMIT = "cpu_limit"
    TOKEN_LIMIT = "token_limit"
    CONSECUTIVE_ERRORS = "consecutive_errors"
    CONTENT_FILTER = "content_filter"
    ANOMALY_DETECTED = "anomaly_detected"
    SECURITY_VIOLATION = "security_violation"

@dataclass
class KillEvent:
    """Repräsentiert ein Kill-Event"""
    level: KillLevel
    trigger: KillTrigger
    persona_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    reason: str = ""
    metrics: dict = field(default_factory=dict)
    recovery_hint: str = ""

@dataclass
class KillSwitchConfig:
    """Konfiguration für Kill-Switch Limits"""
    
    # Level 1 Triggers
    max_iterations: int = 100
    max_runtime_seconds: float = 300.0
    
    # Level 2 Triggers
    max_memory_mb: int = 512
    max_cpu_percent: float = 80.0
    max_tokens: int = 100_000
    max_consecutive_errors: int = 3
    anomaly_threshold: float = 0.8
    
    # Level 3 Triggers
    security_violation_threshold: float = 0.95
    
    # Timeouts
    soft_stop_timeout_seconds: float = 10.0
    hard_stop_timeout_seconds: float = 3.0

class KillSwitchController:
    """Zentraler Kill-Switch Controller"""
    
    def __init__(
        self,
        persona_id: str,
        config: KillSwitchConfig = None,
        on_soft_stop: Callable[[KillEvent], Awaitable[None]] = None,
        on_hard_stop: Callable[[KillEvent], Awaitable[None]] = None,
        on_emergency_kill: Callable[[KillEvent], Awaitable[None]] = None
    ):
        self.persona_id = persona_id
        self.config = config or KillSwitchConfig()
        
        # Callbacks
        self.on_soft_stop = on_soft_stop
        self.on_hard_stop = on_hard_stop
        self.on_emergency_kill = on_emergency_kill
        
        # Runtime State
        self.current_iteration: int = 0
        self.start_time: datetime = datetime.now()
        self.tokens_used: int = 0
        self.consecutive_errors: int = 0
        self.is_running: bool = True
        
        # Process Reference
        self._process: psutil.Process | None = None
    
    async def check(self) -> KillEvent | None:
        """Prüft alle Kill-Conditions und gibt höchsten Level zurück"""
        
        triggers = []
        
        # Level 1 Checks
        if self.current_iteration > self.config.max_iterations:
            triggers.append((KillLevel.SOFT, KillTrigger.MAX_ITERATIONS))
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > self.config.max_runtime_seconds:
            triggers.append((KillLevel.SOFT, KillTrigger.RUNTIME_TIMEOUT))
        
        # Level 2 Checks
        memory_mb = self._get_memory_usage()
        if memory_mb > self.config.max_memory_mb:
            triggers.append((KillLevel.HARD, KillTrigger.MEMORY_LIMIT))
        
        cpu_percent = self._get_cpu_usage()
        if cpu_percent > self.config.max_cpu_percent:
            triggers.append((KillLevel.HARD, KillTrigger.CPU_LIMIT))
        
        if self.tokens_used > self.config.max_tokens:
            triggers.append((KillLevel.HARD, KillTrigger.TOKEN_LIMIT))
        
        if self.consecutive_errors > self.config.max_consecutive_errors:
            triggers.append((KillLevel.HARD, KillTrigger.CONSECUTIVE_ERRORS))
        
        # Anomaly Check (placeholder for ML-based detection)
        anomaly_score = await self._check_anomaly()
        if anomaly_score > self.config.anomaly_threshold:
            if anomaly_score > self.config.security_violation_threshold:
                triggers.append((KillLevel.EMERGENCY, KillTrigger.SECURITY_VIOLATION))
            else:
                triggers.append((KillLevel.HARD, KillTrigger.ANOMALY_DETECTED))
        
        # Return highest priority trigger
        if not triggers:
            return None
        
        # Priority: EMERGENCY > HARD > SOFT
        for level in [KillLevel.EMERGENCY, KillLevel.HARD, KillLevel.SOFT]:
            for trigger_level, trigger in triggers:
                if trigger_level == level:
                    return KillEvent(
                        level=level,
                        trigger=trigger,
                        persona_id=self.persona_id,
                        reason=self._generate_reason(trigger),
                        metrics={
                            "iteration": self.current_iteration,
                            "runtime_seconds": elapsed,
                            "memory_mb": memory_mb,
                            "cpu_percent": cpu_percent,
                            "tokens_used": self.tokens_used,
                            "consecutive_errors": self.consecutive_errors,
                            "anomaly_score": anomaly_score
                        }
                    )
        
        return None
    
    async def execute(self, event: KillEvent) -> None:
        """Führt Kill-Event aus"""
        
        self.is_running = False
        
        if event.level == KillLevel.SOFT:
            await self._execute_soft_stop(event)
        elif event.level == KillLevel.HARD:
            await self._execute_hard_stop(event)
        else:
            await self._execute_emergency_kill(event)
    
    async def _execute_soft_stop(self, event: KillEvent) -> None:
        """Führt Graceful Shutdown aus"""
        
        try:
            # Phase 1: Signal
            # (State wird in Callback gesetzt)
            
            # Phase 2: Wait for completion with timeout
            await asyncio.wait_for(
                self._graceful_completion(),
                timeout=self.config.soft_stop_timeout_seconds - 2
            )
            
            # Phase 3: State Persist
            await self._persist_state(event)
            
            # Phase 4: Callback
            if self.on_soft_stop:
                await self.on_soft_stop(event)
                
        except asyncio.TimeoutError:
            # Fallback zu Hard Stop
            await self._execute_hard_stop(KillEvent(
                level=KillLevel.HARD,
                trigger=KillTrigger.RUNTIME_TIMEOUT,
                persona_id=self.persona_id,
                reason="Soft stop timeout exceeded"
            ))
    
    async def _execute_hard_stop(self, event: KillEvent) -> None:
        """Führt Immediate Stop aus"""
        
        # Phase 1: Interrupt
        # (Sofortige Unterbrechnung)
        
        # Phase 2: State Dump
        await self._dump_state(event)
        
        # Phase 3: Resource Cleanup
        await self._force_cleanup()
        
        # Phase 4: Callback
        if self.on_hard_stop:
            await self.on_hard_stop(event)
    
    async def _execute_emergency_kill(self, event: KillEvent) -> None:
        """Führt Force Kill aus"""
        
        # Phase 1: Terminate
        if self._process:
            self._process.kill()
        
        # Phase 2: Isolate
        # (Network blocking, etc.)
        
        # Phase 3: Callback
        if self.on_emergency_kill:
            await self.on_emergency_kill(event)
    
    def _get_memory_usage(self) -> float:
        """Ermittelt Memory-Usage in MB"""
        if self._process is None:
            self._process = psutil.Process()
        return self._process.memory_info().rss / (1024 * 1024)
    
    def _get_cpu_usage(self) -> float:
        """Ermittelt CPU-Usage in Prozent"""
        if self._process is None:
            self._process = psutil.Process()
        return self._process.cpu_percent(interval=0.1)
    
    async def _check_anomaly(self) -> float:
        """Prüft auf anomales Verhalten (ML-basiert)"""
        # Placeholder für ML-basierte Anomaly Detection
        return 0.0
    
    async def _graceful_completion(self) -> None:
        """Wartet auf graceful Completion"""
        await asyncio.sleep(0.1)
    
    async def _persist_state(self, event: KillEvent) -> None:
        """Persistiert State bei Soft Stop"""
        # Implementierung mit Memory Store
        pass
    
    async def _dump_state(self, event: KillEvent) -> None:
        """Erzeugt State Dump bei Hard Stop"""
        # Implementierung mit Emergency State Collection
        pass
    
    async def _force_cleanup(self) -> None:
        """Erzwingt Resource Cleanup"""
        # Implementierung
        pass
    
    def _generate_reason(self, trigger: KillTrigger) -> str:
        """Generiert lesbare Reason für Kill-Event"""
        reasons = {
            KillTrigger.MAX_ITERATIONS: f"Iteration limit exceeded ({self.current_iteration}/{self.config.max_iterations})",
            KillTrigger.RUNTIME_TIMEOUT: f"Runtime timeout exceeded",
            KillTrigger.MEMORY_LIMIT: f"Memory limit exceeded",
            KillTrigger.CPU_LIMIT: f"CPU limit exceeded",
            KillTrigger.TOKEN_LIMIT: f"Token limit exceeded ({self.tokens_used}/{self.config.max_tokens})",
            KillTrigger.CONSECUTIVE_ERRORS: f"Too many consecutive errors ({self.consecutive_errors})",
            KillTrigger.ANOMALY_DETECTED: "Anomalous behavior detected",
            KillTrigger.SECURITY_VIOLATION: "Security violation detected",
            KillTrigger.USER_REQUEST: "User requested stop",
            KillTrigger.CONTENT_FILTER: "Content filter violation",
        }
        return reasons.get(trigger, "Unknown trigger")
```

---

## 6. API Gateway Load Balancing

### 6.1 Kubernetes Deployment

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY KUBERNETES ARCHITEKTUR                    │
└─────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────────┐
                           │          EXTERNAL TRAFFIC         │
                           │     (Users, API Clients)          │
                           └───────────────┬───────────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────────┐
                           │     INGRESS CONTROLLER (NGINX)    │
                           │     - SSL Termination             │
                           │     - Rate Limiting               │
                           │     - DDoS Protection             │
                           └───────────────┬───────────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────────┐
                           │      KUBERNETES SERVICE           │
                           │   (ClusterIP + LoadBalancer)      │
                           │   animusforge-api                 │
                           └───────────────┬───────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │   POD 1       │      │   POD 2       │      │   POD 3       │
           │  animusforge  │      │  animusforge  │      │  animusforge  │
           │               │      │               │      │               │
           │  FastAPI      │      │  FastAPI      │      │  FastAPI      │
           │  Uvicorn      │      │  Uvicorn      │      │  Uvicorn      │
           │               │      │               │      │               │
           │  Liveness: ✓  │      │  Liveness: ✓  │      │  Liveness: ✓  │
           │  Readiness: ✓ │      │  Readiness: ✓ │      │  Readiness: ✓ │
           └───────────────┘      └───────────────┘      └───────────────┘
                    │                      │                      │
                    └──────────────────────┼──────────────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────────┐
                           │      SHARED SERVICES              │
                           │  ├── Redis (Session State)        │
                           │  ├── Neo4j (Graph DB)             │
                           │  ├── Qdrant (Vector DB)           │
                           │  └── Prometheus (Metrics)         │
                           └───────────────────────────────────┘

```

### 6.2 Kubernetes Manifeste

```yaml
# api-deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: animusforge-api
  namespace: animusforge
  labels:
    app: animusforge-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: animusforge-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: animusforge-api
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: animusforge-api
                topologyKey: kubernetes.io/hostname
      containers:
        - name: api
          image: animusforge/api:latest
          ports:
            - containerPort: 8000
              name: http
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: animusforge-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: animusforge-secrets
                  key: redis-url
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]

---
apiVersion: v1
kind: Service
metadata:
  name: animusforge-api
  namespace: animusforge
spec:
  type: ClusterIP
  selector:
    app: animusforge-api
  ports:
    - port: 80
      targetPort: 8000
      name: http

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: animusforge-api-hpa
  namespace: animusforge
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: animusforge-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 2
          periodSeconds: 15
      selectPolicy: Max
```

### 6.3 Ingress Konfiguration

```yaml
# ingress.yaml

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: animusforge-ingress
  namespace: animusforge
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    # WebSocket Support
    nginx.ingress.kubernetes.io/websocket-services: animusforge-api
    nginx.ingress.kubernetes.io/connection-proxy-header: "upgrade"
spec:
  tls:
    - hosts:
        - api.animusforge.ai
      secretName: animusforge-tls
  rules:
    - host: api.animusforge.ai
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: animusforge-api
                port:
                  number: 80
```

---

## 7. Budget Management System

### 7.1 Architektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BUDGET MANAGEMENT ARCHITEKTUR                         │
└─────────────────────────────────────────────────────────────────────────┘

                           ┌───────────────────────────────────┐
                           │         REQUEST INCOMING          │
                           └───────────────┬───────────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────────┐
                           │       BUDGET GATEWAY MIDDLEWARE   │
                           │                                   │
                           │  ┌─────────────────────────────┐ │
                           │  │     BUDGET CHECK ENGINE     │ │
                           │  │                             │ │
                           │  │  1. Global Budget Check     │ │
                           │  │  2. User Budget Check       │ │
                           │  │  3. Persona Budget Check    │ │
                           │  │  4. Predictive Cost Check   │ │
                           │  │                             │ │
                           │  └─────────────────────────────┘ │
                           │                                   │
                           └───────────────┬───────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
           ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
           │   ALLOWED     │      │   THROTTLED   │      │   DENIED      │
           │               │      │               │      │               │
           │ Request       │      │ Request       │      │ 429 Response  │
           │ Proceeds      │      │ Delayed       │      │               │
           └───────┬───────┘      └───────────────┘      └───────────────┘
                   │
                   ▼
           ┌───────────────────────────────────────────────────────┐
           │                 BUDGET TRACKER                         │
           │                                                        │
           │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
           │  │   REDIS     │  │  POSTGRES   │  │ PROMETHEUS  │   │
           │  │  (Realtime) │  │  (Persist)  │  │  (Metrics)  │   │
           │  │             │  │             │  │             │   │
           │  │  Counters   │  │  Daily      │  │  Cost       │   │
           │  │  per Min/Hr │  │  Aggregates │  │  Gauges     │   │
           │  └─────────────┘  └─────────────┘  └─────────────┘   │
           │                                                        │
           └───────────────────────────────────────────────────────┘

```

### 7.2 Budget-Tiers

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BUDGET TIERS KONFIGURATION                            │
└─────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────��─────────────────────────────┐
│                                                                         │
│  TIER: FREE                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Preis: $0 / Monat                                               │   │
│  │                                                                  │   │
│  │  Limits:                                                         │   │
│  │  ├── Max Personas: 3                                            │   │
│  │  ├── Tokens pro Tag: 10,000                                     │   │
│  │  ├── Tokens pro Monat: 100,000                                  │   │
│  │  ├── Requests pro Minute: 10                                    │   │
│  │  └── Features: Basic                                            │   │
│  │                                                                  │   │
│  │  Kosten-Limit: $1 / Tag Hard-Cap                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  TIER: PRO                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Preis: $29 / Monat                                              │   │
│  │                                                                  │   │
│  │  Limits:                                                         │   │
│  │  ├── Max Personas: 20                                           │   │
│  │  ├── Tokens pro Tag: 100,000                                    │   │
│  │  ├── Tokens pro Monat: 1,000,000                                │   │
│  │  ├── Requests pro Minute: 60                                    │   │
│  │  └── Features: Basic + Evolution + Graph Memory                 │   │
│  │                                                                  │   │
│  │  Kosten-Limit: $10 / Tag Hard-Cap                               │   │
│  │  Inklusive: $20 API-Kredit / Monat                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  TIER: ENTERPRISE                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Preis: Custom (ab $299 / Monat)                                 │   │
│  │                                                                  │   │
│  │  Limits:                                                         │   │
│  │  ├── Max Personas: Unlimited                                    │   │
│  │  ├── Tokens pro Tag: Unlimited                                  │   │
│  │  ├── Tokens pro Monat: Custom                                   │   │
│  │  ├── Requests pro Minute: 1000                                  │   │
│  │  └── Features: Full + Priority Support + SLA                    │   │
│  │                                                                  │   │
│  │  Kosten-Limit: Custom (mit Alerts)                              │   │
│  │  Inklusive: Custom API-Kredit                                   │   │
│  │  SLA: 99.9% Uptime                                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

```

### 7.3 Budget Tracking Implementierung

```python
# Budget Management Implementierung

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import redis.asyncio as redis

class BudgetTier(Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

@dataclass
class BudgetLimits:
    """Budget-Limits für einen User"""
    tier: BudgetTier
    max_personas: int
    tokens_per_day: int
    tokens_per_month: int
    requests_per_minute: int
    cost_cap_per_day: float  # USD

@dataclass
class BudgetUsage:
    """Aktuelle Budget-Nutzung"""
    user_id: str
    period_start: datetime
    tokens_used_today: int
    tokens_used_month: int
    cost_today: float
    cost_month: float
    requests_last_minute: int

# Tier-Konfiguration
TIER_LIMITS: dict[BudgetTier, BudgetLimits] = {
    BudgetTier.FREE: BudgetLimits(
        tier=BudgetTier.FREE,
        max_personas=3,
        tokens_per_day=10_000,
        tokens_per_month=100_000,
        requests_per_minute=10,
        cost_cap_per_day=1.0
    ),
    BudgetTier.PRO: BudgetLimits(
        tier=BudgetTier.PRO,
        max_personas=20,
        tokens_per_day=100_000,
        tokens_per_month=1_000_000,
        requests_per_minute=60,
        cost_cap_per_day=10.0
    ),
    BudgetTier.ENTERPRISE: BudgetLimits(
        tier=BudgetTier.ENTERPRISE,
        max_personas=-1,  # Unlimited
        tokens_per_day=-1,
        tokens_per_month=-1,
        requests_per_minute=1000,
        cost_cap_per_day=1000.0
    )
}

class BudgetManager:
    """Zentrales Budget-Management"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.tier_limits = TIER_LIMITS
    
    async def check_budget(
        self,
        user_id: str,
        tier: BudgetTier,
        estimated_tokens: int = 0,
        estimated_cost: float = 0.0
    ) -> tuple[bool, str]:
        """
        Prüft ob Request innerhalb des Budgets liegt.
        
        Returns:
            (allowed: bool, reason: str)
        """
        
        limits = self.tier_limits[tier]
        usage = await self._get_usage(user_id)
        
        # Rate Limit Check
        if usage.requests_last_minute >= limits.requests_per_minute:
            return False, f"Rate limit exceeded: {limits.requests_per_minute} req/min"
        
        # Token Limit Check (Daily)
        if limits.tokens_per_day > 0:
            if usage.tokens_used_today + estimated_tokens > limits.tokens_per_day:
                return False, f"Daily token limit exceeded: {limits.tokens_per_day}"
        
        # Token Limit Check (Monthly)
        if limits.tokens_per_month > 0:
            if usage.tokens_used_month + estimated_tokens > limits.tokens_per_month:
                return False, f"Monthly token limit exceeded: {limits.tokens_per_month}"
        
        # Cost Cap Check
        if usage.cost_today + estimated_cost > limits.cost_cap_per_day:
            return False, f"Daily cost cap exceeded: ${limits.cost_cap_per_day}"
        
        return True, "OK"
    
    async def record_usage(
        self,
        user_id: str,
        tokens_input: int,
        tokens_output: int,
        cost: float,
        provider: str
    ) -> None:
        """Zeichnet Usage nach Request-Ausführung auf"""
        
        total_tokens = tokens_input + tokens_output
        now = datetime.now()
        
        # Redis Keys
        key_day = f"budget:{user_id}:day:{now.strftime('%Y-%m-%d')}"
        key_month = f"budget:{user_id}:month:{now.strftime('%Y-%m')}"
        key_minute = f"budget:{user_id}:minute:{now.strftime('%Y-%m-%d-%H-%M')}"
        
        # Atomare Increments
        pipe = self.redis.pipeline()
        
        # Daily counters
        pipe.incrby(f"{key_day}:tokens", total_tokens)
        pipe.incrbyfloat(f"{key_day}:cost", cost)
        pipe.expire(f"{key_day}:tokens", 86400 * 2)  # 2 days TTL
        pipe.expire(f"{key_day}:cost", 86400 * 2)
        
        # Monthly counters
        pipe.incrby(f"{key_month}:tokens", total_tokens)
        pipe.incrbyfloat(f"{key_month}:cost", cost)
        pipe.expire(f"{key_month}:tokens", 86400 * 35)  # 35 days TTL
        pipe.expire(f"{key_month}:cost", 86400 * 35)
        
        # Rate limit counter
        pipe.incr(f"{key_minute}:requests")
        pipe.expire(f"{key_minute}:requests", 120)  # 2 min TTL
        
        # Provider breakdown
        pipe.incrbyfloat(f"{key_day}:provider:{provider}:cost", cost)
        pipe.expire(f"{key_day}:provider:{provider}:cost", 86400 * 2)
        
        await pipe.execute()
    
    async def _get_usage(self, user_id: str) -> BudgetUsage:
        """Holt aktuelle Usage aus Redis"""
        
        now = datetime.now()
        key_day = f"budget:{user_id}:day:{now.strftime('%Y-%m-%d')}"
        key_month = f"budget:{user_id}:month:{now.strftime('%Y-%m')}"
        key_minute = f"budget:{user_id}:minute:{now.strftime('%Y-%m-%d-%H-%M')}"
        
        # Batch fetch
        values = await self.redis.mget([
            f"{key_day}:tokens",
            f"{key_day}:cost",
            f"{key_month}:tokens",
            f"{key_month}:cost",
            f"{key_minute}:requests"
        ])
        
        def parse_int(v) -> int:
            return int(v) if v else 0
        
        def parse_float(v) -> float:
            return float(v) if v else 0.0
        
        return BudgetUsage(
            user_id=user_id,
            period_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
            tokens_used_today=parse_int(values[0]),
            tokens_used_month=parse_int(values[2]),
            cost_today=parse_float(values[1]),
            cost_month=parse_float(values[3]),
            requests_last_minute=parse_int(values[4])
        )
    
    async def get_usage_report(self, user_id: str) -> dict:
        """Generiert Usage-Report für User"""
        
        usage = await self._get_usage(user_id)
        
        return {
            "user_id": user_id,
            "period": {
                "start": usage.period_start.isoformat(),
                "end": datetime.now().isoformat()
            },
            "daily": {
                "tokens_used": usage.tokens_used_today,
                "cost_usd": round(usage.cost_today, 4)
            },
            "monthly": {
                "tokens_used": usage.tokens_used_month,
                "cost_usd": round(usage.cost_month, 4)
            },
            "rate_limit": {
                "requests_last_minute": usage.requests_last_minute
            }
        }
```

---

## 8. Implementierungs-Roadmap

### 8.1 Sprint 1 (Kritisch - 15 Tage)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SPRINT 1: KRITISCHE INFRASTRUKTUR                     │
└───────────────────────────────────────────��─────────────────────────────┘

WOCHE 1: LLM Gateway + Kill-Switch
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Tag 1-2: LLM Gateway Basis                                             │
│  ├── Provider Abstraction Layer                                         │
│  ├── OpenAI + Anthropic Adapters                                        │
│  └── Request/Response Models                                            │
│                                                                         │
│  Tag 3-4: Multi-Provider Failover                                       │
│  ├── Circuit Breaker pro Provider                                       │
│  ├── Automatic Failover Logic                                           │
│  └── Health Check Integration                                           │
│                                                                         │
│  Tag 5: Kill-Switch Level 1 & 2                                         │
│  ├── Soft Stop Implementation                                           │
│  ├── Hard Stop Implementation                                           │
│  └── State Persistence                                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

WOCHE 2: Database HA + API Gateway
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Tag 6-8: Neo4j Cluster                                                 │
│  ├── 3 Core Nodes Setup                                                 │
│  ├── 2 Read Replicas                                                    │
│  └── Driver Configuration                                               │
│                                                                         │
│  Tag 9-10: Qdrant Cluster                                               │
│  ├── 3 Node Cluster                                                     │
│  ├── Sharding Configuration                                             │
│  └── Backup Automation                                                  │
│                                                                         │
│  Tag 11-12: API Gateway Load Balancing                                  │
│  ├── Kubernetes Deployment (3 Replicas)                                 │
│  ├── HPA Configuration                                                  │
│  └── Ingress + SSL                                                      │
│                                                                         │
│  Tag 13-15: Redis Sentinel + Integration                                │
│  ├── 3 Sentinel Setup                                                   │
│  ├── Master-Slave Replication                                           │
│  └── End-to-End Testing                                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

```

### 8.2 Sprint 2 (Hoch - 15 Tage)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SPRINT 2: BUDGET & MONITORING                         │
└─────────────────────────────────────────────────────────────────────────┘

WOCHE 3: Budget Management
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Tag 16-18: Budget System Basis                                         │
│  ├── Budget Gateway Middleware                                          │
│  ├── Redis-based Tracking                                               │
│  └── Tier Configuration                                                 │
│                                                                         │
│  Tag 19-21: Usage Dashboard                                             │
│  ├── Real-time Usage API                                                │
│  ├── Cost Breakdown                                                     │
│  └── Predictive Alerts                                                  │
│                                                                         │
│  Tag 22-23: Kill-Switch Level 3                                         │
│  ├── Emergency Kill Implementation                                      │
│  ├── Security Violation Detection                                       │
│  └── Incident Response Integration                                      │
│                                                                         │
└───────────────────────────────────────────��─────────────────────────────┘

WOCHE 4: Observability & Testing
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Tag 24-26: Enhanced Observability                                      │
│  ├── Prometheus Metrics Integration                                     │
│  ├── Grafana Dashboards                                                 │
│  └── Alert Rules                                                        │
│                                                                         │
│  Tag 27-28: Chaos Engineering                                           │
│  ├── Failure Injection Tests                                            │
│  ├── Failover Validation                                                │
│  └── Recovery Time Tests                                                │
│                                                                         │
│  Tag 29-30: Documentation & Handover                                    │
│  ├── Runbooks                                                           │
│  ├── Architecture Documentation                                         │
│  └── Team Training                                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

```

### 8.3 Erfolgsmetriken

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ERFOLGSMETRIKEN                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  VERFÜGBARKEIT (Availability)                                           │
│  ├── Ziel: 99.9% Uptime (max 8.76h Ausfall/Jahr)                        │
│  ├── Messung: Prometheus Uptime Metrics                                 │
│  └── Reporting: Monthly SLA Report                                      │
│                                                                         │
│  FAILOVER-ZEIT (Recovery Time)                                          │
│  ├── LLM Provider Failover: < 5s                                        │
│  ├── Database Failover: < 30s (Neo4j), < 10s (Redis)                    │
│  └── API Gateway Failover: < 5s                                         │
│                                                                         │
│  KOSTENKONTROLLE (Cost Management)                                      │
│  ├── Budget Overrun Alerts: 100% Coverage                               │
│  ├── Cost Prediction Accuracy: > 90%                                    │
│  └── Monthly Cost Variance: < 10%                                       │
│                                                                         │
│  KILL-SWITCH EFFEKTIVITÄT                                               │
│  ├── Soft Stop Success Rate: > 95%                                      │
│  ├── Hard Stop Response Time: < 3s                                      │
│  └── Emergency Kill Response Time: < 100ms                              │
│                                                                         │
│  SYSTEM-RESILIENZ                                                        │
│  ├── Single-Point-of-Failure: 0 (nach Sprint 1)                         │
│  ├── Circuit Breaker Activation Rate: < 1%                              │
│  └── Graceful Degradation Success: > 90%                                │
│                                                                         │
└───────────────────────────────────────────��─────────────────────────────┘

```

---

## 9. Metadaten

| Feld | Wert |
|------|------|
| **Dokument-Version** | 1.0.0 |
| **Erstellungsdatum** | 2026-03-05 |
| **Phase** | 9 - Fundamentale Infrastruktur-Resilienz |
| **Status** | ✅ Abgeschlossen |
| **Vorherige Phase** | Phase 8 - Gesamtbewertung |
| **Nächste Phase** | Phase 10 - Implementierung & Testing |

---

*Diese Dokumentation definiert die kritische Infrastruktur-Resilienz für AnimusForge und dient als Grundlage für die produktive Implementierung.*
