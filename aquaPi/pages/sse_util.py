#!/usr/bin/env python3

import logging
import time
from flask import Response, request, render_template


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


def render_sse_template(html, read, delay=1, **context):
    """ render a Jinja2 template with SSE updatable elements
        html - the Jinja2 template file
        read - long poll method returning a hash of updates
        update - hash of key:value, should be a superset of what
                 read() returns
        delay - timespan between updates, or None for read blocks itself
    """
    if request.headers.get('accept') == 'text/event-stream':
        def events():
            while True:
                yield format_msg(read())
                if delay:
                    time.sleep(delay)

        return Response(events(), content_type='text/event-stream')
    return render_template(html, **context, now=time.asctime())


def send_sse_events(read, delay=1):
    # if request.headers.get('accept') == 'text/event-stream':
    def events():
        while True:
            yield format_msg(read())
            if delay:
                time.sleep(delay)

    return Response(events(), content_type='text/event-stream')
