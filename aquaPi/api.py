#!/usr/bin/env python3

import logging
import shutil
import tempfile
import time
from html import escape
from os import path

from http import HTTPStatus
from flask import (Blueprint, current_app, json, Response, request, jsonify,
                   send_file, after_this_request)
from flask_login import (login_required, current_user)

from . import db
from .auth import roles_required
from .driver.base import DriverError
from .driver.DriverADC import SIMULATED
from .machineroom import (MachineRoom, MsgBus)
from .machineroom.msg_bus import BusRole
from .machineroom.alert_nodes import Alert
from .machineroom.aux_nodes import ScaleAux
from .machineroom.in_nodes import UiInput
from .machineroom.hist_nodes import (QUEST_DB, check_questdb_reachable,
                                     log_calibration_event, get_calibration_log)
from .pages.sse_util import send_sse_events
from .system_info import get_system_stats


log = logging.getLogger('aquaPi.api')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


bp = Blueprint('api', __name__)


def the_bus() -> MsgBus | None:
    """ access the global object MachineRoom
    """
    mr: MachineRoom = current_app.extensions['machineroom']
    return mr.bus


def _wiring_db_path() -> str:
    mr: MachineRoom = current_app.extensions['machineroom']
    return mr.globals['BUS_WIRING']


def _collect_api_routes() -> list[dict]:
    """ every registered /api/... route with its HTTP method(s) and
        description - derived from the live URL map and each route's
        own docstring, so this stays correct without any manual
        upkeep as routes are added, changed or removed
    """
    routes = []
    for rule in current_app.url_map.iter_rules():
        if rule.rule == '/api/' or not rule.rule.startswith('/api'):
            continue
        view = current_app.view_functions.get(rule.endpoint)
        doc = ' '.join((view.__doc__ or '').split())

        # roles_required() (auth.py) stashes the roles it was given on
        # the wrapped view - surface them here instead of relying on
        # each docstring to mention it, so a route can't silently drift
        # out of sync with its actual restriction. Routes open to every
        # valid role are equivalent to plain login_required, so skip those.
        required_roles = getattr(view, 'required_roles', None)
        if required_roles and set(required_roles) != set(db.VALID_ROLES):
            doc = (doc + ' ' if doc else '') + f"Requires role: {'/'.join(required_roles)}."

        routes.append({
            'path': rule.rule,
            'methods': sorted((rule.methods or set()) - {'HEAD', 'OPTIONS'}),
            'description': doc,
        })
    routes.sort(key=lambda r: r['path'])
    return routes


# cosmetic-only: nicer section headers for the HTML view's known top-level
# /api/<segment>/... groups. Any segment missing here still gets a sensible
# auto-derived header (see _api_group_label()), so a newly added route
# doesn't need an entry here to show up correctly grouped.
_API_GROUP_NAMES = {
    'users': 'User management',
    'nodes': 'Nodes',
    'node-types': 'Node types',
    'dashboard': 'Dashboard',
    'history': 'History',
    'notifications': 'Notifications',
    'templates': 'Config templates',
    'config': 'Config snapshots',
    'audit-log': 'Audit log',
    'backup': 'Backup',
    'health': 'Health',
    'sse': 'Live updates (SSE)',
    'system-info': 'System info',
}


def _api_group_label(route_path: str) -> str:
    """ human-readable section header for a /api/<segment>/... path """
    segment = route_path.removeprefix('/api/').split('/', 1)[0]
    return _API_GROUP_NAMES.get(segment, segment.replace('-', ' ').title())


def _render_api_routes_html(routes: list[dict]) -> str:
    rows = []
    prev_group = None
    for route in routes:
        group = _api_group_label(route['path'])
        if group != prev_group:
            rows.append(f'<tr><th colspan="3">{escape(group)}</th></tr>')
            prev_group = group
        rows.append(
            '<tr><td>{}</td><td><code>{}</code></td><td>{}</td></tr>'.format(
                escape('/'.join(route['methods'])),
                escape(route['path']),
                escape(route['description']),
            )
        )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>aquaPi API</title>
<style>
  body {{ font-family: sans-serif; margin: 2em; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 0.35em 0.8em; vertical-align: top; }}
  td {{ border-bottom: 1px solid #ddd; }}
  th {{ background: #f0f0f0; padding-top: 0.8em; }}
  code {{ font-family: monospace; }}
</style>
</head>
<body>
<h1>aquaPi API</h1>
<p>Machine-readable version: send an <code>Accept: application/json</code>
   header to this same URL.</p>
<table>
<thead><tr><th>Method</th><th>Path</th><th>Description</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>'''


@bp.route('/api/', methods=['GET'])
@login_required
def api_index() -> Response:
    """ list every registered /api/... route with its HTTP method(s)
        and description, as JSON or - for a plain browser visit - as
        a human-readable HTML page, based on the request's Accept header.
    """
    routes = _collect_api_routes()
    if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'text/html':
        return Response(_render_api_routes_html(routes), mimetype='text/html')
    return jsonify(routes)


@bp.route('/api/nodes/')
@login_required
def api_nodes() -> Response:
    """ return an array of all node ids.
    """
    bus = the_bus()
    if bus is None:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # an empty wiring (e.g. right after a fresh start, or if every
    # node failed to restore) is a valid state, not a server error -
    # this used to answer with 500 whenever node_ids was empty
    node_ids = [node.id for node in
                sorted(bus.get_nodes(), key=lambda node: node.ROLE.value)]
    body = json.dumps(node_ids)
    log.debug('API nodes: %s', body)
    return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')


def _node_to_dict(node) -> dict:
    """ build the plain, JSON-serializable dict for a single node, as
        returned by the REST API. Reuses db.serialize_node() (also used
        for SQLite persistence) so node-type specific quirks (currently
        only Alert.conditions) are normalized in a single place, instead
        of relying on jsonpickle's generic object introspection.
    """
    item = db.serialize_node(node)
    item['type'] = type(node).__name__
    item['role'] = str(node.ROLE).rsplit('.', 1)[1]

    if hasattr(node, 'alert') and node.alert:
        item['alert'] = node.alert

    return item


@bp.route('/api/nodes/<node_id>')
@login_required
def api_node(node_id: str) -> Response:
    """ return the current state of a single node.
    """
    bus = the_bus()
    if bus:
        node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
        node = bus.get_node(node_id)

        if node:
            item = _node_to_dict(node)

            body = json.dumps({'result': 'SUCCESS', 'data': item})
            log.debug('API nodes/%s: %s', node_id, body)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

        return Response(status=HTTPStatus.NOT_FOUND)

    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/history/')
@login_required
def api_history_nodes() -> Response:
    """ return an array of all history node ids.
    """
    bus = the_bus()
    if bus:
        node_ids = [node.id for node in bus.get_nodes(BusRole.HISTORY)]
        if node_ids:
            body = json.dumps(node_ids)
            log.debug('API history: %s', body)
            return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

        return Response(status=HTTPStatus.NOT_FOUND)

    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/history/<node_id>')
@login_required
def api_history(node_id: str) -> Response:
    """ return a single node's history, which may contain several series
        (?start=<unix timestamp>, default 0 means everything on the
        in-memory DB, or the last 24h on the real DB; ?step=<cluster size
        in seconds>, default 0/none). Clustering only works with the
        real DB; the in-memory DB can't cluster.
    """
    bus = the_bus()
    if bus:
        node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
        node = bus.get_node(node_id)

        start = int(request.args.get('start', 0))
        step = int(request.args.get('step', 0))

        if node:
            if hasattr(node, 'get_history'):
                hist = node.get_history(start, step)

                body = json.dumps({'result': 'SUCCESS', 'data': hist}, sort_keys=False)
                log.debug('API history/%s (%d/%d): %s', node_id, start, step, body)
                return Response(status=HTTPStatus.OK, response=body, mimetype='application/json')

            return Response(status=HTTPStatus.BAD_REQUEST)

        return Response(status=HTTPStatus.NOT_FOUND)

    return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)


@bp.route('/api/history/<node_id>/export')
@login_required
def api_history_export(node_id: str) -> Response:
    """ export a history node's recorded series as CSV or JSON
        (?format=csv|json, default json; optional ?start=/?step= like
        /api/history/<id>), for offline analysis.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node_id = str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')
    node = bus.get_node(node_id)
    if not node or not hasattr(node, 'get_history'):
        return Response(status=HTTPStatus.NOT_FOUND)

    start = int(request.args.get('start', 0))
    step = int(request.args.get('step', 0))
    fmt = request.args.get('format', 'json').lower()
    if fmt not in ('csv', 'json'):
        return jsonify(error=f'Invalid format: {fmt!r}, expected csv or json'), HTTPStatus.BAD_REQUEST

    hist = node.get_history(start, step)
    names = list(hist.get(0, []))
    rows = sorted((ts, vals) for ts, vals in hist.items() if ts != 0)

    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'export_history', node_id, {'format': fmt})

    if fmt == 'csv':
        import csv
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['timestamp'] + names)
        for ts, vals in rows:
            writer.writerow([ts] + list(vals))
        return Response(buf.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{node_id}_history.csv"'
        })

    data = [{'timestamp': ts, **dict(zip(names, vals))} for ts, vals in rows]
    return jsonify({'node_id': node_id, 'fields': names, 'data': data})


@bp.route('/api/nodes/<node_id>/calibration-log')
@login_required
def api_calibration_log(node_id: str) -> Response:
    """ return the recorded calibration history (offset/factor changes)
        of a ScaleAux node (?limit=<max entries>, default 100); empty
        list if QuestDB is unavailable or the node never had a
        calibration change recorded.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node = bus.get_node(node_id)
    if not node:
        return Response(status=HTTPStatus.NOT_FOUND)

    limit = int(request.args.get('limit', 100))
    return jsonify(get_calibration_log(node_id, limit))


@bp.route('/api/sse', methods=['GET'])
@login_required
def api_sse() -> Response:
    """ stream Server-Sent Events with the ids of modified nodes.
        Requires an 'Accept: text/event-stream' request header.
    """
    if request.headers.get('accept') != 'text/event-stream':
        return Response('MUST ACCEPT content type text/event-stream', status=HTTPStatus.BAD_REQUEST)

    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    change_queue = bus.subscribe_changes()

    def sse_update():
        # timeout -> None makes send_sse_events() emit a heartbeat comment,
        # so an idle connection isn't silent forever (see MEMORY: SSE
        # timeout needs reload - a client that resumed from sleep/hibernate
        # can hold a zombie connection that never errors out on its own)
        changed_ids = bus.wait_for_changes(change_queue, timeout=20)
        if not changed_ids:
            return None
        log.debug('API sse reply: %r', changed_ids)
        return json.dumps([id for id in changed_ids])

    return send_sse_events(sse_update, on_close=lambda: bus.unsubscribe_changes(change_queue))


@bp.route('/api/system-info', methods=['GET'])
@login_required
def api_system_info() -> Response:
    """ return a small set of system stats: OS name, load average,
        memory/disk usage.
    """
    return jsonify(get_system_stats())


def _users_db_path() -> str:
    return db.get_users_db_path(current_app.config['INSTANCE_PATH'])


@bp.route('/api/dashboard/', methods=['GET'])
@login_required
def api_get_dashboard() -> Response:
    """ return the current user's own dashboard layout (visible
        controllers/groups, ordering). An empty list means the user
        has never saved one; callers should fall back to a default view.
    """
    layout = db.get_dashboard(_users_db_path(), current_user.id)
    return jsonify(layout)


@bp.route('/api/dashboard/', methods=['PUT'])
@login_required
def api_set_dashboard() -> Response:
    """ save the current user's dashboard layout. """
    layout = request.get_json(silent=True)
    if not isinstance(layout, list):
        return jsonify(error='Body must be a JSON array'), HTTPStatus.BAD_REQUEST

    db.set_dashboard(_users_db_path(), current_user.id, layout)
    log.info('User %r saved dashboard layout (%d items)', current_user.username, len(layout))
    return jsonify(layout)


@bp.route('/api/nodes/<node_id>/settings', methods=['GET'])
@login_required
def api_get_node_settings(node_id: str) -> Response:
    """ return a node's configurable operational parameters: for each
        one, its key, label, current value, value constraints
        (type/min/max/options), and whether it's editable.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node = bus.get_node(node_id)
    if not node:
        return Response(status=HTTPStatus.NOT_FOUND)

    settings = [entry.to_dict() for entry in node.get_settings()]
    return jsonify(settings)


def _validate_and_cast(key: str, raw_value, vtype: str,
                        vmin: float | None = None, vmax: float | None = None,
                        voptions: list[str] | None = None, voptional: bool = False):
    """ validate & cast a single value against a type/min/max/options -
        shared by the /settings API (sourced from a node's get_settings())
        and the /config node-schema API (sourced from get_node_type_schema());
        raises ValueError on an invalid type or an out-of-range/-list value.
        Values are required (non-empty) unless voptional is set.
    """
    if not voptional and raw_value in (None, '', []):
        raise ValueError(f'{key}: value is required')

    if vtype in ('number', 'duration'):
        # 'duration' is a plain number on the wire (always seconds) - the
        # only difference is the /settings widget used to render/edit it
        # and the factor-conversion applied afterward in
        # api_set_node_settings(), not the validation itself.
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f'{key}: expected a number')
        if vmin is not None and value < vmin:
            raise ValueError(f'{key}: value {value} below minimum {vmin}')
        if vmax is not None and value > vmax:
            raise ValueError(f'{key}: value {value} above maximum {vmax}')
        return value
    elif vtype == 'checkbox':
        if not isinstance(raw_value, bool):
            raise ValueError(f'{key}: expected a boolean')
        return raw_value
    elif vtype == 'select':
        if not isinstance(raw_value, str):
            raise ValueError(f'{key}: expected a string')
        if raw_value and voptions is not None and raw_value not in voptions:
            raise ValueError(f'{key}: {raw_value!r} is not a valid choice')
        return raw_value
    elif vtype == 'multiselect':
        if not isinstance(raw_value, list) or not all(isinstance(v, str) for v in raw_value):
            raise ValueError(f'{key}: expected a list of strings')
        if voptions is not None and not all(v in voptions for v in raw_value):
            raise ValueError(f'{key}: contains an invalid choice')
        return raw_value
    else:
        return str(raw_value)


@bp.route('/api/nodes/<node_id>/settings', methods=['PUT'])
@login_required
def api_set_node_settings(node_id: str) -> Response:
    """ update one or more of a node's operational parameters, validated
        against each parameter's type/min/max, then persist the whole
        wiring. Requires operator/admin, except when the target is a
        UiInput node (e.g. UiSwitchInput, UiAnalogInput) and the request
        body contains only the 'value' key - that case is allowed for
        any role, including the anonymous viewer.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node = bus.get_node(node_id)
    if not node:
        return Response(status=HTTPStatus.NOT_FOUND)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Body must be a JSON object of {key: value}'), HTTPStatus.BAD_REQUEST

    is_ui_value_only = isinstance(node, UiInput) and set(body.keys()) <= {'value'}
    if not is_ui_value_only and current_user.role not in ('operator', 'admin'):
        return jsonify(error='Forbidden'), HTTPStatus.FORBIDDEN

    editable = {entry.key: entry for entry in node.get_settings() if entry.key is not None}

    for key in body:
        if key not in editable:
            return jsonify(error=f'Unknown or read-only setting: {key}'), HTTPStatus.BAD_REQUEST

    # Step 28: calibration history - ScaleAux is used for linear sensor
    # calibrations (e.g. pH probes); log offset/factor changes to QuestDB
    calibration_changes: list[tuple[str, float, float]] = []

    try:
        for key, raw_value in body.items():
            entry = editable[key]
            value = _validate_and_cast(key, raw_value, entry.type, entry.min, entry.max,
                                       entry.options, entry.optional)
            if entry.type == 'duration' and entry.factor != 1:
                # raw_value/value is in the wire unit (seconds) - convert
                # back to whatever unit the node itself stores internally
                value = value / entry.factor
            if isinstance(node, ScaleAux) and key in ('offset', 'factor'):
                calibration_changes.append((key, getattr(node, key), value))
            setattr(node, key, value)
    except ValueError as ex:
        return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r updated settings of node %r: %s',
             current_user.username, node_id, list(body.keys()))
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'update_settings', node_id, {'fields': list(body.keys())})

    for field, old_value, new_value in calibration_changes:
        log_calibration_event(node_id, field, old_value, new_value)

    settings = [entry.to_dict() for entry in node.get_settings()]
    return jsonify(settings)


# --- /config: node-graph editor (Step 12) -----------------------------


def _validate_fields(schema_fields: list, raw_fields: dict, *, require_all: bool) -> dict:
    """ validate/cast a {key: value} dict against a get_node_type_schema()
        field list (Setting.to_dict() shape - type/min/max/options live
        under each field's 'attrs'). On creation (require_all=True), fields
        without a submitted value fall back to their schema 'value' (a
        suggested default, may be absent), or raise if 'required' and none
        is given. On update (require_all=False), only the submitted keys
        are validated. Raises ValueError on an unknown key or an invalid
        value.
    """
    by_key = {f['key']: f for f in schema_fields}

    for key in raw_fields:
        if key not in by_key:
            raise ValueError(f'Unknown field: {key}')

    result = {}
    for key, field in by_key.items():
        attrs = field.get('attrs', {})
        if key in raw_fields:
            # get_node_type_schema() already has its own required/default
            # handling (below, for *missing* keys) - always pass
            # voptional=True here so this shared validator doesn't also
            # reject a submitted blank value; that's a separate,
            # /settings-only concept (Setting.optional).
            result[key] = _validate_and_cast(key, raw_fields[key], attrs['type'],
                                              attrs.get('min'), attrs.get('max'),
                                              voptional=True)
        elif require_all:
            if field.get('value') is not None:
                result[key] = field['value']
            elif field.get('required'):
                raise ValueError(f'Missing required field: {key}')
    return result


@bp.route('/api/node-types/', methods=['GET'])
@login_required
def api_node_types() -> Response:
    """ metadata describing every creatable node type: its fields and
        how many 'receives' connections it accepts. Alert nodes are
        not included.
    """
    return jsonify(db.get_node_type_schema())


@bp.route('/api/nodes/', methods=['POST'])
@roles_required('admin')
def api_create_node() -> Response:
    """ create a new node of a creatable type, wire it up on the live
        bus and persist the wiring.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Body must be a JSON object'), HTTPStatus.BAD_REQUEST

    type_name = body.get('type')
    schema = db.get_node_type_schema().get(type_name)
    if not schema:
        return jsonify(error=f'Unknown or non-creatable node type: {type_name!r}'), HTTPStatus.BAD_REQUEST

    name = (body.get('name') or '').strip()
    if not name:
        return jsonify(error='name must not be empty'), HTTPStatus.BAD_REQUEST

    node_id = db.compute_node_id(name)
    if bus.get_node(node_id):
        return jsonify(error=f'A node named {name!r} already exists'), HTTPStatus.BAD_REQUEST

    receives = body.get('receives', [])
    if not isinstance(receives, list) or not all(isinstance(r, str) for r in receives):
        return jsonify(error='receives must be a list of node ids'), HTTPStatus.BAD_REQUEST

    if schema['receives'] == 'none' and receives:
        return jsonify(error=f'{type_name} does not accept any receives'), HTTPStatus.BAD_REQUEST
    if schema['receives'] == 'single' and len(receives) > 1:
        return jsonify(error=f'{type_name} accepts at most 1 receives entry'), HTTPStatus.BAD_REQUEST

    # TODO(config-receives-type-filtering): existence-only - doesn't check
    # the referenced node's data_range compatibility. See
    # .junie/plans/config-receives-type-filtering.md
    for rcv_id in receives:
        if not bus.get_node(rcv_id):
            return jsonify(error=f'Unknown receives node id: {rcv_id}'), HTTPStatus.BAD_REQUEST

    raw_fields = body.get('fields', {})
    if not isinstance(raw_fields, dict):
        return jsonify(error='fields must be a JSON object'), HTTPStatus.BAD_REQUEST

    try:
        fields = _validate_fields(schema['fields'], raw_fields, require_all=True)
        node = db.build_node(type_name, name, receives, fields)
    except (ValueError, KeyError) as ex:
        return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST

    node.group = str(body.get('group', '') or '')
    try:
        node.pos_x = float(body.get('pos_x', 0.0) or 0.0)
        node.pos_y = float(body.get('pos_y', 0.0) or 0.0)
    except (TypeError, ValueError):
        node.pos_x = node.pos_y = 0.0

    node.plugin(bus)

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r created node %r (type %s)', current_user.username, node.id, type_name)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'create_node', node.id, {'type': type_name})

    return jsonify(_node_to_dict(node)), HTTPStatus.CREATED


@bp.route('/api/nodes/<node_id>', methods=['PUT'])
@roles_required('admin')
def api_update_node(node_id: str) -> Response:
    """ update an existing node's wiring (receives), position, group
        and/or type-specific fields. Renaming (which would change the
        node's id) is not supported by this route.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node = bus.get_node(node_id)
    if not node:
        return Response(status=HTTPStatus.NOT_FOUND)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Body must be a JSON object'), HTTPStatus.BAD_REQUEST

    schema = db.get_node_type_schema().get(type(node).__name__)

    if 'receives' in body:
        receives = body['receives']
        if not isinstance(receives, list) or not all(isinstance(r, str) for r in receives):
            return jsonify(error='receives must be a list of node ids'), HTTPStatus.BAD_REQUEST
        if not schema:
            return jsonify(error=f'{type(node).__name__} does not support changing receives'), HTTPStatus.BAD_REQUEST
        if schema['receives'] == 'none' and receives:
            return jsonify(error=f'{type(node).__name__} does not accept any receives'), HTTPStatus.BAD_REQUEST
        if schema['receives'] == 'single' and len(receives) > 1:
            return jsonify(error=f'{type(node).__name__} accepts at most 1 receives entry'), HTTPStatus.BAD_REQUEST
        # TODO(config-receives-type-filtering): existence-only - doesn't
        # check the referenced node's data_range compatibility. See
        # .junie/plans/config-receives-type-filtering.md
        for rcv_id in receives:
            if not bus.get_node(rcv_id):
                return jsonify(error=f'Unknown receives node id: {rcv_id}'), HTTPStatus.BAD_REQUEST
        if db.would_create_cycle(bus, node_id, receives):
            return jsonify(error='This wiring would create a cycle'), HTTPStatus.BAD_REQUEST
        node.receives = receives

    if 'fields' in body:
        raw_fields = body['fields']
        if not isinstance(raw_fields, dict):
            return jsonify(error='fields must be a JSON object'), HTTPStatus.BAD_REQUEST
        if not schema:
            return jsonify(error=f'{type(node).__name__} does not support editing fields'), HTTPStatus.BAD_REQUEST
        try:
            fields = db.convert_duration_fields(
                type(node), _validate_fields(schema['fields'], raw_fields, require_all=False))
        except ValueError as ex:
            return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST
        for key, value in fields.items():
            setattr(node, key, value)

    if 'group' in body:
        node.group = str(body['group'] or '')

    if 'pos_x' in body:
        try:
            node.pos_x = float(body['pos_x'])
        except (TypeError, ValueError):
            return jsonify(error='pos_x must be a number'), HTTPStatus.BAD_REQUEST

    if 'pos_y' in body:
        try:
            node.pos_y = float(body['pos_y'])
        except (TypeError, ValueError):
            return jsonify(error='pos_y must be a number'), HTTPStatus.BAD_REQUEST

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r updated node %r: %s', current_user.username, node_id, list(body.keys()))
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'update_node', node_id, {'fields': list(body.keys())})

    return jsonify(_node_to_dict(node))


@bp.route('/api/nodes/<node_id>/conditions', methods=['PUT'])
@roles_required('operator', 'admin')
def api_set_alert_conditions(node_id: str) -> Response:
    """ bulk-replace every AlertCond of an Alert node in one call -
        add/change/remove are all expressed as the new, complete list.
        AlertCond has no stable per-item id (stored/compared by Python
        object identity inside a set, not a persisted key), so no
        partial add/remove-by-id route is offered; a full bulk-replace
        (matching PUT /api/dashboard/'s existing convention) is atomic
        and needs no new identity scheme. An empty list is accepted -
        it silences the alert without deleting the node (and its
        port/repeat/notification prefs).
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node = bus.get_node(node_id)
    if not node:
        return Response(status=HTTPStatus.NOT_FOUND)
    if not isinstance(node, Alert):
        return jsonify(error=f'{type(node).__name__} does not have alert conditions'), HTTPStatus.BAD_REQUEST

    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('conditions'), list):
        return jsonify(error="Body must be a JSON object with a 'conditions' list"), HTTPStatus.BAD_REQUEST

    conditions = set()
    for i, raw in enumerate(body['conditions']):
        if not isinstance(raw, dict):
            return jsonify(error=f'conditions[{i}] must be an object'), HTTPStatus.BAD_REQUEST

        cls = db.ALERT_COND_FACTORY.get(raw.get('class'))
        if not cls:
            return jsonify(error=f"conditions[{i}]: unknown class {raw.get('class')!r}"), HTTPStatus.BAD_REQUEST

        cond_node_id = raw.get('node_id')
        if not isinstance(cond_node_id, str) or not bus.get_node(cond_node_id):
            return jsonify(error=f'conditions[{i}]: unknown node_id {cond_node_id!r}'), HTTPStatus.BAD_REQUEST

        try:
            limit = _validate_and_cast(f'conditions[{i}].limit', raw.get('limit'), 'number')
            duration = _validate_and_cast(f'conditions[{i}].duration', raw.get('duration', 0),
                                          'number', vmin=0, voptional=True)
        except ValueError as ex:
            return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST

        conditions.add(cls(cond_node_id, limit=limit, duration=int(duration)))

    receives = [c.node_id for c in conditions]
    if db.would_create_cycle(bus, node_id, receives):
        return jsonify(error='This wiring would create a cycle'), HTTPStatus.BAD_REQUEST

    node.conditions = conditions
    node.receives = receives

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r replaced conditions of alert %r: %d condition(s)',
             current_user.username, node_id, len(conditions))
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'update_alert_conditions', node_id, {'count': len(conditions)})

    return jsonify(_node_to_dict(node))


@bp.route('/api/nodes/<node_id>', methods=['DELETE'])
@roles_required('admin')
def api_delete_node(node_id: str) -> Response:
    """ remove a node from the live bus, cleanly disconnecting it from
        any other node that still listens to it (except Alert nodes,
        whose 'receives' can't be edited directly), then persist the
        wiring.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    node = bus.get_node(node_id)
    if not node:
        return Response(status=HTTPStatus.NOT_FOUND)

    db.prune_dangling_references(bus, node_id)

    node.pullout()

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r deleted node %r', current_user.username, node_id)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'delete_node', node_id)

    return Response(status=HTTPStatus.NO_CONTENT)


@bp.route('/api/config/apply', methods=['POST'])
@roles_required('admin')
def api_config_apply() -> Response:
    """ atomically apply a bulk create/update/delete diff to the
        wiring. Either every part of the diff is applied and
        persisted, or (on any validation error) nothing is changed
        at all.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    diff = request.get_json(silent=True)
    if not isinstance(diff, dict):
        return jsonify(error='Body must be a JSON object'), HTTPStatus.BAD_REQUEST

    try:
        result = db.apply_config_diff(bus, diff, _validate_fields)
    except db.ConfigDiffError as ex:
        return jsonify(error=str(ex), entry=ex.entry), HTTPStatus.BAD_REQUEST

    if result['id_map'] or diff.get('creates') or diff.get('updates') or diff.get('deletes'):
        mr: MachineRoom = current_app.extensions['machineroom']
        mr.save_nodes(bus)
        log.info('User %r applied config diff: %d create(s), %d update(s), %d delete(s)',
                 current_user.username, len(diff.get('creates') or []),
                 len(diff.get('updates') or []), len(diff.get('deletes') or []))
        db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                               'apply_config_diff', '', {
                                   'creates': len(diff.get('creates') or []),
                                   'updates': len(diff.get('updates') or []),
                                   'deletes': len(diff.get('deletes') or []),
                               })

    nodes = [_node_to_dict(node) for node in bus.get_nodes()]
    return jsonify(nodes=nodes, id_map=result['id_map'])


# --- /config: node-combination templates (Step 13) ---------------------


@bp.route('/api/templates/', methods=['GET'])
@roles_required('viewer', 'operator', 'admin')
def api_list_templates() -> Response:
    """ list all node-combination templates (name, description, node count). """
    return jsonify(db.list_templates(_wiring_db_path()))


@bp.route('/api/templates/', methods=['POST'])
@roles_required('admin')
def api_create_template() -> Response:
    """ capture a named template from a set of currently live node ids.
        Creating a template with an already-used name overwrites it.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Body must be a JSON object'), HTTPStatus.BAD_REQUEST

    name = (body.get('name') or '').strip()
    if not name:
        return jsonify(error='name must not be empty'), HTTPStatus.BAD_REQUEST

    node_ids = body.get('node_ids', [])
    if not isinstance(node_ids, list) or not node_ids \
       or not all(isinstance(i, str) for i in node_ids):
        return jsonify(error='node_ids must be a non-empty list of node ids'), HTTPStatus.BAD_REQUEST

    try:
        data = db.capture_node_template(bus, node_ids)
    except ValueError as ex:
        return jsonify(error=str(ex)), HTTPStatus.BAD_REQUEST

    db.save_template(_wiring_db_path(), name, body.get('descr', '') or '', data)

    log.info('User %r saved template %r (%d nodes)',
             current_user.username, name, len(node_ids))
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'save_template', name, {'node_count': len(node_ids)})

    return jsonify(db.get_template(_wiring_db_path(), name)), HTTPStatus.CREATED


@bp.route('/api/templates/<name>', methods=['GET'])
@roles_required('viewer', 'operator', 'admin')
def api_get_template(name: str) -> Response:
    """ fetch one template including its full node data. """
    template = db.get_template(_wiring_db_path(), name)
    if not template:
        return Response(status=HTTPStatus.NOT_FOUND)
    return jsonify(template)


@bp.route('/api/templates/<name>', methods=['DELETE'])
@roles_required('admin')
def api_delete_template(name: str) -> Response:
    """ remove a template. """
    if not db.delete_template(_wiring_db_path(), name):
        return Response(status=HTTPStatus.NOT_FOUND)

    log.info('User %r deleted template %r', current_user.username, name)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'delete_template', name)

    return Response(status=HTTPStatus.NO_CONTENT)


@bp.route('/api/templates/<name>/insert', methods=['POST'])
@roles_required('admin')
def api_insert_template(name: str) -> Response:
    """ insert a template's nodes into the live bus with fresh,
        collision-free ids, wire them up and persist the wiring.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    template = db.get_template(_wiring_db_path(), name)
    if not template:
        return Response(status=HTTPStatus.NOT_FOUND)

    try:
        new_nodes = db.instantiate_template(bus, template['data'])
    except (ValueError, KeyError, TypeError, DriverError) as ex:
        log.exception('api_insert_template: failed to instantiate template %r', name)
        return jsonify(error=f'Could not insert template: {ex}'), HTTPStatus.BAD_REQUEST

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r inserted template %r (%d new nodes)',
             current_user.username, name, len(new_nodes))
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'insert_template', name, {'node_count': len(new_nodes)})

    return jsonify([_node_to_dict(n) for n in new_nodes]), HTTPStatus.CREATED


# --- /config: wiring snapshots (Step 13) ------------------------------


@bp.route('/api/config/snapshots', methods=['GET'])
@roles_required('viewer', 'operator', 'admin')
def api_list_snapshots() -> Response:
    """ list all saved configuration snapshots (name, created_at). """
    return jsonify(db.list_snapshots(_wiring_db_path()))


@bp.route('/api/config/snapshots', methods=['POST'])
@roles_required('admin')
def api_create_snapshot() -> Response:
    """ save the entire current wiring as a named snapshot.
        Creating a snapshot with an already-used name overwrites it.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Body must be a JSON object'), HTTPStatus.BAD_REQUEST

    name = (body.get('name') or '').strip()
    if not name:
        return jsonify(error='name must not be empty'), HTTPStatus.BAD_REQUEST

    bus = the_bus()
    if bus:
        # make sure the on-disk 'nodes' table reflects the live bus
        # before it gets exported into the snapshot
        mr: MachineRoom = current_app.extensions['machineroom']
        mr.save_nodes(bus)

    db.create_snapshot(_wiring_db_path(), name)

    log.info('User %r created snapshot %r', current_user.username, name)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'create_snapshot', name)

    return jsonify(db.get_snapshot(_wiring_db_path(), name)), HTTPStatus.CREATED


@bp.route('/api/config/snapshots/<name>', methods=['DELETE'])
@roles_required('admin')
def api_delete_snapshot(name: str) -> Response:
    """ remove a saved snapshot. """
    if not db.delete_snapshot(_wiring_db_path(), name):
        return Response(status=HTTPStatus.NOT_FOUND)

    log.info('User %r deleted snapshot %r', current_user.username, name)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'delete_snapshot', name)

    return Response(status=HTTPStatus.NO_CONTENT)


@bp.route('/api/config/snapshots/<name>/restore', methods=['POST'])
@roles_required('admin')
def api_restore_snapshot(name: str) -> Response:
    """ replace the entire live wiring with the one stored in a
        snapshot, then persist it as the new current wiring.
    """
    bus = the_bus()
    if not bus:
        return Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    snapshot = db.get_snapshot(_wiring_db_path(), name)
    if not snapshot:
        return Response(status=HTTPStatus.NOT_FOUND)

    db.restore_snapshot_into_bus(bus, snapshot['data'])

    mr: MachineRoom = current_app.extensions['machineroom']
    mr.save_nodes(bus)

    log.info('User %r restored snapshot %r (%d nodes)',
             current_user.username, name, len(bus.nodes))
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'restore_snapshot', name, {'node_count': len(bus.nodes)})

    return jsonify([_node_to_dict(n) for n in bus.get_nodes()])


# --- audit log (Step 23) ------------------------------------------------


@bp.route('/api/audit-log', methods=['GET'])
@roles_required('admin')
def api_audit_log() -> Response:
    """ list audit log entries (newest first)
        (?limit=<max entries>, default 50; ?offset=<skip>, default 0;
        optional exact-match filters ?action=/?username=).
    """
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        return jsonify(error='limit/offset must be integers'), HTTPStatus.BAD_REQUEST

    result = db.list_audit_log(_users_db_path(), limit=limit, offset=offset,
                               action=request.args.get('action') or None,
                               username=request.args.get('username') or None)
    return jsonify(result)


# --- database backup (Step 24) ------------------------------------------


@bp.route('/api/backup', methods=['GET'])
@roles_required('admin')
def api_backup() -> Response:
    """ build a fresh, consistent backup archive (wiring + users
        databases) on the fly and offer it as a file download.
    """
    mr: MachineRoom = current_app.extensions['machineroom']
    tmp_dir = tempfile.mkdtemp(prefix='aquapi-backup-dl-')

    @after_this_request
    def _cleanup(response: Response) -> Response:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return response

    archive_path = db.create_backup_archive(
        mr.globals['BUS_WIRING'], mr.globals['USERS_DB'], tmp_dir)

    log.info('User %r downloaded a database backup', current_user.username)
    db.add_audit_log_entry(_users_db_path(), current_user.id, current_user.username,
                           'download_backup')

    return send_file(archive_path, as_attachment=True,
                     download_name=path.basename(archive_path))


# --- health check (Step 25) ---------------------------------------------


@bp.route('/api/health', methods=['GET'])
def api_health() -> Response:
    """ unauthenticated health/monitoring endpoint: reports QuestDB
        availability/reachability, the number of currently active bus
        nodes, and whether the app is running in simulation or on real
        hardware. Always returns 200 even if QuestDB is unreachable;
        check the 'questdb.reachable' field instead.
    """
    bus = the_bus()
    node_count = len(bus.get_nodes()) if bus else 0

    questdb_reachable = check_questdb_reachable() if QUEST_DB else False

    body = {
        'status': 'ok',
        'timestamp': time.time(),
        'mode': 'simulation' if SIMULATED else 'hardware',
        'nodes': {
            'active': node_count,
        },
        'questdb': {
            'available': QUEST_DB,
            'reachable': questdb_reachable,
        },
    }
    return jsonify(body)
