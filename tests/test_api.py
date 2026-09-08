import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from ffrh.api import app
from ffrh.config import HUB_TOKEN

c = TestClient(app)


def test_open_pages_and_api():
    for path in ("/", "/funders", "/patterns", "/sources", "/dpdp", "/docs", "/api/v1/sources", "/api/v1/landscape",
                 "/api/v1/subareas?state=AS", "/api/v1/signals", "/api/v1/rfps", "/api/v1/ngos?state=NL", "/api/v1/themes"):
        r = c.get(path); assert r.status_code == 200, path
    top = c.get("/api/v1/funders?limit=1").json()[0]
    assert c.get(f"/api/v1/funders/{top['cin']}").json()["attributes"]
    assert c.get(f"/funders/{top['cin']}").status_code == 200
    m = c.post("/api/v1/match", json={"themes": ["livelihoods"], "state_code": "ML", "subareas": ["handloom_craft"]}).json()
    assert m["matches"][0]["reasons"][0]["evidence"][0]["retrieved_at"]
    assert c.post("/api/v1/match", json={"themes": ["livelihoods"], "state_code": "XX"}).status_code == 400


def test_hub_is_gated_then_works():
    r = c.get("/hub/team", follow_redirects=False); assert r.status_code == 303
    r = c.post("/hub/enter", data={"persona": "team", "token": "wrong"}, follow_redirects=False); assert "bad=1" in r.headers["location"]
    c.post("/hub/enter", data={"persona": "team", "token": HUB_TOKEN})
    assert c.get("/hub/team").status_code == 200
    c.post("/hub/enter", data={"persona": "advisory", "token": HUB_TOKEN})
    assert c.get("/hub/advisory").status_code == 200
    c.post("/hub/enter", data={"persona": "cso", "token": HUB_TOKEN})
    for s in range(1, 6):
        assert c.get(f"/hub/cso/standin-03?step={s}").status_code == 200, s
    r = c.post("/hub/cso/standin-03/draft", data={"funder_cin": "", "rfp_id": "1", "use_model": ""}, follow_redirects=False)
    assert r.headers["location"].startswith("/hub/draft/")
    assert c.get(r.headers["location"]).status_code == 200
