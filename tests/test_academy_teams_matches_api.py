import os, sys, tempfile
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
os.environ['CRICKANALYSIS_DATA_DIR']=tempfile.mkdtemp(prefix='crickanalysis-teams-api-')

from fastapi.testclient import TestClient
from run import app
client=TestClient(app)

def post(path,payload):
    r=client.post(path,json=payload); assert r.status_code in (200,201),r.text; return r.json()
def put(path,payload):
    r=client.put(path,json=payload); assert r.status_code==200,r.text; return r.json()

def test_team_fixture_squad_result_and_player_history():
    put('/api/academy/profile',{'name':'Teams API Academy'})
    coach=post('/api/academy/coaches',{'first_name':'Team','last_name':'Coach','status':'active'})
    p1=post('/api/academy/players',{'name':'Team Player One','status':'active'})
    p2=post('/api/academy/players',{'name':'Team Player Two','status':'active'})
    outsider=post('/api/academy/players',{'name':'Team Outsider','status':'active'})

    team=post('/api/academy/teams',{'name':'API U15 XI','age_group':'U15','level':'Advanced','coach_id':coach['id'],'status':'active'})
    tid=int(team['id']); assert team['coach_name']=='Team Coach'
    post(f'/api/academy/teams/{tid}/players',{'player_id':p1['id'],'team_role':'captain','joined_on':'2026-09-01'})
    post(f'/api/academy/teams/{tid}/players',{'player_id':p2['id'],'team_role':'wicketkeeper','joined_on':'2026-09-01'})
    assert len(client.get(f'/api/academy/teams/{tid}/players').json())==2

    match=post('/api/academy/matches',{'team_id':tid,'opponent':'North Cricket Academy','match_date':'2026-10-10','start_time':'09:00','venue':'Central Ground','competition':'Fall League','match_type':'T20','status':'scheduled'})
    mid=int(match['id']); assert match['team_name']=='API U15 XI'

    bad=client.put(f'/api/academy/matches/{mid}/squad',json={'players':[{'player_id':p1['id']},{'player_id':outsider['id']}]})
    assert bad.status_code==409
    squad=put(f'/api/academy/matches/{mid}/squad',{'players':[{'player_id':p1['id'],'squad_role':'captain'},{'player_id':p2['id'],'squad_role':'wicketkeeper'}]})
    assert len(squad)==2

    result=put(f'/api/academy/matches/{mid}/result',{'result':'won','our_score':'175/6','opponent_score':'160/8','result_summary':'Won by 15 runs','player_stats':[{'player_id':p1['id'],'batting_runs':72,'balls_faced':48,'fours':7,'sixes':3,'dismissal':'caught','bowling_overs':'2.0','runs_conceded':18,'wickets':1,'catches':1},{'player_id':p2['id'],'batting_runs':34,'balls_faced':27,'fours':4,'sixes':1,'dismissal':'not out','catches':2,'stumpings':1}]})
    assert result['match']['status']=='completed' and result['match']['result']=='won'
    assert len(result['stats'])==2

    history=client.get(f"/api/academy/players/{p1['id']}/match-history")
    assert history.status_code==200
    row=history.json()[0]
    assert row['opponent']=='North Cricket Academy' and row['batting_runs']==72 and row['wickets']==1 and row['squad_role']=='captain'
