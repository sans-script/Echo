"""Offline check of the Claude usage parser: python3 test_snapshot.py (no network, no credentials)."""
from snapshot import claude_limits

r = claude_limits({
    "five_hour": {"utilization": 37.0, "resets_at": "2026-11-21T03:00:00Z"},
    "seven_day": {"utilization": 12.5, "resets_at": "2026-11-26T00:00:00Z"},
    "seven_day_opus": None, "seven_day_oauth_apps": {"utilization": 1, "resets_at": None},
    "limits": [{"kind": "weekly_all", "percent": 12.5, "resets_at": "2026-11-26T00:00:00Z"},
               {"kind": "weekly_scoped", "percent": 40, "resets_at": "2026-11-26T00:00:00Z"},
               {"kind": "monthly", "percent": 5}],  # no reset time: not shown
})
assert [x["label"] for x in r] == ["5h", "Weekly", "Model-scoped · Weekly"], r
assert r[0]["used"] == 37.0 and r[1]["used"] == 12.5 and r[2]["used"] == 40.0, r
assert claude_limits({}) == []
print("ok")
