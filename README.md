
#Recording
.mp4 file
https://drive.google.com/file/d/1zTX27m4TQb6V6nlXy1D2SFdO8xMmHsd4/view?usp=sharing

ppt
https://docs.google.com/presentation/d/1a_UO9MDtQ3wNvRrwYBM_RbfVYhJJ6hxT/edit?usp=sharing&ouid=103351684874788865524&rtpof=true&sd=true

# MediShield — AI-Powered Insurance Document Processing

MediShield automatically classifies, verifies, and adjudicates health-insurance
documents using an LLM-powered multi-agent pipeline built on **LangGraph** and
**OpenAI GPT-4o**.  A Next.js dashboard provides real-time case tracking and a
manual review queue for escalated decisions.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (Next.js 14)                      │
│  /dashboard   /cases/[id]   /review                         │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP  (NEXT_PUBLIC_API_URL)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI  :8000                              │
│  POST /cases/upload   GET /cases/   PATCH /cases/{id}/dec.  │
└───────┬─────────────────────────────────────────────────────┘
        │ task.delay()
        ▼
┌─────────────────────────────────────────────────────────────┐
│              Celery Worker  (pool=solo)                      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LangGraph Pipeline                      │   │
│  │                                                     │   │
│  │  [classifier]                                       │   │
│  │       │                                             │   │
│  │       ├──────────────┬──────────────┐              │   │
│  │   [kyc agent]  [claims agent]  [policy agent]      │   │
│  │       └──────────────┴──────────────┘              │   │
│  │                      │                             │   │
│  │               [fraud agent]                        │   │
│  │                      │                             │   │
│  │             [orchestrator]                         │   │
│  │         APPROVE / REJECT / ESCALATE                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

Infrastructure
  Redis      :6379   Celery broker + case metadata cache
  MinIO      :9000   Document object storage  (console :9001)
  PostgreSQL :5432   Cases schema (provisioned; ready for migration)
  ChromaDB   :8001   Policy-clause vector store
```

### Agent responsibilities

| Agent | Input | Output |
|---|---|---|
| **Classifier** | Raw bytes (B64) | `DocumentType`, confidence, routing hints |
| **KYC** | Extracted text + image | `kyc_passed`, flags, confidence |
| **Claims** | Extracted text + raw fields | `schema_valid`, `extracted_fields`, errors |
| **Policy** | CPT codes | `covered`, `coverage_percentage`, `policy_clause` |
| **Fraud** | Claim fields + history | `fraud_score`, `anomalies`, `risk_level` |
| **Orchestrator** | All agent outputs | Final `decision`, `reasons` |

### Decision rules

| Condition | Decision |
|---|---|
| KYC fails (unknown member / expired / tampered) | `REJECT` |
| Procedure not covered by policy | `REJECT` |
| Fraud score ≥ 0.30 | `ESCALATE` |
| All checks pass | `APPROVE` |

---

## 2. Prerequisites

| Tool | Minimum version | Install |
|---|---|---|
| **Docker Desktop** | 24+ | https://www.docker.com/products/docker-desktop |
| **Python** | 3.11+ | https://www.python.org/downloads/ |
| **Node.js** | 18+ | https://nodejs.org |
| **OpenAI API key** | — | https://platform.openai.com/api-keys |

---

## 3. Quick Start

### Step 1 — Clone and configure

```bash
git clone <repo-url>
cd medishield

# Create your environment file
cp .env.example .env
```

Open `.env` and set your OpenAI API key:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxx
```

All other defaults work out of the box.

### Step 2 — Start all services

```bash
docker compose up --build
```

Docker builds the backend and frontend images, then starts all seven services
in dependency order.  First build takes ~3–5 minutes; subsequent starts are
fast.  Wait until you see:

```
backend   | INFO:     Application startup complete.
worker    | [tasks]
worker    |   . medishield.process_document
```

### Step 3 — Open the UI

| URL | What you see |
|---|---|
| http://localhost:3000 | Case dashboard |
| http://localhost:3000/review | Escalated case queue |
| http://localhost:8000/docs | FastAPI Swagger UI |
| http://localhost:9001 | MinIO console (`minioadmin` / `minioadmin`) |

### Step 4 — Load sample data (optional)

Upload 3 synthetic demo documents via the API:

```bash
pip install requests
python scripts/seed_sample_cases.py
```

Or upload all 20 dataset documents from `/dataset`:

```bash
for f in dataset/*.png; do
  curl -s -X POST http://localhost:8000/cases/upload \
    -F "file=@$f" | python -m json.tool
done
```

### Stopping

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop and delete all data volumes
```

---

## 4. Environment Variables

Copy `.env.example` to `.env` and edit.  All variables have safe defaults
except `OPENAI_API_KEY`.

| Variable | Default | Required | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | — | **Yes** | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | No | Model used by all LLM agents |
| `REDIS_URL` | `redis://localhost:6379/0` | No | Celery broker + result backend |
| `MINIO_ENDPOINT` | `localhost:9000` | No | MinIO S3-compatible endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | No | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | No | MinIO secret key |
| `MINIO_BUCKET` | `medishield-documents` | No | Bucket for uploaded files |
| `MINIO_SECURE` | `false` | No | Enable HTTPS for MinIO |
| `POSTGRES_USER` | `medishield` | No | PostgreSQL user |
| `POSTGRES_PASSWORD` | `medishield` | No | PostgreSQL password |
| `POSTGRES_DB` | `medishield` | No | PostgreSQL database name |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | No | Backend URL (browser-side) |
| `CORS_ORIGINS` | `http://localhost:3000` | No | Comma-separated allowed origins |

---

## 5. Running the Test Suite

The test suite runs entirely without Docker — every external dependency
(OpenAI, Redis, MinIO, ChromaDB) is mocked.

```bash
cd backend
pip install -r requirements.txt
python -m pytest --tb=short -q
```

Expected output:

```
............................................................. [ 62%]
....................................                         [100%]
93 passed in 3.1s
```

### Test layout

```
tests/
├── conftest.py                  Shared fixtures (mock_client, make_tool_response)
├── test_upload.py               FastAPI endpoint smoke tests
├── unit/agents/
│   ├── test_classifier.py       33 tests — document type routing, confidence, content
│   ├── test_kyc.py              10 tests — pass, expired, tampered, member-not-found
│   ├── test_claims.py           12 tests — valid, missing fields, malformed codes
│   ├── test_policy.py           10 tests — covered, excluded, ChromaDB interaction
│   └── test_fraud.py            15 tests — clean, duplicate, outlier, high-frequency
└── integration/
    └── test_pipeline.py         3 end-to-end cases (approve, reject, escalate)
```

To run only a specific agent's tests:

```bash
python -m pytest tests/unit/agents/test_classifier.py -v
```

---

## 6. End-to-End Walkthrough

This section traces a single claim form from upload through to a final
decision visible in the UI.

### Document

`dataset/claim_form_001.png` — Jane Doe, office visit (CPT 99213), $450.00

### Step 1 — Submit

Upload via the dashboard **Upload Document** button, or with curl:

```bash
curl -X POST http://localhost:8000/cases/upload \
  -F "file=@dataset/claim_form_001.png" \
  | python -m json.tool
```

Response:

```json
{
  "case_id": "a1b2c3d4-...",
  "status": "PENDING",
  "file_name": "claim_form_001.png",
  "mime_type": "image/png",
  "created_at": "2024-05-14T10:00:00Z"
}
```

### Step 2 — Classify

The Celery worker picks up the task within seconds and calls the
**ClassifierAgent** with the document's base64 bytes.

GPT-4o calls the `classify_document` tool and returns:

```json
{ "document_type": "CLAIM_FORM", "confidence": 0.96, "routing_hints": ["contains_procedure_codes"] }
```

### Step 3 — Parallel agent fan-out

LangGraph fans out to three agents simultaneously:

- **KYC** — extracts `M001234`, matches member Jane Doe in the registry →
  `kyc_passed: true`
- **Claims** — extracts CPT `99213`, ICD-10 `J18.9`, amount `450.00`,
  all fields valid → `schema_valid: true`
- **Policy** — queries ChromaDB for CPT 99213, retrieves *Section 4.2:
  Office visits covered at 80%* → `covered: true, coverage_percentage: 0.80`

### Step 4 — Fraud check

The **FraudAgent** (rules-based, no LLM) checks:

- No duplicate claim in history ✓
- Amount $450 within 2σ of provider average ✓
- Provider NPI not high-frequency ✓

Result: `fraud_score: 0.05, risk_level: LOW`

### Step 5 — Decision

The **Orchestrator** applies the decision rules:

```
KYC passed      ✓
Policy covered  ✓  (80%)
Fraud score     0.05 < 0.30  ✓
→ APPROVE
```

Redis is updated: `status = APPROVED`.

### Step 6 — UI

The dashboard polls every 5 seconds.  The case row changes from
`PROCESSING` → **APPROVED** (green badge).

Click the case ID to open the detail view:

```
┌─────────────────────────────────────────────────────┐
│  APPROVED                                           │
│  KYC passed, covered at 80%, fraud score 0.05      │
├─────────────────────────────────────────────────────┤
│  Classifier   CLAIM_FORM   conf 0.96               │
│  KYC          Passed       conf 0.95               │
│  Claims       Valid        $450.00 · 99213          │
│  Policy       Covered      80% · Section 4.2        │
│  Fraud        Low          score 0.05               │
└─────────────────────────────────────────────────────┘
```

---

## Dataset

`/dataset` contains 20 synthetic PNG documents for testing and demo purposes.

| Category | Count | Expected decision |
|---|---|---|
| Valid claim forms | 5 | APPROVE |
| Valid ID documents | 4 | APPROVE |
| Discharge summaries | 3 | APPROVE |
| Prescriptions | 3 | APPROVE |
| Fraudulent / invalid | 3 | REJECT or ESCALATE |
| Ambiguous / unknown | 2 | ESCALATE |

`dataset/ground_truth.json` lists the expected `doc_type` and
`expected_decision` for each file — useful for automated accuracy evaluation.

Regenerate the dataset at any time:

```bash
python scripts/generate_dataset.py
```

---

## Project Structure

```
medishield/
├── backend/
│   ├── api/              FastAPI routers (cases, health)
│   ├── core/             Pydantic-settings configuration
│   ├── db/               CaseStore (Redis-backed)
│   ├── pipeline/
│   │   ├── agents/       classifier, kyc, claims, policy, fraud, orchestrator
│   │   ├── fixtures/     policy_chunks.json, members.json, claim_history.json
│   │   └── graph.py      LangGraph pipeline (fan-out / fan-in)
│   ├── shared/           Enums, Pydantic schemas (agent I/O, cases)
│   ├── storage/          MinIO client wrapper
│   ├── worker/           Celery app + process_document task
│   ├── tests/            93 unit + integration tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── dashboard/    Case list + upload button (polls every 5 s)
│   │   ├── cases/[id]/   Case detail — document viewer + 6 agent panels
│   │   └── review/       Escalated queue + manual override modal
│   ├── components/       Navbar, StatusBadge, AgentPanel, DecisionBanner, AuditLog
│   ├── lib/              Typed API client, TypeScript schemas
│   └── Dockerfile
├── infra/
│   └── init.sql          PostgreSQL schema (cases table + indexes)
├── dataset/              20 synthetic PNG documents + ground_truth.json
├── scripts/
│   ├── generate_dataset.py   Regenerate the /dataset images
│   └── seed_sample_cases.py  Upload 3 demo docs via the API
├── docker-compose.yml    All 7 services with health checks
├── .env.example          Environment variable template
└── README.md
```
