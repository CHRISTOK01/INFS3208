"""Tests for keeping nutrient-calc up to date (sync.py), with the database and nutrient-calc
replaced by fakes, so we can pretend nutrient-calc is up or down."""
from contextlib import nullcontext
from datetime import date

import httpx2

from app import sync

DAY = date(2026, 3, 1)


class FakeConn:
    """Just enough of a database connection for sync.py."""
    def transaction(self):
        return nullcontext()

    def commit(self):
        pass


def fake_repo(monkeypatch, pending_days=()):
    """Swap the database functions for fakes, and record which days get marked done."""
    done = []
    monkeypatch.setattr(sync.repo, "lock_day", lambda conn, user_id, day: None)
    monkeypatch.setattr(sync.repo, "get_day_items", lambda conn, user_id, day: [{"fdc_id": 1, "grams": 100}])
    monkeypatch.setattr(sync.repo, "mark_day_done", lambda conn, user_id, day: done.append((user_id, day)))
    monkeypatch.setattr(sync.repo, "get_pending_days", lambda conn, user_id, limit: list(pending_days))
    return done


def nutrient_calc_up(monkeypatch):
    sent = []
    monkeypatch.setattr(sync.nutrient_client, "send_day", lambda user_id, day, items: sent.append((user_id, day, items)))
    return sent


def nutrient_calc_down(monkeypatch):
    def fail(user_id, day, items):
        raise httpx2.ConnectError("connection refused")
    monkeypatch.setattr(sync.nutrient_client, "send_day", fail)


def test_day_is_marked_done_when_nutrient_calc_answers(monkeypatch):
    done = fake_repo(monkeypatch)
    sent = nutrient_calc_up(monkeypatch)
    assert sync.sync_day(FakeConn(), 7, DAY) is True
    assert sent == [(7, DAY, [{"fdc_id": 1, "grams": 100}])]   # the whole day was sent
    assert done == [(7, DAY)]


def test_day_stays_pending_when_nutrient_calc_is_down(monkeypatch):
    done = fake_repo(monkeypatch)
    nutrient_calc_down(monkeypatch)
    assert sync.sync_day(FakeConn(), 7, DAY) is False
    assert done == []


def test_recalculate_sends_every_pending_day(monkeypatch):
    days = [{"user_id": 7, "meal_date": date(2026, 3, d)} for d in (1, 2, 3)]
    done = fake_repo(monkeypatch, days)
    nutrient_calc_up(monkeypatch)
    assert sync.recalculate_pending(FakeConn(), None) == {"sent": 3, "still_pending": 0}
    assert len(done) == 3


def test_recalculate_stops_at_the_first_failure(monkeypatch):
    days = [{"user_id": 7, "meal_date": date(2026, 3, d)} for d in (1, 2, 3)]
    fake_repo(monkeypatch, days)
    nutrient_calc_down(monkeypatch)
    assert sync.recalculate_pending(FakeConn(), None) == {"sent": 0, "still_pending": 3}
