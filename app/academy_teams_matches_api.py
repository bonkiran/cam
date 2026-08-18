from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-teams-matches"])


class TeamPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    age_group: str | None = Field(default=None, max_length=80)
    level: str | None = Field(default=None, max_length=100)
    coach_id: int | None = Field(default=None, gt=0)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = Field(default=None, max_length=1500)


class TeamPlayerPayload(BaseModel):
    player_id: int = Field(gt=0)
    team_role: Literal["player", "captain", "wicketkeeper"] = "player"
    joined_on: str | None = Field(default=None, max_length=20)


class MatchPayload(BaseModel):
    team_id: int = Field(gt=0)
    opponent: str = Field(min_length=2, max_length=180)
    match_date: str = Field(max_length=20)
    start_time: str | None = Field(default=None, max_length=10)
    venue: str | None = Field(default=None, max_length=240)
    competition: str | None = Field(default=None, max_length=180)
    match_type: str | None = Field(default=None, max_length=80)
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"
    notes: str | None = Field(default=None, max_length=1500)


class SquadEntry(BaseModel):
    player_id: int = Field(gt=0)
    squad_role: Literal["player", "captain", "wicketkeeper"] = "player"


class SquadPayload(BaseModel):
    players: list[SquadEntry] = Field(min_length=1, max_length=30)


class MatchPlayerStat(BaseModel):
    player_id: int = Field(gt=0)
    batting_runs: int = Field(default=0, ge=0, le=1000)
    balls_faced: int = Field(default=0, ge=0, le=1000)
    fours: int = Field(default=0, ge=0, le=100)
    sixes: int = Field(default=0, ge=0, le=100)
    dismissal: str | None = Field(default=None, max_length=200)
    bowling_overs: str | None = Field(default=None, max_length=20)
    maidens: int = Field(default=0, ge=0, le=100)
    runs_conceded: int = Field(default=0, ge=0, le=1000)
    wickets: int = Field(default=0, ge=0, le=20)
    catches: int = Field(default=0, ge=0, le=20)
    run_outs: int = Field(default=0, ge=0, le=20)
    stumpings: int = Field(default=0, ge=0, le=20)
    notes: str | None = Field(default=None, max_length=1000)


class MatchResultPayload(BaseModel):
    result: Literal["won", "lost", "tied", "no_result"]
    our_score: str | None = Field(default=None, max_length=80)
    opponent_score: str | None = Field(default=None, max_length=80)
    result_summary: str | None = Field(default=None, max_length=500)
    player_stats: list[MatchPlayerStat] = Field(default_factory=list, max_length=30)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            name TEXT NOT NULL,
            age_group TEXT,
            level TEXT,
            coach_id BIGINT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_teams_status ON academy_teams(status);
        CREATE INDEX IF NOT EXISTS idx_academy_teams_coach ON academy_teams(coach_id);

        CREATE TABLE IF NOT EXISTS academy_team_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            team_role TEXT NOT NULL DEFAULT 'player',
            status TEXT NOT NULL DEFAULT 'active',
            joined_on TEXT,
            ended_on TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(team_id) REFERENCES academy_teams(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_team_players_team ON academy_team_players(team_id);
        CREATE INDEX IF NOT EXISTS idx_team_players_player ON academy_team_players(player_id);
        CREATE INDEX IF NOT EXISTS idx_team_players_status ON academy_team_players(status);

        CREATE TABLE IF NOT EXISTS academy_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            team_id BIGINT NOT NULL,
            opponent TEXT NOT NULL,
            match_date TEXT NOT NULL,
            start_time TEXT,
            venue TEXT,
            competition TEXT,
            match_type TEXT,
            status TEXT NOT NULL DEFAULT 'scheduled',
            result TEXT,
            our_score TEXT,
            opponent_score TEXT,
            result_summary TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(team_id) REFERENCES academy_teams(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_academy_matches_team ON academy_matches(team_id);
        CREATE INDEX IF NOT EXISTS idx_academy_matches_date ON academy_matches(match_date);
        CREATE INDEX IF NOT EXISTS idx_academy_matches_status ON academy_matches(status);

        CREATE TABLE IF NOT EXISTS academy_match_squad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            squad_role TEXT NOT NULL DEFAULT 'player',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(match_id) REFERENCES academy_matches(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            UNIQUE(match_id, player_id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_squad_match ON academy_match_squad(match_id);
        CREATE INDEX IF NOT EXISTS idx_match_squad_player ON academy_match_squad(player_id);

        CREATE TABLE IF NOT EXISTS academy_match_player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            batting_runs INTEGER NOT NULL DEFAULT 0,
            balls_faced INTEGER NOT NULL DEFAULT 0,
            fours INTEGER NOT NULL DEFAULT 0,
            sixes INTEGER NOT NULL DEFAULT 0,
            dismissal TEXT,
            bowling_overs TEXT,
            maidens INTEGER NOT NULL DEFAULT 0,
            runs_conceded INTEGER NOT NULL DEFAULT 0,
            wickets INTEGER NOT NULL DEFAULT 0,
            catches INTEGER NOT NULL DEFAULT 0,
            run_outs INTEGER NOT NULL DEFAULT 0,
            stumpings INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(match_id) REFERENCES academy_matches(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            UNIQUE(match_id, player_id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_stats_match ON academy_match_player_stats(match_id);
        CREATE INDEX IF NOT EXISTS idx_match_stats_player ON academy_match_player_stats(player_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _team(team_id: int) -> dict:
    row = fetch_one(
        """
        SELECT t.*, c.first_name AS coach_first_name,c.last_name AS coach_last_name,
               (SELECT COUNT(*) FROM academy_team_players tp WHERE tp.team_id=t.id AND tp.status='active') AS active_player_count
        FROM academy_teams t LEFT JOIN coaches c ON c.id=t.coach_id WHERE t.id=?
        """,
        (team_id,),
    )
    if not row:
        raise HTTPException(404, "Team not found")
    row["coach_name"] = f"{row.get('coach_first_name') or ''} {row.get('coach_last_name') or ''}".strip() or None
    return row


def _match(match_id: int) -> dict:
    row = fetch_one(
        """
        SELECT m.*,t.name AS team_name,
               (SELECT COUNT(*) FROM academy_match_squad s WHERE s.match_id=m.id) AS squad_count,
               (SELECT COUNT(*) FROM academy_match_player_stats ps WHERE ps.match_id=m.id) AS stats_count
        FROM academy_matches m JOIN academy_teams t ON t.id=m.team_id WHERE m.id=?
        """,
        (match_id,),
    )
    if not row:
        raise HTTPException(404, "Match not found")
    return row


def _validate_team_player(conn, team_id: int, player_id: int) -> None:
    row = conn.execute(
        "SELECT id FROM academy_team_players WHERE team_id=? AND player_id=? AND status='active'",
        (team_id, player_id),
    ).fetchone()
    if not row:
        raise HTTPException(409, "Match squad players must be active members of the selected team")


_ensure_tables()


@router.get("/teams")
def teams():
    rows = fetch_all("SELECT id FROM academy_teams ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END,name COLLATE NOCASE")
    return [_team(int(row["id"])) for row in rows]


@router.get("/teams/{team_id}")
def team(team_id: int):
    return _team(team_id)


@router.post("/teams", status_code=201)
def create_team(payload: TeamPayload):
    name = _clean(payload.name) or ""
    with connection() as conn:
        if conn.execute("SELECT id FROM academy_teams WHERE name=? COLLATE NOCASE", (name,)).fetchone():
            raise HTTPException(409, "A team with this name already exists")
        if payload.coach_id is not None:
            coach = conn.execute("SELECT id,status FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
            if not coach:
                raise HTTPException(404, "Coach not found")
            if str(coach["status"] or "active") != "active":
                raise HTTPException(409, "Only an active coach can be assigned to a team")
        created = conn.execute(
            """
            INSERT INTO academy_teams(academy_id,name,age_group,level,coach_id,status,notes)
            VALUES(?,?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn),name,_clean(payload.age_group),_clean(payload.level),payload.coach_id,payload.status,_clean(payload.notes)),
        ).fetchone()
        team_id = int(created["id"])
    return _team(team_id)


@router.put("/teams/{team_id}")
def update_team(team_id: int, payload: TeamPayload):
    name = _clean(payload.name) or ""
    with connection() as conn:
        if not conn.execute("SELECT id FROM academy_teams WHERE id=?", (team_id,)).fetchone():
            raise HTTPException(404, "Team not found")
        duplicate = conn.execute("SELECT id FROM academy_teams WHERE name=? COLLATE NOCASE AND id<>?", (name,team_id)).fetchone()
        if duplicate:
            raise HTTPException(409, "A team with this name already exists")
        conn.execute(
            "UPDATE academy_teams SET name=?,age_group=?,level=?,coach_id=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (name,_clean(payload.age_group),_clean(payload.level),payload.coach_id,payload.status,_clean(payload.notes),team_id),
        )
    return _team(team_id)


@router.get("/teams/{team_id}/players")
def team_players(team_id: int):
    _team(team_id)
    return fetch_all(
        """
        SELECT tp.*,p.name AS player_name,p.status AS player_status
        FROM academy_team_players tp JOIN players p ON p.id=tp.player_id
        WHERE tp.team_id=? ORDER BY CASE WHEN tp.status='active' THEN 0 ELSE 1 END,p.name COLLATE NOCASE
        """,
        (team_id,),
    )


@router.post("/teams/{team_id}/players", status_code=201)
def add_team_player(team_id: int, payload: TeamPlayerPayload):
    _team(team_id)
    with connection() as conn:
        player = conn.execute("SELECT id,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if str(player["status"] or "active") != "active":
            raise HTTPException(409, "Only active players can be added to a team")
        current = conn.execute(
            "SELECT id FROM academy_team_players WHERE team_id=? AND player_id=? AND status='active'",
            (team_id,payload.player_id),
        ).fetchone()
        if current:
            raise HTTPException(409, "Player is already an active member of this team")
        created = conn.execute(
            "INSERT INTO academy_team_players(team_id,player_id,team_role,status,joined_on) VALUES(?,?,?,'active',?) RETURNING id",
            (team_id,payload.player_id,payload.team_role,_clean(payload.joined_on)),
        ).fetchone()
        membership_id = int(created["id"])
    return fetch_one(
        "SELECT tp.*,p.name AS player_name FROM academy_team_players tp JOIN players p ON p.id=tp.player_id WHERE tp.id=?",
        (membership_id,),
    )


@router.get("/matches")
def matches(team_id: int | None = None):
    sql = "SELECT id FROM academy_matches WHERE 1=1"
    params: list[object] = []
    if team_id is not None:
        sql += " AND team_id=?"
        params.append(team_id)
    sql += " ORDER BY match_date DESC,id DESC"
    rows = fetch_all(sql, params)
    return [_match(int(row["id"])) for row in rows]


@router.get("/matches/{match_id}")
def match(match_id: int):
    return _match(match_id)


@router.post("/matches", status_code=201)
def create_match(payload: MatchPayload):
    _team(payload.team_id)
    with connection() as conn:
        created = conn.execute(
            """
            INSERT INTO academy_matches(academy_id,team_id,opponent,match_date,start_time,venue,competition,match_type,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn),payload.team_id,_clean(payload.opponent),payload.match_date,_clean(payload.start_time),_clean(payload.venue),
             _clean(payload.competition),_clean(payload.match_type),payload.status,_clean(payload.notes)),
        ).fetchone()
        match_id = int(created["id"])
    return _match(match_id)


@router.put("/matches/{match_id}")
def update_match(match_id: int, payload: MatchPayload):
    _match(match_id)
    _team(payload.team_id)
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_matches SET team_id=?,opponent=?,match_date=?,start_time=?,venue=?,competition=?,match_type=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (payload.team_id,_clean(payload.opponent),payload.match_date,_clean(payload.start_time),_clean(payload.venue),_clean(payload.competition),
             _clean(payload.match_type),payload.status,_clean(payload.notes),match_id),
        )
    return _match(match_id)


@router.get("/matches/{match_id}/squad")
def match_squad(match_id: int):
    _match(match_id)
    return fetch_all(
        """
        SELECT s.*,p.name AS player_name
        FROM academy_match_squad s JOIN players p ON p.id=s.player_id
        WHERE s.match_id=? ORDER BY CASE WHEN s.squad_role='captain' THEN 0 ELSE 1 END,p.name COLLATE NOCASE
        """,
        (match_id,),
    )


@router.put("/matches/{match_id}/squad")
def save_match_squad(match_id: int, payload: SquadPayload):
    match_row = _match(match_id)
    player_ids = [entry.player_id for entry in payload.players]
    if len(player_ids) != len(set(player_ids)):
        raise HTTPException(422, "Duplicate player appears in match squad")
    with connection() as conn:
        for player_id in player_ids:
            _validate_team_player(conn, int(match_row["team_id"]), player_id)
        conn.execute("DELETE FROM academy_match_squad WHERE match_id=?", (match_id,))
        for entry in payload.players:
            conn.execute(
                "INSERT INTO academy_match_squad(match_id,player_id,squad_role) VALUES(?,?,?)",
                (match_id,entry.player_id,entry.squad_role),
            )
    return match_squad(match_id)


@router.get("/matches/{match_id}/stats")
def match_stats(match_id: int):
    _match(match_id)
    return fetch_all(
        """
        SELECT ps.*,p.name AS player_name
        FROM academy_match_player_stats ps JOIN players p ON p.id=ps.player_id
        WHERE ps.match_id=? ORDER BY p.name COLLATE NOCASE
        """,
        (match_id,),
    )


@router.put("/matches/{match_id}/result")
def save_match_result(match_id: int, payload: MatchResultPayload):
    _match(match_id)
    player_ids = [stat.player_id for stat in payload.player_stats]
    if len(player_ids) != len(set(player_ids)):
        raise HTTPException(422, "Duplicate player appears in match statistics")
    with connection() as conn:
        squad_ids = {int(row["player_id"]) for row in conn.execute("SELECT player_id FROM academy_match_squad WHERE match_id=?", (match_id,)).fetchall()}
        for player_id in player_ids:
            if player_id not in squad_ids:
                raise HTTPException(409, "Player statistics can only be recorded for selected squad players")
        conn.execute(
            """
            UPDATE academy_matches SET status='completed',result=?,our_score=?,opponent_score=?,result_summary=?,updated_at=CURRENT_TIMESTAMP WHERE id=?
            """,
            (payload.result,_clean(payload.our_score),_clean(payload.opponent_score),_clean(payload.result_summary),match_id),
        )
        for stat in payload.player_stats:
            existing = conn.execute("SELECT id FROM academy_match_player_stats WHERE match_id=? AND player_id=?", (match_id,stat.player_id)).fetchone()
            values = (
                stat.batting_runs,stat.balls_faced,stat.fours,stat.sixes,_clean(stat.dismissal),_clean(stat.bowling_overs),
                stat.maidens,stat.runs_conceded,stat.wickets,stat.catches,stat.run_outs,stat.stumpings,_clean(stat.notes),
            )
            if existing:
                conn.execute(
                    """
                    UPDATE academy_match_player_stats SET batting_runs=?,balls_faced=?,fours=?,sixes=?,dismissal=?,bowling_overs=?,maidens=?,
                        runs_conceded=?,wickets=?,catches=?,run_outs=?,stumpings=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?
                    """,
                    (*values,int(existing["id"])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO academy_match_player_stats(match_id,player_id,batting_runs,balls_faced,fours,sixes,dismissal,bowling_overs,maidens,
                        runs_conceded,wickets,catches,run_outs,stumpings,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (match_id,stat.player_id,*values),
                )
    return {"match":_match(match_id),"stats":match_stats(match_id)}


@router.get("/players/{player_id}/match-history")
def player_match_history(player_id: int):
    player = fetch_one("SELECT id,name FROM players WHERE id=?", (player_id,))
    if not player:
        raise HTTPException(404, "Player not found")
    return fetch_all(
        """
        SELECT m.id AS match_id,m.match_date,m.opponent,m.competition,m.match_type,m.result,m.our_score,m.opponent_score,
               t.name AS team_name,s.squad_role,
               ps.batting_runs,ps.balls_faced,ps.fours,ps.sixes,ps.dismissal,ps.bowling_overs,ps.maidens,ps.runs_conceded,
               ps.wickets,ps.catches,ps.run_outs,ps.stumpings,ps.notes AS stats_notes
        FROM academy_match_squad s
        JOIN academy_matches m ON m.id=s.match_id
        JOIN academy_teams t ON t.id=m.team_id
        LEFT JOIN academy_match_player_stats ps ON ps.match_id=m.id AND ps.player_id=s.player_id
        WHERE s.player_id=? ORDER BY m.match_date DESC,m.id DESC
        """,
        (player_id,),
    )
