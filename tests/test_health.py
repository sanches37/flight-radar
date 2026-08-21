from datetime import date

from flight_radar.health import EMPTY_RUNS_BEFORE_ALERT, record_run

TODAY = date(2026, 8, 21)


def test_a_single_empty_run_is_not_worth_alerting(tmp_path):
    assert record_run(tmp_path / "health.json", collected=0, today=TODAY) is None


def test_warns_once_the_empty_streak_reaches_the_threshold(tmp_path):
    path = tmp_path / "health.json"
    for _ in range(EMPTY_RUNS_BEFORE_ALERT - 1):
        record_run(path, collected=0, today=TODAY)

    warning = record_run(path, collected=0, today=TODAY)

    assert warning is not None
    assert "0건" in warning


def test_keeps_warning_while_collection_stays_dead(tmp_path):
    """A lone warning lost to a failed post is the silence this guards against."""
    path = tmp_path / "health.json"
    for _ in range(EMPTY_RUNS_BEFORE_ALERT):
        record_run(path, collected=0, today=TODAY)

    assert record_run(path, collected=0, today=TODAY) is not None


def test_a_successful_run_clears_the_streak(tmp_path):
    path = tmp_path / "health.json"
    for _ in range(EMPTY_RUNS_BEFORE_ALERT):
        record_run(path, collected=0, today=TODAY)

    assert record_run(path, collected=222, today=TODAY) is None
    assert record_run(path, collected=0, today=TODAY) is None


def test_warning_names_the_last_successful_collection(tmp_path):
    path = tmp_path / "health.json"
    record_run(path, collected=222, today=date(2026, 8, 19))
    for _ in range(EMPTY_RUNS_BEFORE_ALERT - 1):
        record_run(path, collected=0, today=TODAY)

    warning = record_run(path, collected=0, today=TODAY)

    assert "2026-08-19" in warning
