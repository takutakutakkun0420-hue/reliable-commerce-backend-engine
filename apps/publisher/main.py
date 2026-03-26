from __future__ import annotations

import json
import os
import time

import redis
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from packages.db.models import OutboxEvent
from packages.db.session import SessionLocal
from packages.domain.backoff import exponential_backoff_seconds, next_attempt_at
from packages.observability.logging_config import configure_logging, get_logger
from packages.observability.redis_metrics import incr

configure_logging(service_name="publisher")
log = get_logger("publisher")

REDIS_URL = os.environ["REDIS_URL"]
QUEUE_KEY = "queue:orders"


def try_publish_one(client: redis.Redis, session: Session) -> bool:
    now_clause = func.now()
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_(("pending", "publish_failed")),
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now_clause),
        )
        .order_by(OutboxEvent.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        session.rollback()
        return False

    payload = dict(row.payload)
    payload.setdefault("event_id", str(row.event_id))
    payload_bytes = json.dumps(payload).encode("utf-8")

    try:
        client.lpush(QUEUE_KEY, payload_bytes)
    except (redis.RedisError, OSError, TimeoutError) as exc:
        event_id = row.event_id
        session.rollback()
        try:
            with session.begin():
                fresh = session.get(OutboxEvent, event_id, with_for_update=True)
                if fresh is None:
                    return True
                fresh.attempt_count = int(fresh.attempt_count) + 1
                fresh.last_error = f"{type(exc).__name__}:{exc}"
                if fresh.attempt_count >= int(fresh.max_attempts):
                    fresh.status = "dead_letter"
                    fresh.next_attempt_at = None
                else:
                    fresh.status = "publish_failed"
                    fresh.next_attempt_at = next_attempt_at(fresh.attempt_count)
        except Exception:
            log.exception(
                "outbox_failure_persist_error",
                event_id=str(event_id),
                error_type=type(exc).__name__,
            )
            return True
        try:
            incr(client, "queue_publish_failure_total")
        except (redis.RedisError, OSError, TimeoutError) as r_exc:
            log.warning("redis_metrics_incr_failed", error_type=type(r_exc).__name__)
        log.warning(
            "outbox_publish_failed",
            event_id=str(event_id),
            entity_id=str(row.order_id),
            status=fresh.status,
            error_type=type(exc).__name__,
            attempt_count=fresh.attempt_count,
        )
        return True

    row.status = "published"
    row.last_error = None
    row.next_attempt_at = None
    session.commit()
    try:
        incr(client, "queue_publish_success_total")
    except (redis.RedisError, OSError, TimeoutError) as r_exc:
        log.warning("redis_metrics_incr_failed", error_type=type(r_exc).__name__)
    log.info(
        "outbox_published",
        event_id=str(row.event_id),
        entity_id=str(row.order_id),
        status="published",
    )
    return True


def run_forever() -> None:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=False, socket_timeout=30.0)
    while True:
        session = SessionLocal()
        try:
            try_publish_one(client, session)
        except Exception:
            if session.in_transaction():
                session.rollback()
            log.exception("publisher_cycle_error")
            time.sleep(min(300.0, exponential_backoff_seconds(3)))
        finally:
            session.close()
        time.sleep(0.05)


if __name__ == "__main__":
    run_forever()
