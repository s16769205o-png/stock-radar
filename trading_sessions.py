"""Exchange sessions shared by quote validation and prospective research."""
from functools import lru_cache

import exchange_calendars as xcals


@lru_cache
def calendar_for(market):
    return xcals.get_calendar({'台股': 'XTAI', '美股': 'XNYS'}[market])


def last_completed_session(market, now):
    calendar = calendar_for(market)
    local_day = now.astimezone(calendar.tz).date().isoformat()
    session = calendar.date_to_session(local_day, direction='previous')
    if calendar.session_close(session) > now:
        session = calendar.previous_session(session)
    return session.date().isoformat()


def first_later_session(market, observed_at):
    """Use the next session on a later local date, even for pre-open signals."""
    calendar = calendar_for(market)
    local_day = observed_at.astimezone(calendar.tz).date().isoformat()
    session = calendar.date_to_session(local_day, direction='next')
    if session.date().isoformat() == local_day:
        session = calendar.next_session(session)
    return session.date().isoformat()


def session_after(market, day, count):
    return calendar_for(market).session_offset(day, count).date().isoformat()


def recent_sessions(market, end_day, count):
    calendar = calendar_for(market)
    start = calendar.session_offset(end_day, 1 - count)
    return [session.date().isoformat() for session in calendar.sessions_in_range(start, end_day)]
