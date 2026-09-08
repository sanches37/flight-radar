from datetime import date
from pathlib import Path
from tempfile import mkdtemp

from conftest import make_insight, make_quote

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


def test_a_shallow_dip_is_not_a_drop_but_is_still_a_record_low(route):
    """2026-09-08: 최저를 경신했는데 10%에 못 미쳐 아무것도 발사되지 않았다."""
    history = [make_quote(2_000_000, date(2026, 8, 10))]
    fresh = [make_quote(1_850_000, TODAY)]

    alerts = find_alerts(route, fresh, history, today=TODAY)

    assert [alert.reason for alert in alerts] == ["low"]
    assert alerts[0].baseline_krw == 2_000_000


def test_a_wobble_below_the_margin_is_not_a_record_worth_sending(route):
    """매일 수집하는 노선에서 몇 천 원 갱신까지 알리면 알림을 끄게 된다."""
    history = [make_quote(2_000_000, date(2026, 8, 10))]
    fresh = [make_quote(1_997_000, TODAY)]

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


ABOVE_TARGET = 1_500_000
AT_ITS_LOW = make_insight((1_800_000,) * 20 + (1_100_000,))
MID_RANGE = make_insight((1_000_000,) * 10 + (1_800_000,) * 10 + (1_400_000,))


def test_alerts_when_the_date_pair_sits_at_the_bottom_of_its_own_history(route):
    fresh = [make_quote(ABOVE_TARGET, TODAY)]

    alerts = find_alerts(route, fresh, [], TODAY, insights=[AT_ITS_LOW])

    assert [alert.reason for alert in alerts] == ["percentile"]
    assert alerts[0].market.percentile == 0.0


def test_a_typical_price_is_not_a_buy_signal(route):
    fresh = [make_quote(ABOVE_TARGET, TODAY)]

    assert find_alerts(route, fresh, [], TODAY, insights=[MID_RANGE]) == []


def test_reaching_target_outranks_the_percentile_signal(route):
    fresh = [make_quote(1_350_000, TODAY)]

    alerts = find_alerts(route, fresh, [], TODAY, insights=[AT_ITS_LOW])

    assert [alert.reason for alert in alerts] == ["target"]
    assert alerts[0].market.percentile == 0.0


def test_the_percentile_signal_outranks_a_ten_percent_drop(route):
    """Sixty days of daily history says more than a thirty-day minimum."""
    history = [make_quote(1_700_000, date(2026, 8, 10))]
    fresh = [make_quote(ABOVE_TARGET, TODAY)]

    alerts = find_alerts(route, fresh, history, TODAY, insights=[AT_ITS_LOW])

    assert [alert.reason for alert in alerts] == ["percentile"]


def test_a_cheaper_date_pair_cancels_another_pairs_record_low(route):
    """Every watched pair is a candidate, so the cheapest one sets the bar."""
    cheaper_until_today = make_insight(
        (900_000,) * 20 + (1_500_000,), return_date=date(2026, 10, 16)
    )
    fresh = [make_quote(ABOVE_TARGET, TODAY)]

    assert find_alerts(route, fresh, [], TODAY, insights=[AT_ITS_LOW, cheaper_until_today]) == []


def test_alerting_still_works_when_no_curve_came_back(route):
    """Google may drop the insights block; target and drop must survive it."""
    alerts = find_alerts(route, [make_quote(1_350_000, TODAY)], [], TODAY)

    assert [alert.reason for alert in alerts] == ["target"]
    assert alerts[0].market is None


def test_a_record_low_is_not_hidden_by_an_earlier_alert_in_the_same_band(route):
    """실제 사고 재현: 9/3에 139.9만 목표가 알림 → 9/8 136.5만이 같은 27번
    구간이라 7일 차단에 걸려 조용히 사라졌다. 최저 경신은 구간으로 묶지 않는다.
    """
    state = Path(mkdtemp()) / "alerts.json"
    baseline = [make_quote(1_399_000, date(2026, 9, 2))]

    first = find_alerts(route, [make_quote(1_399_000, date(2026, 9, 3))], [], date(2026, 9, 3))
    record_sent(first, state, date(2026, 9, 3))

    later = find_alerts(route, [make_quote(1_365_000, TODAY)], baseline, TODAY)

    # 두 알림 모두 목표가 도달이고 같은 5만원 구간(27번)이다. 그래도 뒤엣것은
    # 직전 최저를 깼으므로 구간이 아니라 정확한 가격으로 기록돼 살아남는다.
    assert [alert.reason for alert in later] == ["target"]
    assert later[0].baseline_krw == 1_399_000
    assert suppress_repeats(later, state, TODAY) == later


def test_the_same_record_is_not_sent_twice(route):
    state = Path(mkdtemp()) / "alerts.json"
    history = [make_quote(2_000_000, date(2026, 8, 10))]
    alerts = find_alerts(route, [make_quote(1_850_000, TODAY)], history, TODAY)

    record_sent(alerts, state, TODAY)

    assert suppress_repeats(alerts, state, TODAY) == []
