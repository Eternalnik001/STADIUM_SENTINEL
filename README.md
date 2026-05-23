# 🏟️ Stadium Sentinel

**Agentic Crowd Intelligence & Emergency Command Platform**

A real-time, multi-agent command platform that fuses turnstile telemetry, ticketing, CCTV density signals, and weather into a Gemini-powered agentic core. It predicts crowd bottlenecks 5–15 minutes ahead, auto-issues rerouting directives, and coordinates volunteer and security response — all with an immutable forensic audit trail.

[![Built with Gemini](https://img.shields.io/badge/AI-Gemini%202.0%20Flash-4285F4?logo=google)](https://cloud.google.com/vertex-ai)
[![Cloud Run](https://img.shields.io/badge/Deploy-Cloud%20Run-4285F4?logo=googlecloud)](https://cloud.google.com/run)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![PostGIS](https://img.shields.io/badge/DB-PostgreSQL%20%2B%20PostGIS-336791?logo=postgresql)](https://postgis.net)
[![Redis](https://img.shields.io/badge/Streams-Redis-DC382D?logo=redis)](https://redis.io)

---

## 🎯 Problem

Cricket stadiums hosting 50,000–130,000 fans rely on fragmented, manual crowd-management systems. When the wave hits, multiple organisations run multiple playbooks — and people die.

**June 4, 2025 — Bengaluru.** RCB's IPL victory celebration drew an estimated 2.5–5 lakh fans to Chinnaswamy Stadium (capacity 35,000). **11 dead from suffocation. 50+ injured.** Ambulances were trapped in the very crowd they were trying to reach. The Karnataka government's report to the High Court blamed the franchise for unilateral promotion without police consultation. The Chief Minister stated that authorities *"did not expect such a big crowd."*

The data was there. It just wasn't fused.

## 💡 Solution

Stadium Sentinel deploys autonomous AI agents that:

- **Predict** crowd bottlenecks 5–15 minutes ahead using live density + ticket-flow telemetry
- **Decide** rerouting actions through Gemini-powered ReAct loops with confidence gating
- **Push** directives in real-time to volunteer PWAs and the command console via WebSocket
- **Record** every agent decision in an immutable, hash-verified audit log

We don't ship dashboards. Dashboards inform. **Agents act.**

---

## 🏗️ System Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Turnstiles  │  │  CCTV Edge  │  │ Ticket App  │  │   Weather   │
│   (IoT)     │  │  (density)  │  │  (Paytm)    │  │ (Open-Meteo)│
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │
       └────────────────┴────────────────┴────────────────┘
                              │ HTTPS / mTLS
                              ▼
              ┌─────────────────────────────────┐
              │  Cloud Run: FastAPI Gateway     │  ← JWT, rate-limit, schema-validate
              └──────────────┬──────────────────┘
                             │ XADD
                             ▼
              ┌─────────────────────────────────┐
              │ Memorystore Redis (Streams)     │  ← stream:ingest, consumer groups
              └──────────────┬──────────────────┘
                             │ XREADGROUP
       ┌─────────────────────┼─────────────────────┐
       ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ CrowdFlowAgt │    │ ThreatAgent  │    │  EvacAgent   │
│ (Gemini 2.0) │    │ (Gemini 2.0) │    │ (Gemini 2.0) │
│   ReAct      │    │   ReAct      │    │   ReAct      │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
   ┌────────────────────┐       ┌──────────────────┐
   │ Cloud SQL Postgres │       │ Redis Pub/Sub    │
   │   + PostGIS        │       │ channel:dirctvs  │
   │ canonical state    │       └────────┬─────────┘
   └────────────────────┘                │
                                         ▼
                         ┌──────────────────────────┐
                         │ FastAPI WebSocket Hub    │
                         │ (zone-scoped, JWT-gated) │
                         └─────────────┬────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
   ┌──────────────┐          ┌──────────────┐           ┌──────────────┐
   │ Command      │          │ Volunteer    │           │ Fan App      │
   │ Console      │          │ PWA          │           │ (deep-link)  │
   └──────────────┘          └──────────────┘           └──────────────┘
```

### Architectural Justifications

| Layer | Choice | Rationale |
|---|---|---|
| **API Gateway** | FastAPI on Cloud Run | Async-native, autoscales to zero, Python ecosystem matches Vertex AI SDK |
| **Ingestion** | Redis Streams + Consumer Groups | Durability + replay + horizontal scaling at 50k events/sec for 10% of Kafka's ops cost |
| **State** | PostgreSQL 16 + PostGIS | Real polygon geometry for zones, `ST_DWithin` for spatial adjacency, ACID for forensic audit |
| **Agents** | Gemini 2.0 Flash | 5× faster, 10× cheaper than Pro. Sufficient for structured-output tool-calling |
| **Push** | Redis Pub/Sub → WebSocket | Sub-second fan-out; ~800ms p99 sensor-to-push latency |
| **Forensics** | Immutable `audit_log` table | Every agent decision hashed (SHA-256), timestamped, fully replayable |

---

## 🤖 The Agentic Core

### CrowdFlowAgent

**Trigger:** Density delta > 15% or ticket-scan rate spike on a zone

**Decision Logic:**
1. Utilization < 70% AND trend ≠ rising → `no_action`
2. Utilization ≥ 70% AND neighbour has spare capacity → `emit_directive` (selects lowest-utilization neighbour)
3. Utilization ≥ 90% AND no safe neighbour → `defer_to_human`
4. Confidence < 0.75 → defer to commander (safety gate)

**Output:** Structured `RoutingDirective` published to `channel:directives`

### ThreatAgent

**Trigger:** Anomaly score > 0.8 or sudden density spike > 50% within 60s

**Detects:** Pressure waves, panic flux, unauthorized zone breaches, rapid flow-rate fluctuations

**Output:** Structured `ThreatAlert` published to `channel:alerts`

### EvacAgent *(roadmap)*

**Trigger:** `Alert.severity == critical`

**Action:** Computes egress path via PostGIS shortest-path; issues counter-flow directives to clear ambulance corridors.

### Safety Rails

| Rail | Mechanism |
|---|---|
| **Structured Output Schema** | Gemini called with `response_schema`; model cannot return malformed JSON |
| **Confidence Gate** | Directives emitted only when `confidence ≥ 0.75`; below threshold → human-in-loop |
| **Rate Limiting** | Maximum 1 directive per zone per 30 seconds (prevents flapping) |
| **Kill Switch** | Single Redis flag `agents:enabled=false` halts all agent action atomically |
| **Forensic Audit** | Every decision (including errors) persisted to `audit_log` with input hash |
| **Fail-Closed** | On any invalid model output → defer to commander, never auto-act |

---

## 🚀 Getting Started

### Prerequisites
- Docker Desktop
- Python 3.11+
- `gcloud` CLI for deployment
- GCP project with Vertex AI enabled

### Local Development

```bash
# 1. Clone and configure
git clone <repo-url>
cd stadium-sentinel
cp .env.example .env
# Edit .env: set GCP_PROJECT, generate JWT_SECRET with: openssl rand -hex 32

# 2. Bring up infrastructure
docker-compose up -d db redis

# 3. Initialize database
alembic upgrade head
python scripts/seed.py

# 4. Start API and agent worker
docker-compose up -d --build api agent

# 5. Verify
curl http://localhost:8080/healthz                  # {"status":"ok"}
curl http://localhost:8080/v1/zones | jq            # 9 stadium zones
open http://localhost:8080/index.html               # Command console
```

---

## 🗂️ Project Structure

```
stadium-sentinel/
├── app/
│   ├── api/                    # FastAPI routers
│   │   ├── ingest.py           # IoT/CCTV/ticket ingestion → Redis Streams
│   │   ├── zones.py            # GeoJSON + live snapshots
│   │   ├── ws.py               # WebSocket hub (directives, alerts)
│   │   └── health.py           # Cloud Run readiness probe
│   ├── agents/                 # Autonomous decision-makers
│   │   ├── crowd_flow.py       # CrowdFlowAgent
│   │   ├── threat.py           # ThreatAgent
│   │   ├── tools.py            # PostGIS-backed agent tools
│   │   ├── llm.py              # Vertex AI Gemini wrapper
│   │   └── runner.py           # Redis Streams consumer (XREADGROUP)
│   ├── core/                   # Infrastructure primitives
│   │   ├── redis_client.py     # Singleton async Redis pool
│   │   ├── streams.py          # Typed XADD writer
│   │   ├── idempotency.py      # SETNX dedup (anti-replay)
│   │   ├── security.py         # JWT + bcrypt
│   │   └── pubsub.py           # Redis pub/sub publisher
│   ├── db/                     # Persistence layer
│   │   ├── models.py           # SQLAlchemy 2.0 + PostGIS types
│   │   ├── session.py          # Async pool, leak-safe
│   │   └── base.py
│   ├── schemas/                # Pydantic v2 contracts
│   │   ├── ingest.py           # IoT event schemas
│   │   ├── directive.py        # RoutingDirective + AgentDecision
│   │   └── alert.py            # ThreatAlert
│   ├── static/
│   │   └── index.html          # Command Console (Leaflet + WS)
│   ├── config.py               # pydantic-settings, fail-fast
│   └── main.py                 # FastAPI app + lifespan
├── migrations/                 # Alembic migrations (PostGIS-aware)
├── scripts/
│   └── seed.py                 # Stadium zones + demo users
├── docker-compose.yml
├── Dockerfile                  # Multi-stage, slim Cloud Run image
└── pyproject.toml
```

---

## 🛡️ Security Posture

| Threat Vector | Mitigation |
|---|---|
| Stolen JWT | 60-min TTL, refresh rotation, `jti` blacklist on logout |
| SQL injection | SQLAlchemy parameterized queries; no f-string SQL |
| Prompt injection | Tool outputs sanitized; system prompts pinned; no user-content in prompts |
| DDoS on ingest | slowapi per-IP rate-limit + Redis backpressure + Cloud Armor |
| Replay attacks | SETNX idempotency keys + future-timestamp rejection (`ts > now + 60s`) |
| PII leakage | No PII in Redis streams; opaque IDs only; PII hashed at rest |
| Insider threat | `audit_log` immutable (append-only role); RBAC enforced on mutations |
| **DPDP Act (India)** | **No biometrics. No facial recognition. Anonymous density only. 90-day retention.** |

---

## 📈 Scalability Targets

| Metric | Target | Mechanism |
|---|---|---|
| Concurrent ingest connections | 16,000 | Cloud Run @ concurrency=80, max-instances=200 |
| Events/sec sustained | 50,000 | Redis Streams + consumer groups (horizontal agent scaling) |
| Sensor → directive p99 latency | < 800ms | Hot path never touches Postgres; agents read Redis, write async |
| Cold start | < 2s | Slim Docker image (~120 MB), lazy Vertex SDK init |
| Cost per match (6h, IPL scale) | **~₹8,000 (US$95)** | Free-tier-friendly; Memorystore is the only fixed cost |

---

## 🌩️ Deployment

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=asia-south1

gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com

gcloud artifacts repositories create sentinel \
  --repository-format=docker --location=$REGION

gcloud builds submit \
  --tag $REGION-docker.pkg.dev/$PROJECT_ID/sentinel/api:latest \
  --timeout=15m .

gcloud run deploy stadium-sentinel \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/sentinel/api:latest \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=512Mi --cpu=1 \
  --min-instances=1 --max-instances=3 \
  --port=8080 \
  --env-vars-file=/tmp/sentinel-env.yaml
```

Compatible with free-tier managed services:
- **Neon** for Postgres + PostGIS
- **Upstash** for Redis (TLS-enabled)

---

## 🗺️ Roadmap

| Phase | Milestone |
|---|---|
| **Q1** | Pilot at Chinnaswamy — 3 IPL matches in observer mode + 1 active mode |
| **Q2** | Drone vision integration; BCCI certification; expand to Wankhede and Eden Gardens |
| **Q3** | Multi-event SaaS (concerts, marathons, Kumbh Mela); SOC 2 Type I |
| **Q4** | International expansion (cricket boards in AUS/ENG); LoRa mesh for cell-failure resilience |

---

## 📜 License

MIT — see `LICENSE`.

---

> *In memory of the eleven lives lost at Chinnaswamy Stadium on June 4, 2025.*
> *This is the system that should have been there.*
