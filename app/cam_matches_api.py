from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam", tags=["cam-teams-matches"])


class TeamPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=40)
    age_group: str | None = Field(default=None, max_length=80)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = Field(default=None, max_length=1500)


class TeamRosterPayload(BaseModel):
    player_id: int = Field(gt=0)
    role: str | None = Field(default="player", max_length=60)
    jersey_number: str | None = Field(default=None, max_length=20)
    joined_on: str | None = Field(default=None, max_length=20)


class FixturePayload(BaseModel):
    team_id: int = Field(gt=0)
    opponent: str = Field(min_length=2, max_length=160)
    match_date: str = Field(min_length=8, max_length=20)
    start_time: str | None = Field(default=None, max_length=10)
    venue: str | None = Field(default=None, max_length=240)
    competition: str | None = Field(default=None, max_length=160)
    match_format: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=1500)


class SquadPayload(BaseModel):
    player_ids: list[int] = Field(min_length=1, max_length=30)
    captain_id: int | None = Field(default=None, gt=0)
    wicketkeeper_id: int | None = Field(default=None, gt=0)


class PlayerMatchStatPayload(BaseModel):
    player_id: int = Field(gt=0)
    runs: int = Field(default=0, ge=0, le=1000)
    balls_faced: int = Field(default=0, ge=0, le=1000)
    fours: int = Field(default=0, ge=0, le=100)
    sixes: int = Field(default=0, ge=0, le=100)
    balls_bowled: int = Field(default=0, ge=0, le=1000)
    runs_conceded: int = Field(default=0, ge=0, le=1000)
    wickets: int = Field(default=0, ge=0, le=20)
    catches: int = Field(default=0, ge=0, le=20)
    stumpings: int = Field(default=0, ge=0, le=20)
    run_outs: int = Field(default=0, ge=0, le=20)


class MatchResultPayload(BaseModel):
    outcome: Literal["win", "loss", "tie", "no_result"]
    our_score: str | None = Field(default=None, max_length=80)
    opponent_score: str | None = Field(default=None, max_length=80)
    result_summary: str | None = Field(default=None, max_length=500)
    player_stats: list[PlayerMatchStatPayload] = Field(default_factory=list, max_length=30)


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
            code TEXT,
            age_group TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_teams_status ON academy_teams(status);

        CREATE TABLE IF NOT EXISTS academy_team_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            role TEXT NOT NULL DEFAULT 'player',
            jersey_number TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            joined_on TEXT,
            ended_on TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(team_id) REFERENCES academy_teams(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_team_players_team ON academy_team_players(team_id);
        CREATE INDEX IF NOT EXISTS idx_academy_team_players_player ON academy_team_players(player_id);

        CREATE TABLE IF NOT EXISTS academy_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            team_id BIGINT NOT NULL,
            opponent TEXT NOT NULL,
            match_date TEXT NOT NULL,
            start_time TEXT,
            venue TEXT,
            competition TEXT,
            match_format TEXT,
            status TEXT NOT NULL DEFAULT 'scheduled',
            outcome TEXT,
            our_score TEXT,
            opponent_score TEXT,
            result_summary TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(team_id) REFERENCES academy_teams(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_matches_team ON academy_matches(team_id);
        CREATE INDEX IF NOT EXISTS idx_academy_matches_date ON academy_matches(match_date);
        CREATE INDEX IF NOT EXISTS idx_academy_matches_status ON academy_matches(status);

        CREATE TABLE IF NOT EXISTS academy_match_squad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            is_captain INTEGER NOT NULL DEFAULT 0,
            is_wicketkeeper INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(match_id) REFERENCES academy_matches(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_match_squad_match ON academy_match_squad(match_id);
        CREATE INDEX IF NOT EXISTS idx_academy_match_squad_player ON academy_match_squad(player_id);

        CREATE TABLE IF NOT EXISTS academy_match_player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            runs INTEGER NOT NULL DEFAULT 0,
            balls_faced INTEGER NOT NULL DEFAULT 0,
            fours INTEGER NOT NULL DEFAULT 0,
            sixes INTEGER NOT NULL DEFAULT 0,
            balls_bowled INTEGER NOT NULL DEFAULT 0,
            runs_conceded INTEGER NOT NULL DEFAULT 0,
            wickets INTEGER NOT NULL DEFAULT 0,
            catches INTEGER NOT NULL DEFAULT 0,
            stumpings INTEGER NOT NULL DEFAULT 0,
            run_outs INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(match_id) REFERENCES academy_matches(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_match_stats_match ON academy_match_player_stats(match_id);
        CREATE INDEX IF NOT EXISTS idx_academy_match_stats_player ON academy_match_player_stats(player_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _team(team_id: int) -> dict:
    row = fetch_one(
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM academy_team_players tp WHERE tp.team_id=t.id AND tp.status='active') AS roster_count,
               (SELECT COUNT(*) FROM academy_matches m WHERE m.team_id=t.id) AS match_count
        FROM academy_teams t WHERE t.id=?
        """,
        (team_id,),
    )
    if not row:
        raise HTTPException(404, "Team not found")
    return row


def _match(match_id: int) -> dict:
    row = fetch_one(
        """
        SELECT m.*, t.name AS team_name,
               (SELECT COUNT(*) FROM academy_match_squad s WHERE s.match_id=m.id) AS squad_count,
               (SELECT COUNT(*) FROM academy_match_player_stats ps WHERE ps.match_id=m.id) AS stat_count
        FROM academy_matches m JOIN academy_teams t ON t.id=m.team_id WHERE m.id=?
        """,
        (match_id,),
    )
    if not row:
        raise HTTPException(404, "Match not found")
    return row


def _active_roster_ids(conn, team_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT player_id FROM academy_team_players WHERE team_id=? AND status='active'",
        (team_id,),
    ).fetchall()
    return {int(row["player_id"]) for row in rows}


_ensure_tables()


@router.get("/teams")
def teams():
    rows = fetch_all("SELECT id FROM academy_teams ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, name COLLATE NOCASE")
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
        row = conn.execute(
            """
            INSERT INTO academy_teams(academy_id,name,code,age_group,status,notes)
            VALUES(?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn), name, _clean(payload.code), _clean(payload.age_group), payload.status, _clean(payload.notes)),
        ).fetchone()
        team_id = int(row["id"])
    return _team(team_id)


@router.put("/teams/{team_id}")
def update_team(team_id: int, payload: TeamPayload):
    _team(team_id)
    name = _clean(payload.name) or ""
    with connection() as conn:
        duplicate = conn.execute("SELECT id FROM academy_teams WHERE name=? COLLATE NOCASE AND id<>?", (name, team_id)).fetchone()
        if duplicate:
            raise HTTPException(409, "A team with this name already exists")
        conn.execute(
            "UPDATE academy_teams SET name=?,code=?,age_group=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (name, _clean(payload.code), _clean(payload.age_group), payload.status, _clean(payload.notes), team_id),
        )
    return _team(team_id)


@router.get("/teams/{team_id}/roster")
def team_roster(team_id: int):
    _team(team_id)
    return fetch_all(
        """
        SELECT tp.*,p.name AS player_name,p.status AS player_status
        FROM academy_team_players tp JOIN players p ON p.id=tp.player_id
        WHERE tp.team_id=? ORDER BY CASE WHEN tp.status='active' THEN 0 ELSE 1 END,p.name COLLATE NOCASE
        """,
        (team_id,),
    )


@router.post("/teams/{team_id}/roster", status_code=201)
def add_team_player(team_id: int, payload: TeamRosterPayload):
    team_row = _team(team_id)
    if team_row["status"] != "active":
        raise HTTPException(409, "Players can only be added to an active team")
    with connection() as conn:
        player = conn.execute("SELECT id,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if str(player["status"] or "active") != "active":
            raise HTTPException(409, "Only active players can be added to a team")
        duplicate = conn.execute(
            "SELECT id FROM academy_team_players WHERE team_id=? AND player_id=? AND status='active'",
            (team_id, payload.player_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "Player is already on this team roster")
        row = conn.execute(
            """
            INSERT INTO academy_team_players(team_id,player_id,role,jersey_number,status,joined_on)
            VALUES(?,?,?,?,'active',?) RETURNING id
            """,
            (team_id, payload.player_id, _clean(payload.role) or "player", _clean(payload.jersey_number), _clean(payload.joined_on)),
        ).fetchone()
        roster_id = int(row["id"])
    return fetch_one(
        """
        SELECT tp.*,p.name AS player_name FROM academy_team_players tp JOIN players p ON p.id=tp.player_id WHERE tp.id=?
        """,
        (roster_id,),
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
def create_fixture(payload: FixturePayload):
    team_row = _team(payload.team_id)
    if team_row["status"] != "active":
        raise HTTPException(409, "Fixtures require an active team")
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO academy_matches(academy_id,team_id,opponent,match_date,start_time,venue,competition,match_format,status,notes)
            VALUES(?,?,?,?,?,?,?,?,'scheduled',?) RETURNING id
            """,
            (_academy_id(conn), payload.team_id, _clean(payload.opponent), payload.match_date, _clean(payload.start_time),
             _clean(payload.venue), _clean(payload.competition), _clean(payload.match_format), _clean(payload.notes)),
        ).fetchone()
        match_id = int(row["id"])
    return _match(match_id)


@router.get("/matches/{match_id}/squad")
def match_squad(match_id: int):
    _match(match_id)
    return fetch_all(
        """
        SELECT s.*,p.name AS player_name
        FROM academy_match_squad s JOIN players p ON p.id=s.player_id
        WHERE s.match_id=? ORDER BY s.is_captain DESC,s.is_wicketkeeper DESC,p.name COLLATE NOCASE
        """,
        (match_id,),
    )


@router.put("/matches/{match_id}/squad")
def select_match_squad(match_id: int, payload: SquadPayload):
    match_row = _match(match_id)
    unique_ids = list(dict.fromkeys(payload.player_ids))
    if payload.captain_id is not None and payload.captain_id not in unique_ids:
        raise HTTPException(422, "Captain must be selected in the squad")
    if payload.wicketkeeper_id is not None and payload.wicketkeeper_id not in unique_ids:
        raise HTTPException(422, "Wicketkeeper must be selected in the squad")
    with connection() as conn:
        roster_ids = _active_roster_ids(conn, int(match_row["team_id"]))
        invalid = [player_id for player_id in unique_ids if player_id not in roster_ids]
        if invalid:
            raise HTTPException(409, "Every squad player must be on the active team roster")
        conn.execute("DELETE FROM academy_match_squad WHERE match_id=?", (match_id,))
        for player_id in unique_ids:
            conn.execute(
                """
                INSERT INTO academy_match_squad(match_id,player_id,is_captain,is_wicketkeeper)
                VALUES(?,?,?,?)
                """,
                (match_id, player_id, 1 if player_id == payload.captain_id else 0, 1 if player_id == payload.wicketkeeper_id else 0),
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
def record_match_result(match_id: int, payload: MatchResultPayload):
    _match(match_id)
    with connection() as conn:
        squad_ids = {
            int(row["player_id"])
            for row in conn.execute("SELECT player_id FROM academy_match_squad WHERE match_id=?", (match_id,)).fetchall()
        }
        if payload.player_stats and not squad_ids:
            raise HTTPException(409, "Select the match squad before recording player statistics")
        stat_ids = [item.player_id for item in payload.player_stats]
        if len(stat_ids) != len(set(stat_ids)):
            raise HTTPException(422, "Each player may have only one statistics row")
        invalid = [player_id for player_id in stat_ids if player_id not in squad_ids]
        if invalid:
            raise HTTPException(409, "Player statistics can only be recorded for selected squad players")

        conn.execute(
            """
            UPDATE academy_matches
            SET status='completed',outcome=?,our_score=?,opponent_score=?,result_summary=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (payload.outcome, _clean(payload.our_score), _clean(payload.opponent_score), _clean(payload.result_summary), match_id),
        )
        conn.execute("DELETE FROM academy_match_player_stats WHERE match_id=?", (match_id,))
        for item in payload.player_stats:
            conn.execute(
                """
                INSERT INTO academy_match_player_stats(
                    match_id,player_id,runs,balls_faced,fours,sixes,balls_bowled,runs_conceded,wickets,catches,stumpings,run_outs
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (match_id,item.player_id,item.runs,item.balls_faced,item.fours,item.sixes,item.balls_bowled,item.runs_conceded,
                 item.wickets,item.catches,item.stumpings,item.run_outs),
            )
    return {"match": _match(match_id), "stats": match_stats(match_id), "squad": match_squad(match_id)}
