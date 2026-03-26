# Reliable Commerce Backend Engine

> A production-grade backend that guarantees no data loss and automatic recovery under system failure.

---

## What this system guarantees

* **No data loss under Redis failure**
  Orders are committed in PostgreSQL with a **transactional outbox**.
  Even if Redis is unavailable, no data is dropped — events are retried or safely moved to a terminal state.

* **Automatic recovery from partial failure**
  When Redis or workers recover, the system **automatically resumes processing** without manual intervention.

* **Idempotent request handling**
  All writes require an **Idempotency-Key**.

  * Same key + same payload → same response
  * Same key + different payload → **409 Conflict**

* **Observable by design**

  * Structured JSON logs (`structlog`)
  * Prometheus metrics (`/metrics`)
  * Health checks (`/healthz`, `/readyz`)

---

## Why this matters

This system is built for environments where **failure is inevitable**.

It guarantees:

* No lost orders
* No duplicate processing
* No silent failure
* Deterministic recovery behavior

This is critical for:

* **E-commerce platforms**
* **Payment systems**
* **Financial pipelines**
* **Event-driven architectures**

---

## Target Use Cases

This system can be directly used in:

* E-commerce order processing systems
* Payment and transaction pipelines
* Event-driven microservices
* Systems migrating from unreliable queue-based architectures

Ideal for:

* SaaS startups handling async workflows
* Fintech platforms requiring strict consistency
* Teams experiencing message loss or duplicate processing

---

## Architecture

```text
Client → API → DB (transaction)
                ↓
            Outbox
                ↓
         Publisher → Redis
                ↓
             Worker
                ↓
        External Systems
                ↓
               DB
```

---

### Key Design Principles

* No Redis usage in request path
* All state persisted in PostgreSQL
* Retry handled at data layer (not memory)
* Explicit terminal states (`completed`, `failed`, `dead_letter`)
* Failure is treated as a **first-class design concern**

---

## End-to-End Flow

### Order Creation

```
POST /orders → 202 Accepted
```

**Transaction includes:**

* orders
* order_items
* outbox_events
* async_jobs
* idempotency_records
* audit_logs

---

### Async Processing

1. Publisher reads `outbox_events`
2. Pushes to Redis queue
3. Worker consumes queue
4. Calls external connectors
5. Updates order state

---

### Recovery Behavior

```
Failure → Stored in DB → Retried → Completed or Dead Letter
```

---

## Failure Scenario Demo

### Redis Outage Test

```bash
docker compose stop redis

# Create order
POST /orders → status = pending

docker compose start redis

# System recovers automatically
GET /orders/{id} → completed
```

---

### What this proves

* Outbox pattern works
* Retry logic is correct
* No data loss
* Recovery is automatic
* System is production-safe

---

## Business Impact

* Prevents revenue loss from message broker failure
* Eliminates duplicate processing via idempotency
* Guarantees eventual consistency
* Reduces operational overhead (self-healing system)

---

## Components

### API

* FastAPI
* Idempotent endpoints
* No dependency on Redis for request handling

### Publisher

* Outbox relay (DB → Redis)
* Retry with exponential backoff
* Dead-letter handling

### Worker

* Async job execution
* Retry + failure classification
* Idempotent processing

### Scheduler / Watchdog

* Detects stuck jobs
* Requeues or fails safely
* Ensures no indefinite processing state

### Database

* PostgreSQL
* Fully durable state
* Single transaction per request

---

## How to run

```bash
docker compose up --build
```

---

## Quick Test

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test" \
  -d '{"items":[{"product_id":"sku-1","quantity":1}]}'
```

---

## Health & Metrics

```bash
GET /healthz   → liveness
GET /readyz    → dependency checks
GET /metrics   → Prometheus metrics
```

---

## Admin Recovery

### Retry Outbox

```
POST /admin/outbox/{event_id}/retry
```

### Retry Job

```
POST /admin/jobs/{job_id}/retry
```

---

## Failure Scenarios Covered

* Redis outage
* Worker crash
* Duplicate request
* External API timeout
* Validation failure
* Stuck job recovery

---

## Core Concept

> This system does not assume things will work.
> It guarantees correct behavior when they don’t.

---

## Summary

This is not a demo backend.

This is a **production-grade reliability system** that:

* survives failure
* recovers automatically
* guarantees data integrity

---

## Value Proposition

Most systems:

```
Work → Break → Manual fix
```

This system:

```
Work → Break → Recover automatically
```

---

## Final Note

This system was designed with one principle:

> "Design for failure, not for success."

---

## License / Usage

Production-ready reference implementation.
Can be used as a foundation for any system requiring **strong reliability guarantees**.

---
