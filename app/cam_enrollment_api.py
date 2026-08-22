from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .cam_registration_api import _application, _approve, _clean, _require_admin
from .cam_registration_branding_api import _academy_name
from .database import connection, fetch_all, fetch_one

router = APIRouter(tags=["cam-enrollment"])

PUBLIC_FORM = Path(__file__).resolve().parent / "static" / "cam_enrollment_public_v1.html"
DOCUMENT_ROOT = Path(__file__).resolve().parent / "enrollment_documents"
ENROLLMENT_LINK_DAYS = 14
ACTIVE_STATUSES = {"created", "sent", "opened", "in_progress"}
ELECTRONIC_CONSENT_VERSION = "cam-esign-v1"

TEST_DOCUMENTS = (
    {
        "code": "test_parent_consent_packet",
        "title": "CAM Cricket Academy Parent Registration & Consent Packet",
        "version": "test-v1",
        "file_name": "CAM_Cricket_Academy_Parent_Consent_Packet_TEST.pdf",
        "required": 1,
        "display_order": 10,
        "test_only": 1,
    },
    {
        "code": "test_payment_authorization",
        "title": "CAM Parent Enrollment & Payment Authorization Agreement",
        "version": "test-v1",
        "file_name": "CAM_Parent_Enrollment_and_Payment_Authorization_Agreement_TEST.pdf",
        "required": 1,
        "display_order": 20,
        "test_only": 1,
    },
)


class EnrollmentSentPayload(BaseModel):
    channel: Literal["sms", "whatsapp", "email"]


class AgreementAcceptancePayload(BaseModel):
    document_ids: list[int]
    signer_name: str
    electronic_signature_consent: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_enrollment_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            application_id BIGINT NOT NULL UNIQUE,
            player_id BIGINT NOT NULL,
            created_by_user_id BIGINT,
            created_by_name TEXT,
            parent_first_name TEXT,
            parent_last_name TEXT,
            parent_phone TEXT,
            parent_email TEXT,
            token_hash TEXT NOT NULL UNIQUE,
            token_last4 TEXT,
            status TEXT NOT NULL DEFAULT 'created',
            last_channel TEXT,
            expires_at TEXT NOT NULL,
            sent_at TEXT,
            opened_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            last_activity_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(application_id) REFERENCES academy_registration_applications(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by_user_id) REFERENCES academy_users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_invites_status ON academy_enrollment_invites(status);
        CREATE INDEX IF NOT EXISTS idx_enrollment_invites_player ON academy_enrollment_invites(player_id);

        CREATE TABLE IF NOT EXISTS academy_enrollment_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            version TEXT NOT NULL,
            file_name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            required INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            test_only INTEGER NOT NULL DEFAULT 0,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_documents_active ON academy_enrollment_documents(active,display_order);

        CREATE TABLE IF NOT EXISTS academy_enrollment_document_acceptances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id BIGINT NOT NULL,
            document_id BIGINT NOT NULL,
            document_title TEXT NOT NULL,
            document_version TEXT NOT NULL,
            document_sha256 TEXT NOT NULL,
            viewed_at TEXT,
            accepted_at TEXT,
            signer_name TEXT,
            electronic_consent_version TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(enrollment_id,document_id),
            FOREIGN KEY(enrollment_id) REFERENCES academy_enrollment_invites(id) ON DELETE CASCADE,
            FOREIGN KEY(document_id) REFERENCES academy_enrollment_documents(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_document_acceptances_enrollment
            ON academy_enrollment_document_acceptances(enrollment_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _seed_test_documents() -> None:
    DOCUMENT_ROOT.mkdir(parents=True, exist_ok=True)
    for spec in TEST_DOCUMENTS:
        path = DOCUMENT_ROOT / str(spec["file_name"])
        if not path.exists():
            continue
        sha256_value = _file_sha256(path)
        existing = fetch_one(
            "SELECT id FROM academy_enrollment_documents WHERE code=?",
            (str(spec["code"]),),
        )
        with connection() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE academy_enrollment_documents
                    SET title=?,version=?,file_name=?,sha256=?,required=?,active=1,test_only=?,display_order=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        str(spec["title"]),
                        str(spec["version"]),
                        str(spec["file_name"]),
                        sha256_value,
                        int(spec["required"]),
                        int(spec["test_only"]),
                        int(spec["display_order"]),
                        int(existing["id"]),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO academy_enrollment_documents(
                        academy_id,code,title,version,file_name,sha256,required,active,test_only,display_order
                    ) VALUES(NULL,?,?,?,?,?,?,1,?,?)
                    """,
                    (
                        str(spec["code"]),
                        str(spec["title"]),
                        str(spec["version"]),
                        str(spec["file_name"]),
                        sha256_value,
                        int(spec["required"]),
                        int(spec["test_only"]),
                        int(spec["display_order"]),
                    ),
                )


def _enrollment(enrollment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT e.*,a.player_first_name,a.player_last_name,a.status AS registration_status
        FROM academy_enrollment_invites e
        JOIN academy_registration_applications a ON a.id=e.application_id
        WHERE e.id=?
        """,
        (enrollment_id,),
    )
    if not row:
        raise HTTPException(404, "Enrollment record not found")
    row["academy_name"] = _academy_name(int(row.get("academy_id") or 0) or None)
    row["player_name"] = " ".join(
        part
        for part in [
            str(row.get("player_first_name") or "").strip(),
            str(row.get("player_last_name") or "").strip(),
        ]
        if part
    )
    return row


def _enrollment_by_application(application_id: int) -> dict | None:
    row = fetch_one("SELECT id FROM academy_enrollment_invites WHERE application_id=?", (application_id,))
    return _enrollment(int(row["id"])) if row else None


def _enrollment_for_token(token: str, *, mark_opened: bool = False) -> dict:
    row = fetch_one("SELECT id FROM academy_enrollment_invites WHERE token_hash=?", (_hash_token(token),))
    if not row:
        raise HTTPException(404, "Enrollment link is not valid")
    enrollment = _enrollment(int(row["id"]))
    try:
        expires = datetime.fromisoformat(str(enrollment["expires_at"]))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise HTTPException(410, "Enrollment link has expired") from exc
    if expires <= _now() and str(enrollment.get("status")) != "completed":
        with connection() as conn:
            conn.execute(
                "UPDATE academy_enrollment_invites SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(enrollment["id"]),),
            )
        raise HTTPException(410, "Enrollment link has expired")
    if str(enrollment.get("status")) == "expired":
        raise HTTPException(410, "Enrollment link has expired")
    if mark_opened and str(enrollment.get("status")) in {"created", "sent"}:
        now = _iso(_now())
        with connection() as conn:
            conn.execute(
                """
                UPDATE academy_enrollment_invites
                SET status='opened',opened_at=COALESCE(opened_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (now, now, int(enrollment["id"])),
            )
        enrollment = _enrollment(int(enrollment["id"]))
    return enrollment


def _academy_id_for_application(application_id: int) -> int | None:
    row = fetch_one(
        """
        SELECT i.academy_id
        FROM academy_registration_applications a
        JOIN academy_registration_invites i ON i.id=a.invite_id
        WHERE a.id=?
        """,
        (application_id,),
    )
    return int(row["academy_id"]) if row and row.get("academy_id") else None


def _create_or_rotate_enrollment(application: dict, player_id: int, user: dict, request: Request) -> dict:
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(days=ENROLLMENT_LINK_DAYS)
    academy_id = _academy_id_for_application(int(application["id"]))
    existing = _enrollment_by_application(int(application["id"]))
    user_id = int(user.get("id") or 0) or None
    user_name = str(user.get("display_name") or "Admin")

    with connection() as conn:
        if existing:
            existing_status = str(existing.get("status") or "")
            if existing_status in {"documents_accepted", "completed"}:
                raise HTTPException(409, "Enrollment has already progressed beyond link generation")
            conn.execute(
                """
                UPDATE academy_enrollment_invites
                SET token_hash=?,token_last4=?,status='created',expires_at=?,last_channel=NULL,sent_at=NULL,
                    opened_at=NULL,started_at=NULL,last_activity_at=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (_hash_token(token), token[-4:], _iso(expires), _iso(now), int(existing["id"])),
            )
            enrollment_id = int(existing["id"])
        else:
            row = conn.execute(
                """
                INSERT INTO academy_enrollment_invites(
                    academy_id,application_id,player_id,created_by_user_id,created_by_name,
                    parent_first_name,parent_last_name,parent_phone,parent_email,
                    token_hash,token_last4,status,expires_at,last_activity_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'created',?,?) RETURNING id
                """,
                (
                    academy_id,
                    int(application["id"]),
                    player_id,
                    user_id,
                    user_name,
                    _clean(application.get("parent_first_name")),
                    _clean(application.get("parent_last_name")),
                    _clean(application.get("parent_phone")),
                    _clean(application.get("parent_email")),
                    _hash_token(token),
                    token[-4:],
                    _iso(expires),
                    _iso(now),
                ),
            ).fetchone()
            enrollment_id = int(row["id"])

    result = _enrollment(enrollment_id)
    result["enrollment_url"] = f"{str(request.base_url).rstrip('/')}/enroll/{token}"
    result["expires_in_days"] = ENROLLMENT_LINK_DAYS
    return result


def _documents_for_enrollment(enrollment: dict, token: str) -> list[dict]:
    rows = fetch_all(
        """
        SELECT d.*,
               a.viewed_at AS acceptance_viewed_at,
               a.accepted_at AS acceptance_accepted_at,
               a.signer_name AS acceptance_signer_name
        FROM academy_enrollment_documents d
        LEFT JOIN academy_enrollment_document_acceptances a
          ON a.document_id=d.id AND a.enrollment_id=?
        WHERE d.active=1 AND (d.academy_id IS NULL OR d.academy_id=?)
        ORDER BY d.display_order,d.id
        """,
        (int(enrollment["id"]), enrollment.get("academy_id")),
    )
    result = []
    for row in rows:
        file_path = DOCUMENT_ROOT / str(row["file_name"])
        result.append(
            {
                "id": int(row["id"]),
                "code": row.get("code"),
                "title": row.get("title"),
                "version": row.get("version"),
                "sha256": row.get("sha256"),
                "required": bool(row.get("required")),
                "test_only": bool(row.get("test_only")),
                "available": file_path.exists(),
                "viewed": bool(row.get("acceptance_viewed_at")),
                "accepted": bool(row.get("acceptance_accepted_at")),
                "accepted_at": row.get("acceptance_accepted_at"),
                "signer_name": row.get("acceptance_signer_name"),
                "view_url": f"/api/public/enrollment/{token}/documents/{int(row['id'])}/view",
                "download_url": f"/api/public/enrollment/{token}/documents/{int(row['id'])}/download",
            }
        )
    return result


def _document_for_enrollment(enrollment: dict, document_id: int) -> dict:
    row = fetch_one(
        """
        SELECT *
        FROM academy_enrollment_documents
        WHERE id=? AND active=1 AND (academy_id IS NULL OR academy_id=?)
        """,
        (document_id, enrollment.get("academy_id")),
    )
    if not row:
        raise HTTPException(404, "Enrollment document not found")
    path = DOCUMENT_ROOT / str(row["file_name"])
    if not path.exists():
        raise HTTPException(503, "Enrollment document file is unavailable")
    actual_sha = _file_sha256(path)
    if actual_sha != str(row.get("sha256") or ""):
        raise HTTPException(503, "Enrollment document integrity check failed")
    row["path"] = path
    return row


def _record_view(enrollment: dict, document: dict) -> None:
    now = _iso(_now())
    existing = fetch_one(
        "SELECT id,viewed_at FROM academy_enrollment_document_acceptances WHERE enrollment_id=? AND document_id=?",
        (int(enrollment["id"]), int(document["id"])),
    )
    with connection() as conn:
        if existing:
            conn.execute(
                """
                UPDATE academy_enrollment_document_acceptances
                SET viewed_at=COALESCE(viewed_at,?),updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (now, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO academy_enrollment_document_acceptances(
                    enrollment_id,document_id,document_title,document_version,document_sha256,viewed_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    int(enrollment["id"]),
                    int(document["id"]),
                    str(document["title"]),
                    str(document["version"]),
                    str(document["sha256"]),
                    now,
                ),
            )
        conn.execute(
            "UPDATE academy_enrollment_invites SET last_activity_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (now, int(enrollment["id"])),
        )


def _safe_download_name(document: dict) -> str:
    title = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "" for ch in str(document["title"])).strip()
    return f"{title or 'Enrollment Document'} - {document['version']}.pdf"


def _steps_for_status(status_value: str) -> list[dict]:
    keys = [
        ("summary", "Enrollment Summary"),
        ("agreements", "Agreements & Documents"),
        ("payment", "Fees & Payment"),
        ("complete", "Complete"),
    ]
    current_index = 0
    done_through = -1
    if status_value == "in_progress":
        current_index = 1
        done_through = 0
    elif status_value == "documents_accepted":
        current_index = 2
        done_through = 1
    elif status_value == "completed":
        current_index = 3
        done_through = 3

    steps = []
    for index, (key, label) in enumerate(keys):
        if index <= done_through:
            step_status = "done"
        elif index == current_index:
            step_status = "current"
        else:
            step_status = "later"
        steps.append({"key": key, "label": label, "status": step_status})
    return steps


_ensure_tables()
_seed_test_documents()


@router.post("/api/cam/enrollments/from-registration/{application_id}")
def approve_and_create_enrollment(
    application_id: int,
    request: Request,
    user: dict = Depends(_require_admin),
):
    application = _application(application_id)
    status_value = str(application.get("status") or "")
    if status_value == "submitted":
        player_id = _approve(application, user)
        application = _application(application_id)
    elif status_value == "approved" and application.get("approved_player_id"):
        player_id = int(application["approved_player_id"])
    else:
        raise HTTPException(409, "Only a submitted or approved registration can start enrollment")
    return _create_or_rotate_enrollment(application, int(player_id), user, request)


@router.get("/api/cam/enrollments")
def list_enrollments(_: dict = Depends(_require_admin)):
    rows = fetch_all("SELECT id FROM academy_enrollment_invites ORDER BY created_at DESC,id DESC")
    return [_enrollment(int(row["id"])) for row in rows]


@router.get("/api/cam/enrollments/by-application/{application_id}")
def enrollment_by_application(application_id: int, _: dict = Depends(_require_admin)):
    enrollment = _enrollment_by_application(application_id)
    if not enrollment:
        raise HTTPException(404, "Enrollment has not been created for this registration")
    return enrollment


@router.post("/api/cam/enrollments/{enrollment_id}/sent")
def mark_enrollment_sent(
    enrollment_id: int,
    payload: EnrollmentSentPayload,
    _: dict = Depends(_require_admin),
):
    enrollment = _enrollment(enrollment_id)
    if str(enrollment.get("status")) not in ACTIVE_STATUSES:
        raise HTTPException(409, "This enrollment link can no longer be sent")
    now = _iso(_now())
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_enrollment_invites
            SET status=CASE WHEN status='created' THEN 'sent' ELSE status END,last_channel=?,
                sent_at=COALESCE(sent_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (payload.channel, now, now, enrollment_id),
        )
    return _enrollment(enrollment_id)


@router.get("/api/public/enrollment/{token}")
def public_enrollment(token: str):
    enrollment = _enrollment_for_token(token, mark_opened=True)
    return {
        "enrollment": {
            "id": int(enrollment["id"]),
            "status": enrollment.get("status"),
            "expires_at": enrollment.get("expires_at"),
            "academy_name": enrollment.get("academy_name"),
            "player_name": enrollment.get("player_name"),
            "parent_first_name": enrollment.get("parent_first_name"),
            "parent_last_name": enrollment.get("parent_last_name"),
        },
        "steps": _steps_for_status(str(enrollment.get("status") or "")),
    }


@router.post("/api/public/enrollment/{token}/start")
def start_public_enrollment(token: str):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status")) not in ACTIVE_STATUSES:
        raise HTTPException(409, "This enrollment can no longer be started")
    now = _iso(_now())
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_enrollment_invites
            SET status='in_progress',started_at=COALESCE(started_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (now, now, int(enrollment["id"])),
        )
    return {"status": "in_progress", "next_step": "agreements"}


@router.get("/api/public/enrollment/{token}/documents")
def public_enrollment_documents(token: str):
    enrollment = _enrollment_for_token(token)
    status_value = str(enrollment.get("status") or "")
    if status_value not in {"in_progress", "documents_accepted", "completed"}:
        raise HTTPException(409, "Start enrollment before reviewing agreements")
    documents = _documents_for_enrollment(enrollment, token)
    if not documents:
        raise HTTPException(503, "No enrollment documents are configured")
    return {
        "status": status_value,
        "electronic_consent_version": ELECTRONIC_CONSENT_VERSION,
        "documents": documents,
    }


@router.get("/api/public/enrollment/{token}/documents/{document_id}/view")
def view_public_enrollment_document(token: str, document_id: int):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status") or "") not in {"in_progress", "documents_accepted", "completed"}:
        raise HTTPException(409, "Start enrollment before reviewing agreements")
    document = _document_for_enrollment(enrollment, document_id)
    _record_view(enrollment, document)
    return FileResponse(
        document["path"],
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{_safe_download_name(document)}"'},
    )


@router.get("/api/public/enrollment/{token}/documents/{document_id}/download")
def download_public_enrollment_document(token: str, document_id: int):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status") or "") not in {"in_progress", "documents_accepted", "completed"}:
        raise HTTPException(409, "Start enrollment before reviewing agreements")
    document = _document_for_enrollment(enrollment, document_id)
    _record_view(enrollment, document)
    return FileResponse(
        document["path"],
        media_type="application/pdf",
        filename=_safe_download_name(document),
    )


@router.post("/api/public/enrollment/{token}/agreements/accept")
def accept_public_enrollment_agreements(
    token: str,
    payload: AgreementAcceptancePayload,
    request: Request,
):
    enrollment = _enrollment_for_token(token)
    status_value = str(enrollment.get("status") or "")
    if status_value == "documents_accepted":
        return {"status": "documents_accepted", "next_step": "payment"}
    if status_value != "in_progress":
        raise HTTPException(409, "Agreements can only be accepted after enrollment has started")

    signer_name = " ".join(str(payload.signer_name or "").split())
    if len(signer_name.split()) < 2:
        raise HTTPException(422, "Enter the parent/guardian full legal name")
    if not payload.electronic_signature_consent:
        raise HTTPException(422, "Electronic signature consent is required")

    documents = _documents_for_enrollment(enrollment, token)
    required_ids = {int(item["id"]) for item in documents if item["required"]}
    accepted_ids = {int(value) for value in payload.document_ids}
    if not required_ids or not required_ids.issubset(accepted_ids):
        raise HTTPException(422, "Accept each required enrollment document before continuing")

    rows = fetch_all(
        """
        SELECT document_id,viewed_at
        FROM academy_enrollment_document_acceptances
        WHERE enrollment_id=?
        """,
        (int(enrollment["id"]),),
    )
    viewed_ids = {int(row["document_id"]) for row in rows if row.get("viewed_at")}
    if required_ids - viewed_ids:
        raise HTTPException(422, "Open and review each required PDF before accepting it")

    now = _iso(_now())
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    by_id = {int(item["id"]): item for item in documents}

    with connection() as conn:
        for document_id in sorted(required_ids):
            document = by_id[document_id]
            conn.execute(
                """
                UPDATE academy_enrollment_document_acceptances
                SET document_title=?,document_version=?,document_sha256=?,accepted_at=?,signer_name=?,
                    electronic_consent_version=?,ip_address=?,user_agent=?,updated_at=CURRENT_TIMESTAMP
                WHERE enrollment_id=? AND document_id=?
                """,
                (
                    str(document["title"]),
                    str(document["version"]),
                    str(document["sha256"]),
                    now,
                    signer_name,
                    ELECTRONIC_CONSENT_VERSION,
                    ip_address,
                    user_agent,
                    int(enrollment["id"]),
                    document_id,
                ),
            )
        conn.execute(
            """
            UPDATE academy_enrollment_invites
            SET status='documents_accepted',last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (now, int(enrollment["id"])),
        )

    return {
        "status": "documents_accepted",
        "next_step": "payment",
        "accepted_documents": len(required_ids),
        "accepted_at": now,
        "signer_name": signer_name,
    }


@router.get("/enroll/{token}", response_class=HTMLResponse)
def enrollment_form_page(token: str):
    if not PUBLIC_FORM.exists():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Enrollment portal is not available")
    return HTMLResponse(PUBLIC_FORM.read_text(encoding="utf-8"))
