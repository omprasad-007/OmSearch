"""
OM Search - Durable Unified Task Scheduler
Provides atomic leased claims, persistent priority queues, exponential backoff retries,
and lease-expiry recovery backed by PostgreSQL / SQLite.
"""
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.repositories.database import (
    get_db_manager,
    IngestionTask,
    TaskStatus,
    TaskPriorityClass,
)
from app.ingestion.policy import IngestionPolicyEngine

logger = logging.getLogger("om_ingestion.scheduler")


class DurableTaskScheduler:
    """
    Durable scheduler managing ingestion work units across sources.
    """

    def __init__(self, policy_engine: Optional[IngestionPolicyEngine] = None):
        self.db_mgr = get_db_manager()
        self.policy_engine = policy_engine or IngestionPolicyEngine()

    def submit_task(
        self,
        source_type: str,
        work_unit_id: str,
        priority_class: str = TaskPriorityClass.ROUTINE,
        base_priority: int = 0,
        estimated_cost: float = 1.0,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        max_attempts: int = 3,
    ) -> IngestionTask:
        """
        Durable task submission. Guarantees idempotency via idempotency_key.
        """
        key = idempotency_key or f"{source_type}:{work_unit_id}"
        db = self.db_mgr.get_session()
        try:
            # Check existing task
            existing = db.query(IngestionTask).filter(IngestionTask.idempotency_key == key).first()
            if existing:
                return existing

            now = datetime.now(timezone.utc)
            score = self.policy_engine.calculate_priority_score(
                priority_class=priority_class,
                base_priority=base_priority,
                age_minutes=0.0,
            )
            task_id = f"task_{uuid.uuid4().hex[:16]}"

            task = IngestionTask(
                task_id=task_id,
                source_type=source_type,
                work_unit_id=work_unit_id,
                priority_class=priority_class,
                priority_score=score,
                estimated_cost=estimated_cost,
                status=TaskStatus.PENDING,
                attempt_count=0,
                max_attempts=max_attempts,
                lease_owner=None,
                lease_expires_at=None,
                next_eligible_at=now,
                idempotency_key=key,
                payload_json=json.dumps(payload or {}),
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task
        except Exception as e:
            db.rollback()
            logger.exception("Error submitting task for %s (%s): %s", source_type, work_unit_id, e)
            raise
        finally:
            db.close()

    def claim_next_task(
        self,
        worker_id: str,
        lease_seconds: int = 90,
        source_filter: Optional[List[str]] = None,
    ) -> Optional[IngestionTask]:
        """
        Atomically claims the highest priority eligible task.
        """
        db = self.db_mgr.get_session()
        try:
            now = datetime.now(timezone.utc)

            query = db.query(IngestionTask).filter(
                and_(
                    IngestionTask.next_eligible_at <= now,
                    or_(
                        IngestionTask.status == TaskStatus.PENDING,
                        and_(
                            IngestionTask.status == TaskStatus.LEASED,
                            IngestionTask.lease_expires_at < now,
                        ),
                    ),
                )
            )

            if self.policy_engine.globally_paused:
                return None

            # Filter out sources currently paused by policy
            paused_sources = [st for st, b in self.policy_engine.budgets.items() if b.is_paused]
            if paused_sources:
                query = query.filter(IngestionTask.source_type.notin_(paused_sources))

            if source_filter:
                query = query.filter(IngestionTask.source_type.in_(source_filter))

            # Order by highest dynamic priority score, then oldest eligible time
            task = query.order_by(
                IngestionTask.priority_score.desc(),
                IngestionTask.next_eligible_at.asc(),
            ).first()

            if not task:
                return None

            # Claim lease
            task.status = TaskStatus.LEASED
            task.lease_owner = worker_id
            task.lease_expires_at = now + timedelta(seconds=lease_seconds)
            task.attempt_count += 1
            task.updated_at = now

            db.commit()
            db.refresh(task)
            return task
        except Exception as e:
            db.rollback()
            logger.error("Error claiming task for worker %s: %s", worker_id, e)
            return None
        finally:
            db.close()

    def complete_task(self, task_id: str) -> bool:
        """Marks task as successfully completed."""
        db = self.db_mgr.get_session()
        try:
            task = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
            if task:
                task.status = TaskStatus.COMPLETED
                task.lease_owner = None
                task.lease_expires_at = None
                task.last_error = None
                task.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error("Error completing task %s: %s", task_id, e)
            return False
        finally:
            db.close()

    def fail_task(
        self,
        task_id: str,
        error: str,
        is_transient: bool = True,
        backoff_seconds: Optional[float] = None,
    ) -> bool:
        """
        Handles failure with bounded exponential backoff retries.
        """
        db = self.db_mgr.get_session()
        try:
            task = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
            if not task:
                return False

            now = datetime.now(timezone.utc)
            task.last_error = error
            task.lease_owner = None
            task.lease_expires_at = None
            task.updated_at = now

            if is_transient and task.attempt_count < task.max_attempts:
                # Exponential backoff or custom test delay
                delay = backoff_seconds if backoff_seconds is not None else min(300.0, 5.0 * (2 ** (task.attempt_count - 1)))
                task.status = TaskStatus.PENDING
                task.priority_class = TaskPriorityClass.RETRY
                task.next_eligible_at = now + timedelta(seconds=delay)
                logger.warning(
                    "Task %s transient failure (attempt %d/%d). Retry scheduled in %.1fs: %s",
                    task_id, task.attempt_count, task.max_attempts, delay, error
                )
            else:
                task.status = TaskStatus.DEAD_LETTER
                logger.error("Task %s moved to DEAD_LETTER (attempt %d/%d): %s", task_id, task.attempt_count, task.max_attempts, error)

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error("Error failing task %s: %s", task_id, e)
            return False
        finally:
            db.close()

    def reclaim_expired_leases(self) -> int:
        """
        Reclaims abandoned leases from crashed or timed-out workers.
        """
        db = self.db_mgr.get_session()
        try:
            now = datetime.now(timezone.utc)
            expired = (
                db.query(IngestionTask)
                .filter(
                    IngestionTask.status == TaskStatus.LEASED,
                    IngestionTask.lease_expires_at < now,
                )
                .all()
            )
            count = len(expired)
            for t in expired:
                t.status = TaskStatus.PENDING
                t.lease_owner = None
                t.lease_expires_at = None
                t.updated_at = now
            if count > 0:
                db.commit()
                logger.info("Reclaimed %d expired worker leases in task scheduler.", count)
            return count
        except Exception as e:
            db.rollback()
            logger.error("Error reclaiming expired leases: %s", e)
            return 0
        finally:
            db.close()

    def apply_aging(self) -> int:
        """
        Applies priority aging to pending tasks so older work units don't starve.
        """
        db = self.db_mgr.get_session()
        try:
            now = datetime.now(timezone.utc)
            pending_tasks = db.query(IngestionTask).filter(IngestionTask.status == TaskStatus.PENDING).all()
            for t in pending_tasks:
                if t.created_at:
                    age_minutes = (now - t.created_at).total_seconds() / 60.0
                    t.priority_score = self.policy_engine.calculate_priority_score(
                        priority_class=t.priority_class,
                        base_priority=0,
                        age_minutes=age_minutes,
                    )
            db.commit()
            return len(pending_tasks)
        except Exception as e:
            db.rollback()
            logger.error("Error applying queue aging: %s", e)
            return 0
        finally:
            db.close()

    def get_queue_stats(self) -> Dict[str, Any]:
        """Returns statistics on active, pending, leased, and failed tasks."""
        db = self.db_mgr.get_session()
        try:
            total = db.query(IngestionTask).count()
            pending = db.query(IngestionTask).filter(IngestionTask.status == TaskStatus.PENDING).count()
            leased = db.query(IngestionTask).filter(IngestionTask.status == TaskStatus.LEASED).count()
            completed = db.query(IngestionTask).filter(IngestionTask.status == TaskStatus.COMPLETED).count()
            dead_letter = db.query(IngestionTask).filter(IngestionTask.status == TaskStatus.DEAD_LETTER).count()

            by_source = {}
            for row in db.query(IngestionTask.source_type, IngestionTask.status).all():
                src, st = row[0], row[1]
                if src not in by_source:
                    by_source[src] = {}
                by_source[src][st] = by_source[src].get(st, 0) + 1

            return {
                "total_tasks": total,
                "pending": pending,
                "leased": leased,
                "completed": completed,
                "dead_letter": dead_letter,
                "by_source": by_source,
            }
        finally:
            db.close()
