from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from .academy_auth_api import current_access_user
from .database import fetch_all


def require_roles(*roles: str) -> Callable:
    allowed = set(roles)

    def dependency(user: dict = Depends(current_access_user)) -> dict:
        if str(user.get("role")) not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this Academy function")
        return user

    return dependency


def require_permission(permission: str) -> Callable:
    def dependency(user: dict = Depends(current_access_user)) -> dict:
        if permission not in set(user.get("permissions") or []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this Academy function")
        return user

    return dependency


def linked_player_ids_for_guardian(guardian_id: int, *, billing_only: bool = False) -> list[int]:
    sql = "SELECT player_id FROM player_guardians WHERE guardian_id=?"
    params: list[object] = [guardian_id]
    if billing_only:
        sql += " AND billing_contact=1"
    sql += " ORDER BY player_id"
    return [int(row["player_id"]) for row in fetch_all(sql, params)]


def billing_account_ids_for_guardian(guardian_id: int) -> list[int]:
    rows = fetch_all(
        """
        SELECT DISTINCT a.id
        FROM academy_billing_accounts a
        JOIN academy_billing_account_players bap
          ON bap.account_id=a.id AND bap.status='active'
        JOIN player_guardians pg
          ON pg.player_id=bap.player_id AND pg.billing_contact=1
        WHERE pg.guardian_id=? AND a.status='active'
        ORDER BY a.id
        """,
        (guardian_id,),
    )
    return [int(row["id"]) for row in rows]


def require_parent_billing_user(user: dict = Depends(current_access_user)) -> dict:
    if user.get("role") != "parent" or not user.get("guardian_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A linked parent account is required")
    if "billing.view" not in set(user.get("permissions") or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Parent billing access is not enabled")
    return user
