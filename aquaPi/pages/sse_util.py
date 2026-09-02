#!/usr/bin/env python3

import logging
import time
from flask import Response


log = logging.getLogger('pages.sse_util')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


def format_msg(data: str, event=None) -> str:
    """ Formats a string and an event name in order to follow the event stream convention.
        for event!=None you'll need a custom event listener
        The receiving page needs something like:
<script>
if (!!window.EventSource) {
  const source = new EventSource(document.URL);

  // .onmessage allows "data:.." events;
  // "event: bla\ndata: blub" needs source.addEventListener('join', event => { ...event code... });
  source.onmessage = function(e) {
    console.debug(`EventSource sent: ${e.data}`);
    const obj = JSON.parse(e.data);
    // react on the received data, can be any JSON data structure
    for (const i in obj) {
        ...
    }
  }
}
</script>
    """
    msg = f'data: {data}\n\n'
    if event is not None:
        msg = f'event: {event}\n{msg}'
    return msg


def send_sse_events(read, delay=1, on_close=None):
    # if request.headers.get('accept') == 'text/event-stream':
    def events():
        try:
            while True:
                data = read()
                if data is None:
                    # read() timed out without new data - send a comment
                    # line (ignored by EventSource, keeps no "data:" event)
                    # so idle connections keep bytes flowing. This lets a
                    # dead client (e.g. one that suspended/hibernated and
                    # never sent a TCP FIN/RST) be noticed on the next
                    # failed write, instead of leaking the subscription
                    # forever; see MEMORY: SSE timeout needs reload.
                    yield ': ping\n\n'
                else:
                    yield format_msg(data)
                if delay:
                    time.sleep(delay)
        finally:
            # runs on client disconnect (GeneratorExit) as well as any
            # other exit path - lets the caller release per-connection
            # resources (e.g. MsgBus.unsubscribe_changes())
            if on_close:
                on_close()

    return Response(events(), content_type='text/event-stream')
