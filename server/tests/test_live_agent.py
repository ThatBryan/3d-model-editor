"""Opt-in: a real Claude call (local Claude Code login) driving the editor tools on a fixture
project with the fake builder. Run with:  server/.venv/bin/python -m pytest server/tests -m live -q -s
"""
import pytest

from app.agent import ClaudeAgentRunner
from conftest import create_ready, wait_job


@pytest.mark.live
def test_real_agent_moves_a_part_through_tools(make_client):
    c = make_client(agent=ClaudeAgentRunner(model="claude-opus-5-5", max_turns=12, timeout_s=300))
    p = create_ready(c)
    body = c.post(f"/api/projects/{p['id']}/pins", json={
        "part": "Roof__Searchlight", "point": [2, 4.5, 0], "text": "Raise this 0.5 m.", "author": "You"}).json()
    job = wait_job(c, body["job_id"], timeout=300)
    print("\n".join(job["log"][-25:]))
    assert job["status"] == "done", job
    proj = c.get(f"/api/projects/{p['id']}").json()
    off = proj["spec"]["overrides"]["Roof__Searchlight"]["offset_m"]
    assert off[2] == pytest.approx(0.5) and off[0] == pytest.approx(0) and off[1] == pytest.approx(0)
    assert proj["version"] == 2
    pin = proj["pins"][0]
    assert pin["status"] in ("waiting", "resolved") and pin["after_version"] == 2
    print("AI reply:", pin["messages"][-1]["text"])
