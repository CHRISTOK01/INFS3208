"""Keeping nutrient-calc's daily totals in step with the meals people log.

How it works:
  1. When a meal is added or deleted, we save the change AND put that day on the pending_days
     list, in the same transaction. Then we commit, so the meal is safe whatever happens next.
  2. Straight after, sync_day() sends the whole day to nutrient-calc. If that works, the day
     comes off the list and its items are marked 'done'.
  3. If nutrient-calc is down, the day just stays on the list. The user still gets a success
     reply (with calc_status "pending"), and recalculate_pending() sends it later.
"""
import logging
from datetime import date

import httpx2
from psycopg import Connection

from app import config, nutrient_client, repo

log = logging.getLogger(config.SERVICE_NAME)


def sync_day(conn: Connection, user_id: str, day: date) -> bool:
    """Send one day to nutrient-calc. Returns True if it worked, False if the day is still pending.

    The connection must not be in the middle of a transaction (call conn.commit() first), so
    that this runs as its own transaction and holds the day's lock while it works.
    """
    with conn.transaction():
        repo.lock_day(conn, user_id, day)
        items = repo.get_day_items(conn, user_id, day)
        try:
            nutrient_client.send_day(user_id, day, items)
        except httpx2.HTTPError as exc:
            log.warning("nutrient-calc unavailable, day %s for user %s stays pending: %s", day, user_id, exc)
            return False
        repo.mark_day_done(conn, user_id, day)
    return True


def recalculate_pending(conn: Connection, user_id: str | None, limit: int = 100) -> dict:
    """Send every pending day to nutrient-calc (just one user's, or everyone's if user_id is None).

    Stops at the first failure: if nutrient-calc is still down, there's no point waiting for it
    to time out on every remaining day.
    """
    days = repo.get_pending_days(conn, user_id, limit)
    conn.commit()  # end this transaction, so each day below is sent in a transaction of its own
    sent = 0
    for row in days:
        if not sync_day(conn, row["user_id"], row["meal_date"]):
            break
        sent += 1
    return {"sent": sent, "still_pending": len(days) - sent}
