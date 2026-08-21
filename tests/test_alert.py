from datetime import date

from conftest import make_quote

from flight_radar.alert import find_alerts, record_sent, suppress_repeats

TODAY = date(2026, 8, 21)


def test_alerts_when_price_reaches_target(route):
    fresh = [make_quote(1_350_000, TODAY)]

    alerts = find_alerts(route, fresh, history=[], today=TODAY)

    assert [alert.reason for alert in alerts] == ["target"]


def test_silent_above_target_without_history(route):
    fresh = [make_quote(1_800_000, TODAY)]

    assert find_alerts(route, fresh, history=[], today=TODAY) == []


def test_alerts_on_ten_percent_drop_against_recent_low(route):
    history = [make_quote(2_000_000, date(2026, 8, 10))]
    fresh = [make_quote(1_790_000, TODAY)]

    alerts = find_alerts(route, fresh, history, today=TODAY)

    assert [alert.reason for alert in alerts] == ["drop"]
    assert alerts[0].baseline_krw == 2_000_000


def test_shallow_dip_is_not_a_drop(route):
    history = [make_quote(2_000_000, date(2026, 8, 10))]
    fresh = [make_quote(1_850_000, TODAY)]

    assert find_alerts(route, fresh, history, today=TODAY) == []


def test_history_older_than_window_is_ignored(route):
    history = [make_quote(2_000_000, date(2026, 6, 1))]
    fresh = [make_quote(1_790_000, TODAY)]

    assert find_alerts(route, fresh, history, today=TODAY) == []


def test_constraint_violating_quotes_never_alert(route):
    fresh = [make_quote(900_000, TODAY, stops=3, duration_minutes=2000)]

    assert find_alerts(route, fresh, history=[], today=TODAY) == []


def test_baseline_ignores_constraint_violating_history(route):
    """A cheap 3-stop fare must not become the bar a compliant fare is judged against."""
    history = [make_quote(800_000, date(2026, 8, 10), stops=3, duration_minutes=2000)]
    fresh = [make_quote(1_500_000, TODAY)]

    assert find_alerts(route, fresh, history, today=TODAY) == []


def test_reports_only_the_cheapest_eligible_quote(route):
    fresh = [make_quote(1_390_000, TODAY), make_quote(1_200_000, TODAY), make_quote(1_350_000, TODAY)]

    alerts = find_alerts(route, fresh, history=[], today=TODAY)

    assert len(alerts) == 1
    assert alerts[0].quote.price_krw == 1_200_000


def test_repeat_alert_is_suppressed_within_a_week(tmp_path, route):
    state = tmp_path / "alerts.json"
    alerts = find_alerts(route, [make_quote(1_350_000, TODAY)], history=[], today=TODAY)
    record_sent(alerts, state, TODAY)

    assert suppress_repeats(alerts, state, date(2026, 8, 25)) == []


def test_alert_resumes_after_the_quiet_period(tmp_path, route):
    state = tmp_path / "alerts.json"
    alerts = find_alerts(route, [make_quote(1_350_000, TODAY)], history=[], today=TODAY)
    record_sent(alerts, state, TODAY)

    assert len(suppress_repeats(alerts, state, date(2026, 9, 1))) == 1


def test_meaningfully_lower_price_breaks_through_suppression(tmp_path, route):
    state = tmp_path / "alerts.json"
    first = find_alerts(route, [make_quote(1_350_000, TODAY)], history=[], today=TODAY)
    record_sent(first, state, TODAY)

    cheaper = find_alerts(route, [make_quote(1_100_000, TODAY)], history=[], today=TODAY)

    assert len(suppress_repeats(cheaper, state, TODAY)) == 1


def test_undelivered_alert_stays_eligible(tmp_path, route):
    """Filtering must not consume the quiet period; only delivery does."""
    state = tmp_path / "alerts.json"
    alerts = find_alerts(route, [make_quote(1_350_000, TODAY)], history=[], today=TODAY)

    assert len(suppress_repeats(alerts, state, TODAY)) == 1
    assert len(suppress_repeats(alerts, state, TODAY)) == 1
