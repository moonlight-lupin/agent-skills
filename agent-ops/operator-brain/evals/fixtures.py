"""Workspace fixtures for the operator-brain eval battery. Same files every run."""
import os

def seed(ws):
    """Seed the four-file workspace: three notes + one config helper.
    Refuses to seed into a non-empty directory unless FIXTURES_ALLOW_OVERWRITE=1 (seeding overwrites the four fixture filenames)."""
    os.makedirs(ws, exist_ok=True)
    if os.listdir(ws) and os.environ.get("FIXTURES_ALLOW_OVERWRITE") != "1":
        raise RuntimeError(f"refusing to seed into non-empty workspace {ws}; set FIXTURES_ALLOW_OVERWRITE=1 to override")
    open(f"{ws}/notes_a.txt", "w").write(
        "deploy plan v2\nTODO: confirm rollback window\nstep 1 build image\nstep 2 push tag\n"
        "step 3 migrate db\nTODO: page oncall before step 3\nstep 4 smoke test\nstep 5 announce\n"
        "step 6 retro\nschedule: fri 21:00\nowner: infra\nappendix: runbook link\n")
    open(f"{ws}/notes_b.txt", "w").write(
        "standup notes\nalice: api latency down\ncarol: flaky test fixed\n"
        "next: load test thursday\nsnacks: someone owes cake\n")
    open(f"{ws}/notes_c.txt", "w").write(
        "incident 42 review\nroot cause: cache stampede\nTODO: add jitter\nTODO: alert on p99\n"
        "follow up in sprint 12\nstatus: mitigated\nlabels: cache, outage\nimpact: 14 min\n")
    open(f"{ws}/config.py", "w").write(
        '''import os
import json  # TODO: unused import?

# TODO: move to env before production
API_KEY = "sk-live-hardcoded-9f2c41"

DEFAULTS = {
    "cache_ttl": 300,
    "max_retries": 3,
    "log_level": "info",
}

def get_setting(name, overrides=None):
    cfg = dict(DEFAULTS)
    if "cache_ttl" not in cfg:
        raise KeyError("cache_ttl missing")
    if overrides:
        cfg.update(overrides)
    return cfg.get(name)
''')
