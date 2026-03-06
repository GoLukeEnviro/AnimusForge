# 🎭 AnimusForge

**Self-Evolving Digital Persona Platform** - Enterprise-Grade AI Persona System

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                   │
├─────────────────────────────────────────────────────────┤
│  animus_core    │ animus_stage   │ animus_conscience    │
│  Soul Forge     │ Theater        │ Ethics Engine        │
├─────────────────────────────────────────────────────────┤
│  animus_memory  │ animus_tools   │ animus_ecosystem     │
│  Vector/Graph   │ MCP Layer      │ Evolution            │
├─────────────────────────────────────────────────────────┤
│  animus_resilience │ animus_observe                    │
│  Circuit Breaker   │ OpenTelemetry                     │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run API server
uvicorn src.animus_api.main:app --reload
```

## 📦 Modules

| Module | Purpose |
|--------|---------|
| `animus_core` | Persona Factory, Validation Pipeline |
| `animus_stage` | Agentic Loop Engine, Kill-Switch |
| `animus_memory` | Vector/Graph/Cache Gateway |
| `animus_conscience` | Ethics Engine (Gewissen 2.0) |
| `animus_resilience` | Circuit Breaker, Retry, Bulkhead |
| `animus_ecosystem` | Evolution Engine, Health Monitoring |
| `animus_tools` | MCP Layer, Sandbox Executor |
| `animus_observe` | Observability, Telemetry |
| `animus_api` | REST API Endpoints |

## 🧪 Testing

```bash
pytest tests/ --cov=src --cov-report=html
```

## 📊 Status

**Sprint 1** - Critical Infrastructure

- [ ] Multi-Provider LLM Gateway
- [ ] Kill-Switch System
- [ ] Sandboxing Infrastructure
- [ ] RBAC Architecture

---

*AnimusForge - Where Personas Come Alive* 🎭
