# KMFlow Architecture

## System Overview

```mermaid
graph TB
    subgraph "Frontend"
        UI[Next.js 14+<br/>React 18]
    end

    subgraph "API Gateway"
        API[FastAPI<br/>Port 8000]
        MW[Middleware Stack<br/>Auth / Rate Limit / Audit]
    end

    subgraph "Processing Services"
        EV[Evidence<br/>Ingestion]
        SEM[Semantic<br/>Engine]
        POV[POV<br/>Generator]
        TOM[TOM<br/>Alignment]
        RAG[RAG<br/>Copilot]
        CONF[Conformance<br/>Checker]
        MON[Monitoring<br/>Workers]
    end

    subgraph "Data Layer"
        PG[(PostgreSQL 15<br/>+ pgvector)]
        NEO[(Neo4j 5.x<br/>Knowledge Graph)]
        RED[(Redis 7<br/>Cache / Queues)]
    end

    UI --> API
    API --> MW
    MW --> EV & SEM & POV & TOM & RAG & CONF & MON
    EV & SEM & POV & TOM & RAG --> PG
    SEM --> NEO
    RAG --> NEO
    MON --> RED
    API --> RED
```

## Data Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API Gateway
    participant E as Evidence Service
    participant S as Semantic Engine
    participant P as POV Generator
    participant T as TOM Alignment
    participant DB as PostgreSQL
    participant G as Neo4j

    C->>A: Upload Evidence
    A->>E: Process & Extract Fragments
    E->>DB: Store Fragments + Embeddings
    E->>S: Build Semantic Relationships
    S->>G: Store Knowledge Graph
    C->>A: Generate POV
    A->>P: Consensus Algorithm
    P->>DB: Read Fragments
    P->>G: Read Relationships
    P-->>A: Process Model + Confidence Scores
    C->>A: Run TOM Alignment
    A->>T: Gap Analysis
    T->>DB: Read POV + TOM
    T-->>A: Gap Report + Recommendations
```

## Middleware Stack

Middleware executes in this order (outermost first):

1. **RateLimitMiddleware** - Per-IP request throttling (100/min)
2. **RequestIDMiddleware** - Unique X-Request-ID on every response
3. **AuditLoggingMiddleware** - Logs POST/PUT/PATCH/DELETE with user context
4. **SecurityHeadersMiddleware** - X-Frame-Options, CSP, etc.
5. **CORSMiddleware** - Cross-origin request handling

## Authentication & Authorization

- **JWT** (HS256) with 30-minute access tokens and 7-day refresh tokens
- **RBAC** with 5 roles: platform_admin, engagement_lead, process_analyst, evidence_reviewer, client_viewer
- **Permission-based** route protection via `require_permission()` dependency
- 17/18 route files protected (health endpoint intentionally public)

## Database Schema

- **31 models** across engagements, evidence, semantic, POV, TOM, regulatory, monitoring, patterns, simulation, conformance, and copilot domains
- **pgvector** for semantic similarity search on evidence fragment embeddings
- **Neo4j** for knowledge graph (entities, relationships, processes)
- **Redis** for rate limiting, WebSocket state, monitoring job queues

## Deployment

```mermaid
graph LR
    subgraph "Docker Compose"
        PG[PostgreSQL<br/>pgvector:pg15]
        NEO[Neo4j<br/>5-community]
        RED[Redis<br/>7-alpine]
        BE[Backend<br/>FastAPI]
        FE[Frontend<br/>Next.js]
    end

    PG --- BE
    NEO --- BE
    RED --- BE
    BE --- FE

    FE -->|:3000| USER((User))
    BE -->|:8000| USER
```

Production overlay (`docker-compose.prod.yml`) adds resource limits, log rotation, and security hardening.
