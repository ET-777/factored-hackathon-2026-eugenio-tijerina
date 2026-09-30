"""Deny-by-default tool-layer guard for a future trusted demo-session adapter.

Only server-owned authentication code may construct TrustedSession. Never build
it from model output, a chat-supplied customer ID, or an unsigned browser payload.
This module is a policy primitive, not an identity provider or a working tool.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Permission(str, Enum):
    READ_TRANSACTION = "transaction:read"
    CREATE_SIMULATED_INTAKE = "intake:create_simulated"
    CREATE_SIMULATED_HANDOFF = "handoff:create_simulated"


class AccessDenied(Exception):
    """Generic denial deliberately contains no record or customer details."""


@dataclass(frozen=True)
class TrustedSession:
    customer_id: str
    expires_at: datetime
    permissions: frozenset[Permission] = frozenset()


def require_access(
    session: TrustedSession | None,
    record_customer_id: str,
    permission: Permission,
    *,
    now: datetime,
) -> None:
    """Authorize a known record owner, before returning any record fields.

    A future tool must load the owner from its own repository, call this guard,
    and perform any confirmation/idempotency/write verification separately.
    Malformed or expired context fails closed. No permissions are inferred.
    """
    deny = AccessDenied("Access denied")
    if not isinstance(session, TrustedSession):
        raise deny
    if not isinstance(permission, Permission):
        raise deny
    if (
        not isinstance(session.customer_id, str)
        or not session.customer_id.strip()
        or not isinstance(record_customer_id, str)
        or not record_customer_id.strip()
        or session.customer_id != record_customer_id
    ):
        raise deny
    if not isinstance(session.permissions, frozenset) or any(
        not isinstance(value, Permission) for value in session.permissions
    ):
        raise deny
    for timestamp in (session.expires_at, now):
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            raise deny
    if now >= session.expires_at or permission not in session.permissions:
        raise deny
