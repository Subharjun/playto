"""
State machine for Payout status transitions.

Legal transitions:
    pending    → processing
    processing → completed
    processing → failed

Everything else is illegal and raises InvalidStateTransitionError.
This is enforced at the service layer — not just in the API, but in the
background task too — so no code path can make an invalid transition.
"""

from .models import PayoutStatus


class InvalidStateTransitionError(Exception):
    pass


# Explicit whitelist — anything not in this map is illegal
LEGAL_TRANSITIONS: dict[str, list[str]] = {
    PayoutStatus.PENDING: [PayoutStatus.PROCESSING],
    PayoutStatus.PROCESSING: [PayoutStatus.COMPLETED, PayoutStatus.FAILED],
    # Terminal states — no outgoing transitions allowed
    PayoutStatus.COMPLETED: [],
    PayoutStatus.FAILED: [],
}


def assert_legal_transition(current_status: str, new_status: str) -> None:
    """
    Raises InvalidStateTransitionError if the transition is not legal.

    Call this BEFORE updating the payout status. The calling code must
    have a SELECT FOR UPDATE lock on the payout row to prevent TOCTOU.

    Example of a blocked transition:
        assert_legal_transition("failed", "completed")
        → raises InvalidStateTransitionError("Cannot transition from failed to completed")
    """
    allowed = LEGAL_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition from '{current_status}' to '{new_status}'. "
            f"Legal next states from '{current_status}': {allowed or ['none (terminal state)']}"
        )
