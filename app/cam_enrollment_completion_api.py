from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .cam_enrollment_api import DOCUMENT_ROOT, _enrollment, _enrollment_for_token
from .cam_registration_api import _require_admin
from .database import connection, fetch_all, fetch_one

router = APIRouter(tags=["cam-enrollment-completion"])

COMPLETION_VERSION = "cam-enrollment-complete-v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_enrollment_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id BIGINT NOT NULL UNIQUE,
            academy_id BIGINT,
            player_id BIGINT NOT NULL,
            completion_version TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            package_ready INTEGER NOT NULL DEFAULT 1,
            confirmation_delivery_status TEXT NOT NULL DEFAULT 'secure_portal_ready',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(enrollment_id) REFERENCES academy_enrollment_invites(id) ON DELETE CASCADE,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_completions_academy
            ON academy_enrollment_completions(academy_id,completed_at);
    """
    with connection() as conn:
        conn.executescript(schema)


def _payment_authorization(enrollment_id: int) -> dict | None:
    return fetch_one(
        "SELECT * FROM academy_enrollment_payment_authorizations WHERE enrollment_id=?",
        (enrollment_id,),
    )


def _completion(enrollment_id: int) -> dict | None:
    return fetch_one(
        "SELECT * FROM academy_enrollment_completions WHERE enrollment_id=?",
        (enrollment_id,),
    )


def _document_rows(enrollment: dict) -> list[dict]:
    return fetch_all(
        """
        SELECT d.id,d.code,d.title,d.version,d.file_name,d.sha256,d.required,d.display_order,
               a.viewed_at,a.accepted_at,a.signer_name,a.electronic_consent_version,
               a.document_title,a.document_version,a.document_sha256
        FROM academy_enrollment_documents d
        LEFT JOIN academy_enrollment_document_acceptances a
          ON a.document_id=d.id AND a.enrollment_id=?
        WHERE d.active=1 AND (d.academy_id IS NULL OR d.academy_id=?)
        ORDER BY d.display_order,d.id
        """,
        (int(enrollment["id"]), enrollment.get("academy_id")),
    )


def _completion_readiness(enrollment: dict) -> tuple[dict, list[dict]]:
    authorization = _payment_authorization(int(enrollment["id"]))
    if not authorization or str(authorization.get("setup_status") or "") != "succeeded":
        raise HTTPException(409, "Save a valid payment method before completing enrollment")

    documents = _document_rows(enrollment)
    required = [row for row in documents if bool(row.get("required"))]
    if not required or any(not row.get("accepted_at") for row in required):
        raise HTTPException(409, "Accept every required enrollment document before completing enrollment")
    return authorization, documents


def _safe_name(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "" for ch in str(value or "")).strip()
    return cleaned or fallback


def _summary(enrollment: dict, token: str) -> dict:
    authorization, documents = _completion_readiness(enrollment)
    completion = _completion(int(enrollment["id"]))
    completed = bool(completion or str(enrollment.get("status") or "") == "completed")
    completed_at = (completion or {}).get("completed_at") or enrollment.get("completed_at")

    accepted_documents = []
    for row in documents:
        if not row.get("accepted_at"):
            continue
        accepted_documents.append(
            {
                "id": int(row["id"]),
                "title": row.get("document_title") or row.get("title"),
                "version": row.get("document_version") or row.get("version"),
                "sha256": row.get("document_sha256") or row.get("sha256"),
                "accepted_at": row.get("accepted_at"),
                "signer_name": row.get("signer_name"),
                "electronic_consent_version": row.get("electronic_consent_version"),
                "download_url": f"/api/public/enrollment/{token}/documents/{int(row['id'])}/download",
            }
        )

    parent_name = " ".join(
        part for part in [str(enrollment.get("parent_first_name") or "").strip(), str(enrollment.get("parent_last_name") or "").strip()] if part
    )
    return {
        "status": "completed" if completed else "payment_method_added",
        "completion_ready": True,
        "completion_version": COMPLETION_VERSION,
        "completed_at": completed_at,
        "player": {
            "id": int(enrollment["player_id"]),
            "name": enrollment.get("player_name"),
        },
        "parent": {"name": parent_name},
        "payment": {
            "provider": authorization.get("provider"),
            "card_brand": authorization.get("card_brand"),
            "card_last4": authorization.get("card_last4"),
            "monthly_amount_cents": int(authorization.get("monthly_amount_cents") or 0),
            "currency": authorization.get("currency") or "USD",
            "billing_start_date": authorization.get("billing_start_date"),
            "recurring_consent_version": authorization.get("recurring_consent_version"),
            "recurring_consent_sha256": authorization.get("recurring_consent_sha256"),
        },
        "documents": accepted_documents,
        "package_url": f"/api/public/enrollment/{token}/completion/package" if completed else None,
        "placement_ready": completed,
        "next_operational_step": "program_batch_assignment" if completed else "complete_enrollment",
        "confirmation_delivery": {
            "secure_portal": "ready" if completed else "pending_completion",
            "email_sms": "not_configured",
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _confirmation_text(enrollment: dict, summary: dict) -> str:
    payment = summary["payment"]
    return "\n".join(
        [
            "CAM Enrollment Confirmation",
            "===========================",
            f"Player: {summary['player']['name'] or ''}",
            f"Parent/Guardian: {summary['parent']['name'] or ''}",
            f"Enrollment completed: {summary.get('completed_at') or ''}",
            f"Monthly tuition: {payment['currency']} {payment['monthly_amount_cents'] / 100:,.2f}",
            f"First payment date: {payment.get('billing_start_date') or ''}",
            f"Saved payment method: {str(payment.get('card_brand') or 'Card').title()} ending {payment.get('card_last4') or ''}",
            "Due during enrollment: USD 0.00",
            "Next academy step: Program / Batch Assignment",
            "",
            "This package is generated from the secure CAM enrollment record.",
        ]
    )


def _acceptance_text(summary: dict) -> str:
    lines = ["CAM Enrollment Acceptance Summary", "================================", ""]
    for index, doc in enumerate(summary["documents"], start=1):
        lines.extend(
            [
                f"Document {index}: {doc.get('title') or ''}",
                f"Version: {doc.get('version') or ''}",
                f"SHA-256: {doc.get('sha256') or ''}",
                f"Accepted at: {doc.get('accepted_at') or ''}",
                f"Signer: {doc.get('signer_name') or ''}",
                f"Electronic consent version: {doc.get('electronic_consent_version') or ''}",
                "",
            ]
        )
    payment = summary["payment"]
    lines.extend(
        [
            "Recurring Tuition Authorization",
            "-------------------------------",
            f"Consent version: {payment.get('recurring_consent_version') or ''}",
            f"Consent SHA-256: {payment.get('recurring_consent_sha256') or ''}",
            f"Saved method: {str(payment.get('card_brand') or 'Card').title()} ending {payment.get('card_last4') or ''}",
            f"First charge date: {payment.get('billing_start_date') or ''}",
        ]
    )
    return "\n".join(lines)


_ensure_tables()


@router.get("/api/public/enrollment/{token}/completion")
def public_completion_summary(token: str):
    enrollment = _enrollment_for_token(token)
    return _summary(enrollment, token)


@router.post("/api/public/enrollment/{token}/complete")
def complete_public_enrollment(token: str, request: Request):
    enrollment = _enrollment_for_token(token)
    status_value = str(enrollment.get("status") or "")
    if status_value == "completed":
        return _summary(enrollment, token)
    if status_value not in {"documents_accepted", "payment_method_added"}:
        raise HTTPException(409, "Enrollment is not ready for completion")

    _completion_readiness(enrollment)
    now = _now_iso()
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO academy_enrollment_completions(
                enrollment_id,academy_id,player_id,completion_version,completed_at,ip_address,user_agent,
                package_ready,confirmation_delivery_status
            ) VALUES(?,?,?,?,?,?,?,1,'secure_portal_ready')
            ON CONFLICT(enrollment_id) DO UPDATE SET
                completion_version=excluded.completion_version,
                completed_at=COALESCE(academy_enrollment_completions.completed_at,excluded.completed_at),
                ip_address=COALESCE(academy_enrollment_completions.ip_address,excluded.ip_address),
                user_agent=COALESCE(academy_enrollment_completions.user_agent,excluded.user_agent),
                package_ready=1,confirmation_delivery_status='secure_portal_ready',updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(enrollment["id"]),
                int(enrollment.get("academy_id") or 0) or None,
                int(enrollment["player_id"]),
                COMPLETION_VERSION,
                now,
                ip_address,
                user_agent,
            ),
        )
        conn.execute(
            """
            UPDATE academy_enrollment_invites
            SET status='completed',completed_at=COALESCE(completed_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (now, now, int(enrollment["id"])),
        )

    return _summary(_enrollment(int(enrollment["id"])), token)


@router.get("/api/public/enrollment/{token}/completion/package")
def download_completion_package(token: str):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status") or "") != "completed":
        raise HTTPException(409, "Complete enrollment before downloading the final package")
    summary = _summary(enrollment, token)
    documents = _document_rows(enrollment)

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        accepted_index = 0
        for row in documents:
            if not row.get("accepted_at"):
                continue
            accepted_index += 1
            path = DOCUMENT_ROOT / str(row.get("file_name") or "")
            if not path.exists():
                raise HTTPException(503, "An accepted enrollment document is unavailable")
            expected_sha = str(row.get("document_sha256") or row.get("sha256") or "")
            if not expected_sha or _sha256_file(path) != expected_sha:
                raise HTTPException(503, "An accepted enrollment document failed its integrity check")
            title = _safe_name(str(row.get("document_title") or row.get("title") or ""), f"Document {accepted_index}")
            version = _safe_name(str(row.get("document_version") or row.get("version") or ""), "version")
            archive.writestr(f"{accepted_index:02d} - {title} - {version}.pdf", path.read_bytes())

        archive.writestr("CAM Enrollment Confirmation.txt", _confirmation_text(enrollment, summary))
        archive.writestr("CAM Acceptance Summary.txt", _acceptance_text(summary))

    player_name = _safe_name(str(summary["player"].get("name") or "Player"), "Player").replace(" ", "_")
    filename = f"CAM_Enrollment_Package_{player_name}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/cam/enrollments/completed")
def completed_enrollments_ready_for_placement(user: dict = Depends(_require_admin)):
    academy_id = int(user.get("academy_id") or 0) or None
    params: tuple = ()
    academy_clause = ""
    if academy_id is not None:
        academy_clause = "WHERE c.academy_id=?"
        params = (academy_id,)
    rows = fetch_all(
        f"""
        SELECT c.enrollment_id,c.completed_at,c.academy_id,e.player_id,
               e.parent_first_name,e.parent_last_name,p.name AS player_name
        FROM academy_enrollment_completions c
        JOIN academy_enrollment_invites e ON e.id=c.enrollment_id
        LEFT JOIN players p ON p.id=e.player_id
        {academy_clause}
        ORDER BY c.completed_at DESC,c.enrollment_id DESC
        """,
        params,
    )
    return [
        {
            **row,
            "placement_ready": True,
            "next_operational_step": "program_batch_assignment",
        }
        for row in rows
    ]
