"""Drop evaluation (FR-7) and alert text (FR-8): pure functions."""

from datetime import datetime, timezone

import pytest

from shopping_assistant.alerts import (
    alert_facts,
    alert_reason,
    alert_subject,
    percent_below,
    should_alert,
    template_alert,
)
from shopping_assistant.models import PriceCheck, TrackedItem

INF = None  # last_notified NULL


@pytest.mark.parametrize(
    "price, in_stock, target, prev_low, last_notified, reason",
    [
        # target reached
        (400.0, True, 400.0, 449.99, INF, "target_reached"),   # exactly at target
        (399.0, True, 400.0, 449.99, INF, "target_reached"),
        (399.0, True, 400.0, 380.0, INF, "target_reached"),    # at target but not a new low: still alerts
        # new low above target
        (420.0, True, 400.0, 449.99, INF, "new_low"),
        (449.99, True, 400.0, 449.99, INF, None),              # equal to previous low: not new
        (460.0, True, 400.0, 449.99, INF, None),               # price went up
        # out of stock never alerts (BRL-4)
        (350.0, False, 400.0, 449.99, INF, None),
        # duplicate suppression (US-15)
        (399.0, True, 400.0, 449.99, 399.0, None),              # same price as last alert
        (410.0, True, 400.0, 449.99, 399.0, None),              # new low vs previous_lowest? no: above last alert
        (398.0, True, 400.0, 399.0, 399.0, "target_reached"),  # dropped further below last alert
        (430.0, True, 400.0, 435.0, 440.0, "new_low"),          # below last alert and a new low
    ],
)
def test_alert_reason_table(price, in_stock, target, prev_low, last_notified, reason):
    assert alert_reason(price, in_stock, target, prev_low, last_notified) == reason
    assert should_alert(price, in_stock, target, prev_low, last_notified) is (reason is not None)


def test_percent_below():
    assert percent_below(500.0, 450.0) == 10.0
    assert percent_below(449.99, 399.0) == 11.3
    assert percent_below(400.0, 420.0) == -5.0
    assert percent_below(0, 10) == 0.0


def make_check(price=399.0, previous_price=449.99, previous_lowest=449.99, reason="target_reached", **item_kw):
    item = TrackedItem(
        id=7, product_name="Sony WH-1000XM6", retailer="Amazon.ca",
        url="https://www.amazon.ca/dp/B0F3PQHWTZ", initial_price=478.0, target_price=430.2,
        lowest_price_seen=449.99, created_at=datetime.now(timezone.utc), **item_kw,
    )
    return PriceCheck(item=item, price=price, in_stock=True, previous_price=previous_price,
                      previous_lowest=previous_lowest, reason=reason)


def test_alert_facts_precompute_every_number():
    f = alert_facts(make_check())
    assert f["new_price"] == "CA$399.00"
    assert f["previous_price"] == "CA$449.99"
    assert f["price_when_tracking_started"] == "CA$478.00"
    assert f["percent_below_start"] == 16.5
    assert f["target_price"] == "CA$430.20"
    assert f["is_new_all_time_low"] is True
    assert f["url"] == "https://www.amazon.ca/dp/B0F3PQHWTZ"


def test_subject_by_reason():
    assert alert_subject(make_check()) == "Target price reached: Sony WH-1000XM6 now CA$399.00 at Amazon.ca"
    assert alert_subject(make_check(reason="new_low")).startswith("New low price:")


def test_template_alert_contains_required_facts():
    body = template_alert(make_check())
    for expected in ("Sony WH-1000XM6 is now CA$399.00 at Amazon.ca.", "Previous check: CA$449.99.",
                     "16.5% below CA$478.00", "at or below your target of CA$430.20",
                     "lowest price seen so far (previous low CA$449.99)", "Link: https://www.amazon.ca/dp/B0F3PQHWTZ"):
        assert expected in body


def test_template_alert_new_low_above_target():
    body = template_alert(make_check(price=440.0, reason="new_low"))
    assert "target" not in body and "lowest price seen so far" in body
