"""
Celery tasks for payout processing.

process_payout:
    Simulates bank settlement with weighted random outcomes:
      70% → completed
      20% → failed (funds refunded)
      10% → hangs (sleeps 60s, triggering the reaper)

    Uses exponential backoff on retry. Max 3 attempts total.
    Each attempt transitions pending → processing first.

reap_stuck_payouts:
    Scheduled every 30s via Celery Beat.
    Finds payouts stuck in 'processing' for more than PAYOUT_STUCK_THRESHOLD_SECONDS.
    Retries them if under the max attempt limit, otherwise marks them failed.
"""

import random
import time
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Payout, PayoutStatus
from .state_machine import InvalidStateTransitionError

logger = logging.getLogger(__name__)

# Weighted simulation outcomes
OUTCOME_COMPLETED = "completed"
OUTCOME_FAILED = "failed"
OUTCOME_HANG = "hang"

SIMULATION_OUTCOMES = [OUTCOME_COMPLETED, OUTCOME_FAILED, OUTCOME_HANG]
SIMULATION_WEIGHTS = [70, 20, 10]

# Exponential backoff base in seconds
BACKOFF_BASE = 5


@shared_task(
    bind=True,
    max_retries=settings.PAYOUT_MAX_RETRY_ATTEMPTS,
    name="payouts.tasks.process_payout",
)
def process_payout(self, payout_id: str):
    """
    Process a single payout. Called by the API after payout creation,
    and by the reaper when a stuck payout is picked up.

    Task is idempotent at the Celery level: if the payout is already
    completed or failed when the task runs, it logs and exits cleanly.
    """
    from .services import mark_payout_processing, mark_payout_completed, mark_payout_failed
    from .state_machine import InvalidStateTransitionError

    logger.info("process_payout starting for payout_id=%s", payout_id)

    try:
        payout = Payout.objects.get(pk=payout_id)
    except Payout.DoesNotExist:
        logger.error("process_payout: payout %s not found", payout_id)
        return

    # If already in a terminal state (completed/failed), nothing to do.
    # This handles the case where the reaper picks up a payout that was
    # already processed by a prior attempt.
    if payout.status in [PayoutStatus.COMPLETED, PayoutStatus.FAILED]:
        logger.info(
            "process_payout: payout %s already in terminal state %s, skipping",
            payout_id,
            payout.status,
        )
        return

    # Transition to processing (also increments attempt_count)
    try:
        payout = mark_payout_processing(payout_id)
    except InvalidStateTransitionError as e:
        logger.warning(
            "process_payout: invalid transition for payout %s: %s", payout_id, e
        )
        return

    # --- Simulate bank settlement ---
    outcome = random.choices(SIMULATION_OUTCOMES, weights=SIMULATION_WEIGHTS, k=1)[0]
    logger.info("process_payout: payout %s outcome=%s (attempt %d)", payout_id, outcome, payout.attempt_count)

    if outcome == OUTCOME_COMPLETED:
        mark_payout_completed(payout_id)

    elif outcome == OUTCOME_FAILED:
        mark_payout_failed(payout_id, reason="Bank declined the transfer.")

    elif outcome == OUTCOME_HANG:
        # Sleep 60s — longer than the 30s reaper threshold.
        # The reaper will eventually pick this up and re-enqueue.
        # We do NOT mark it failed here — the "hang" simulates a gateway timeout,
        # not a definitive failure. The reaper handles recovery.
        logger.info(
            "process_payout: payout %s is hanging (simulating gateway timeout)...",
            payout_id,
        )
        time.sleep(60)
        # After the sleep, the reaper has already marked this or re-enqueued it.
        # This task just exits; any further action comes from the reaper.
        logger.info("process_payout: payout %s hang sleep done, exiting task", payout_id)


@shared_task(name="payouts.tasks.reap_stuck_payouts")
def reap_stuck_payouts():
    """
    Scheduled every 30 seconds by Celery Beat.

    Finds payouts stuck in PROCESSING state for longer than PAYOUT_STUCK_THRESHOLD_SECONDS.
    For each stuck payout:
      - If attempt_count < PAYOUT_MAX_RETRY_ATTEMPTS: re-enqueue with exponential backoff
      - Otherwise: mark as FAILED and refund the held funds

    This handles the "hang" simulation outcome as well as real-world gateway timeouts.
    """
    from .services import mark_payout_failed

    threshold = settings.PAYOUT_STUCK_THRESHOLD_SECONDS
    max_retries = settings.PAYOUT_MAX_RETRY_ATTEMPTS
    cutoff_time = timezone.now() - timedelta(seconds=threshold)

    stuck_payouts = Payout.objects.filter(
        status=PayoutStatus.PROCESSING,
        processing_started_at__lt=cutoff_time,
    )

    count = stuck_payouts.count()
    if count == 0:
        return

    logger.warning("reap_stuck_payouts: found %d stuck payout(s)", count)

    for payout in stuck_payouts:
        if payout.attempt_count < max_retries:
            # Exponential backoff: 5s, 25s, 125s
            backoff = BACKOFF_BASE ** payout.attempt_count
            logger.info(
                "reap_stuck_payouts: re-enqueuing payout %s (attempt %d), backoff=%ds",
                payout.id,
                payout.attempt_count,
                backoff,
            )
            # Reset to PENDING so process_payout can transition it to PROCESSING again
            Payout.objects.filter(pk=payout.pk, status=PayoutStatus.PROCESSING).update(
                status=PayoutStatus.PENDING,
                processing_started_at=None,
            )
            process_payout.apply_async(
                args=[str(payout.id)],
                countdown=backoff,
            )
        else:
            logger.error(
                "reap_stuck_payouts: payout %s exhausted all %d retries, marking failed",
                payout.id,
                max_retries,
            )
            try:
                mark_payout_failed(
                    str(payout.id),
                    reason=f"Timed out after {max_retries} attempts. Bank gateway unresponsive.",
                )
            except Exception as e:
                logger.exception(
                    "reap_stuck_payouts: error marking payout %s failed: %s", payout.id, e
                )
