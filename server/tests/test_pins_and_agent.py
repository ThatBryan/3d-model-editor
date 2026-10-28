import json

from app.agent import ScriptedAgent, validate_research
from conftest import create_ready, wait_job

OVERRIDE = ("set_part_override", {"part": "Roof__Searchlight", "override": {"offset_m": [0, 0, 0.5]}})


def test_pin_lifecycle_change_then_waiting(make_client):
    agent = ScriptedAgent([("get_project", {}), OVERRIDE, ("rebuild", {}),
                           ("reply_to_pin", {"pin_id": "{pin_id}", "text": "Raised it 0.5 m.", "status": "waiting"})],
                          reply="Raised it 0.5 m.")
    c = make_client(agent=agent)
    p = create_ready(c)
    body = c.post(f"/api/projects/{p['id']}/pins", json={
        "part": "Roof__Searchlight", "point": [2, 4.5, 0], "text": "raise this a bit", "author": "You"}).json()
    assert body["pin"]["status"] == "working" and body["pin"]["before_version"] == 1
    job = wait_job(c, body["job_id"])
    assert job["status"] == "done", job
    pin = c.get(f"/api/projects/{p['id']}").json()["pins"][0]
    assert pin["status"] == "waiting"
    assert (pin["before_version"], pin["after_version"]) == (1, 2)
    assert [m["who"] for m in pin["messages"]] == ["You", "AI"]  # reply posted once, not twice
    prompt = agent.prompts[0]
    assert "`Roof__Searchlight`" in prompt and "Roof › Searchlight" in prompt and "raise this a bit" in prompt
    assert "[2.0, 0.0, 4.5]" in prompt  # the click, converted into the ship frame
    spec = c.get(f"/api/projects/{p['id']}").json()["spec"]
    assert spec["overrides"]["Roof__Searchlight"] == {"offset_m": [0, 0, 0.5]}
    # user reply re-runs the agent on the same pin
    job = wait_job(c, c.post(f"/api/projects/{p['id']}/pins/{pin['id']}/reply", json={"text": "more"}).json()["job_id"])
    assert job["status"] == "done"
    pin = c.patch(f"/api/projects/{p['id']}/pins/{pin['id']}", json={"status": "resolved"}).json()["pin"]
    assert pin["status"] == "resolved" and pin["messages"][2]["text"] == "more"


def test_pin_resolved_without_change(make_client):
    agent = ScriptedAgent([("reply_to_pin", {"pin_id": "{pin_id}", "text": "Already 4.5 m, matches the research.",
                                              "status": "resolved"})])
    c = make_client(agent=agent)
    p = create_ready(c)
    wait_job(c, c.post(f"/api/projects/{p['id']}/pins", json={"part": "Roof__Searchlight", "text": "too low?"}).json()["job_id"])
    pin = c.get(f"/api/projects/{p['id']}").json()["pins"][0]
    assert pin["status"] == "resolved" and pin["after_version"] is None
    assert c.get(f"/api/projects/{p['id']}").json()["version"] == 1


def test_unbuilt_agent_edits_are_rebuilt_and_reply_lands_on_pin(make_client):
    agent = ScriptedAgent([OVERRIDE], reply="Moved it up.")  # forgot to rebuild, forgot reply_to_pin
    c = make_client(agent=agent)
    p = create_ready(c)
    job = wait_job(c, c.post(f"/api/projects/{p['id']}/pins", json={"part": "Roof__Searchlight", "text": "up"}).json()["job_id"])
    assert job["status"] == "done"
    proj = c.get(f"/api/projects/{p['id']}").json()
    assert proj["version"] == 2
    assert proj["pins"][0]["status"] == "waiting" and proj["pins"][0]["messages"][-1] == {
        **proj["pins"][0]["messages"][-1], "who": "AI", "text": "Moved it up."}


def test_failed_agent_rebuild_is_reported_in_reply(make_client):
    agent = ScriptedAgent([("set_params", {"patch": {"fail": "keel below draught"}}), ("rebuild", {})], reply="Done.")
    c = make_client(agent=agent)
    p = create_ready(c)
    job = wait_job(c, c.post(f"/api/projects/{p['id']}/chat", json={"message": "break it", "mode": "build"}).json()["job_id"])
    assert job["status"] == "done"
    assert "keel below draught" in job["result"]["reply"] and job["result"]["version"] == 1
    msgs = c.get(f"/api/projects/{p['id']}").json()["messages"]
    assert [m["who"] for m in msgs] == ["You", "AI"]


def test_tools_refuse_bad_input(make_client):
    agent = ScriptedAgent([
        ("set_part_override", {"part": "Roof__Searchlite", "override": {"offset_m": [0, 0, 1]}}),
        ("set_params", {"patch": {"funnel_height_m": 9}}),
        ("set_params", {"patch": {"loa_m": 5000}}),
        ("add_custom_op", {"description": "x", "code": "import os\nos.system('rm -rf ~')"}),
        ("add_custom_op", {"description": "horn", "code": "o = bpy.data.objects.new('my horn', None)\no.name = 'my horn'"}),
        ("set_joint_limits", {"part": "Hull__Main", "min_deg": -10, "max_deg": 10}),
        ("set_body", {"patch": {"height_cm": 190}}),  # crew tool on a ship
        ("save_research", {"research": {}}),  # research tool in build mode
        ("add_custom_op", {"description": "horn", "code": "o = me3d.box('Mast__Horn', size=(0.2,0.2,0.2))"}),
    ])
    c = make_client(agent=agent)
    p = create_ready(c)
    wait_job(c, c.post(f"/api/projects/{p['id']}/chat", json={"message": "x"}).json()["job_id"])
    errs = [e for _, _, e in agent.results]
    assert errs == [True, True, True, True, True, True, True, True, False], agent.results
    assert "Did you mean: Roof__Searchlight" in agent.results[0][1]
    spec = c.get(f"/api/projects/{p['id']}").json()["spec"]
    assert [o["id"] for o in spec["custom_ops"]] == ["op_1"]


def test_crew_tools_validate_against_catalog(make_client):
    agent = ScriptedAgent([
        ("set_clothes", {"patch": {"hat": "cap01"}}),
        ("set_clothes", {"patch": {"hat": "tiara"}}),
        ("set_equipment", {"equipment": ["binoculars"]}),
        ("set_equipment", {"equipment": ["rifle"]}),
        ("set_animations", {"animations": ["idle", "squat"]}),
        ("set_body", {"patch": {"height_cm": 240}}),
        ("set_body", {"patch": {"height_cm": 185}}),
        ("rebuild", {}),
    ])
    c = make_client(agent=agent)
    p = create_ready(c, "crew", "male_default")
    wait_job(c, c.post(f"/api/projects/{p['id']}/chat", json={"message": "x"}).json()["job_id"])
    assert [e for _, _, e in agent.results] == [False, True, False, True, False, True, False, False]
    spec = c.get(f"/api/projects/{p['id']}").json()["spec"]
    assert spec["clothes"]["hat"] == "cap01" and spec["equipment"] == ["binoculars"]
    assert spec["body"]["height_cm"] == 185


GOOD_RESEARCH = {
    "subject": "PCG PC 303", "summary": {"verdict": "Buildable from photos.", "existing_work": "none"},
    "sources": [{"id": "s1", "title": "MINDEF", "url": "https://example", "status": "Official", "what_it_proves": "length"}],
    "claims": [{"claim": "LOA 18 m", "sources": ["s1"], "status": "Official", "consequence_for_model": "loa_m=18"}],
    "open_questions": [], "articulation": [{"part": "Roof__Searchlight", "motion": "yaw", "priority": "P1"}],
}


def test_research_validation():
    assert validate_research(GOOD_RESEARCH) == []
    bad = json.loads(json.dumps(GOOD_RESEARCH))
    bad["sources"][0]["status"] = "Verified"
    bad["claims"][0]["sources"] = ["s9"]
    del bad["claims"][0]["consequence_for_model"]
    errs = validate_research(bad)
    assert len(errs) == 3, errs


def test_research_mode_saves_research_and_builds_nothing(make_client):
    agent = ScriptedAgent([("set_params", {"patch": {"loa_m": 100}}), ("save_research", {"research": GOOD_RESEARCH})])
    c = make_client(agent=agent)
    p = create_ready(c)
    job = wait_job(c, c.post(f"/api/projects/{p['id']}/chat", json={"message": "research PC 303", "mode": "research"}).json()["job_id"])
    assert job["result"]["research_saved"] is True
    assert agent.results[0][2] is True  # build tools are not available in research mode
    proj = c.get(f"/api/projects/{p['id']}").json()
    assert proj["research"]["subject"] == "PCG PC 303" and proj["version"] == 1
