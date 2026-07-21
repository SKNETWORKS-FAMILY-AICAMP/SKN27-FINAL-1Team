from app.backend.services import calendar_job


def test_calendar_job_entrypoint_runs_exactly_one_batch(monkeypatch):
    calls = []

    async def fake_sync():
        calls.append("sync")

    monkeypatch.setattr(calendar_job, "sync_daily_calendar_events", fake_sync)

    calendar_job.main()

    assert calls == ["sync"]
