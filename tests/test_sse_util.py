#!/usr/bin/env python3
""" send_sse_events(): idle heartbeat is a named 'ping' event the client's
    watchdog can see (a ': comment' line never reaches EventSource code)
"""

from aquaPi.pages.sse_util import send_sse_events


def test_idle_read_sends_a_ping_event_then_data():
    reads = iter([None, '["filter"]'])
    closed = []
    resp = send_sse_events(lambda: next(reads), delay=0, on_close=lambda: closed.append(1))
    events = resp.response
    assert next(events) == 'event: ping\ndata: \n\n'
    assert next(events) == 'data: ["filter"]\n\n'
    events.close()
    assert closed == [1]
