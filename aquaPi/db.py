#!/usr/bin/env python3
""" SQLite based persistence layer for the node topology.

    This replaces the previous pickle based persistence
    (aquaPi/machineroom/__init__.py: save_nodes()/restore_nodes()),
    which was a security risk: unpickling arbitrary bytes can execute
    arbitrary code (RCE). This module never uses pickle - the topology
    is stored as plain JSON (one row per node) in a SQLite database,
    and nodes are reconstructed by explicitly calling the constructor
    (via each node's existing __setstate__) of a small, fixed set of
    known node classes (NODE_FACTORY below). No arbitrary code can be
    triggered by a manipulated database file: at worst an unknown
    'type' value is rejected.

    Schema ("hybrid": relational columns + a JSON column for details):
        nodes(id TEXT PRIMARY KEY, type TEXT NOT NULL,
              name TEXT, params TEXT NOT NULL)
    'params' contains the JSON serialized node state (as produced by
    the node's own __getstate__()), so node-specific parameters and
    'receives' wiring don't need a rigid, per-type schema.
"""

import json
import logging
import secrets
import sqlite3
from os import path, replace
from typing import Any

from werkzeug.security import generate_password_hash

from .machineroom.msg_bus import MsgBus, BusNode
from .machineroom.ctrl_nodes import (MaximumCtrl, MinimumCtrl, PidCtrl,
                                     SunCtrl, FadeCtrl)
from .machineroom.in_nodes import (AnalogInput, SwitchInput, ScheduleInput)
from .machineroom.out_nodes import (AnalogDevice, SlowPwmDevice, SwitchDevice)
from .machineroom.aux_nodes import (AvgAux, MaxAux, MinAux, ScaleAux)
from .machineroom.hist_nodes import History
from .machineroom.alert_nodes import (Alert, AlertAbove, AlertBelow)
from .driver.base import DriverError


log = logging.getLogger('aquaPi.db')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


DEFAULT_DB_FILENAME = 'topo.sqlite'
DEFAULT_USERS_DB_FILENAME = 'users.sqlite'

VALID_ROLES = ('viewer', 'operator', 'admin')

# Fixed, explicit whitelist of node classes that may be reconstructed
# from the database. This is the core safety guarantee: only these
# classes can ever be instantiated, and only via their own __setstate__.
NODE_FACTORY: dict[str, type[BusNode]] = {
    cls.__name__: cls for cls in (
        MaximumCtrl, MinimumCtrl, PidCtrl, SunCtrl, FadeCtrl,
        AnalogInput, SwitchInput, ScheduleInput,
        AnalogDevice, SlowPwmDevice, SwitchDevice,
        AvgAux, MaxAux, MinAux, ScaleAux,
        History,
        Alert,
    )
}

# Same idea for the small helper objects used inside Alert.conditions
ALERT_COND_FACTORY: dict[str, type] = {
    cls.__name__: cls for cls in (AlertAbove, AlertBelow)
}


# --- node type metadata for the /config graph editor ---------------------
#
# Describes, for every *creatable* node type (a subset of NODE_FACTORY -
# Alert is excluded here since its 'conditions' are a set of objects, not
# a simple field, and are out of scope for the generic add/edit dialog),
# which constructor fields the /config page should render, and how many
# 'receives' wires (0, 1 or many) the type accepts.
#
# 'receives' is one of:
#   'none'   - the type doesn't listen to other nodes (e.g. AnalogInput)
#   'single' - exactly one source node id (e.g. a controller output)
#   'multi'  - zero or more source node ids (e.g. History, AvgAux)
#
# Each field entry mirrors the attrs used by get_settings()/the /settings
# API (type: 'text'|'number'|'checkbox', optional min/max), plus
# 'required' (no default, must be supplied on creation) or 'default'.

NODE_TYPE_SCHEMA: dict[str, dict[str, Any]] = {
    'AnalogInput': {
        'receives': 'none',
        'fields': [
            {'key': 'port', 'label': 'Input port', 'type': 'text', 'default': ''},
            {'key': 'initval', 'label': 'Initial value', 'type': 'number', 'default': 0.0},
            {'key': 'unit', 'label': 'Unit', 'type': 'text', 'default': ''},
            {'key': 'interval', 'label': 'Read interval [s]', 'type': 'number',
             'min': 1, 'max': 600, 'default': 10.0},
            {'key': 'avg', 'label': 'Averaging [1=off]', 'type': 'number',
             'min': 1, 'max': 5, 'default': 1},
        ],
    },
    'SwitchInput': {
        'receives': 'none',
        'fields': [
            {'key': 'port', 'label': 'Input port', 'type': 'text', 'default': ''},
            {'key': 'interval', 'label': 'Read interval [s]', 'type': 'number',
             'min': 0.1, 'default': 0.5},
            {'key': 'inverted', 'label': 'Inverted', 'type': 'checkbox', 'default': False},
        ],
    },
    'ScheduleInput': {
        'receives': 'none',
        'fields': [
            {'key': 'cronspec', 'label': 'CRON (m h DoM M DoW)', 'type': 'text', 'required': True},
        ],
    },
    'AnalogDevice': {
        'receives': 'single',
        'fields': [
            {'key': 'port', 'label': 'Output port', 'type': 'text', 'default': ''},
            {'key': 'minimum', 'label': 'Minimum [%]', 'type': 'number',
             'min': 0, 'max': 99, 'default': 0},
            {'key': 'maximum', 'label': 'Maximum [%]', 'type': 'number',
             'min': 1, 'max': 100, 'default': 100},
            {'key': 'percept', 'label': 'Perceptive', 'type': 'checkbox', 'default': False},
        ],
    },
    'SlowPwmDevice': {
        'receives': 'single',
        'fields': [
            {'key': 'port', 'label': 'Output port', 'type': 'text', 'default': ''},
            {'key': 'cycle', 'label': 'PWM cycle time [s]', 'type': 'number',
             'min': 10, 'max': 300, 'default': 60.0},
            {'key': 'inverted', 'label': 'Inverted', 'type': 'checkbox', 'default': False},
        ],
    },
    'SwitchDevice': {
        'receives': 'single',
        'fields': [
            {'key': 'port', 'label': 'Output port', 'type': 'text', 'default': ''},
            {'key': 'inverted', 'label': 'Inverted', 'type': 'checkbox', 'default': False},
        ],
    },
    'MaximumCtrl': {
        'receives': 'single',
        'fields': [
            {'key': 'setpoint', 'label': 'Setpoint', 'type': 'number', 'required': True},
            {'key': 'hysteresis', 'label': 'Hysteresis', 'type': 'number', 'default': 0.0},
        ],
    },
    'MinimumCtrl': {
        'receives': 'single',
        'fields': [
            {'key': 'setpoint', 'label': 'Setpoint', 'type': 'number', 'required': True},
            {'key': 'hysteresis', 'label': 'Hysteresis', 'type': 'number', 'default': 0.0},
        ],
    },
    'PidCtrl': {
        'receives': 'single',
        'fields': [
            {'key': 'setpoint', 'label': 'Setpoint', 'type': 'number', 'required': True},
            {'key': 'p_fact', 'label': 'P factor', 'type': 'number',
             'min': -10, 'max': 10, 'default': 1.0},
            {'key': 'i_fact', 'label': 'I factor', 'type': 'number',
             'min': -10, 'max': 10, 'default': 0.05},
            {'key': 'd_fact', 'label': 'D factor', 'type': 'number',
             'min': -10, 'max': 10, 'default': 0.0},
        ],
    },
    'SunCtrl': {
        'receives': 'single',
        'fields': [
            {'key': 'xscend', 'label': 'Ascend/descend factor', 'type': 'number',
             'default': 1.0},
        ],
    },
    'FadeCtrl': {
        'receives': 'single',
        'fields': [
            {'key': 'fade_time', 'label': 'Fade-in time [s]', 'type': 'number', 'default': 0},
            {'key': 'fade_out', 'label': 'Fade-out time [s]', 'type': 'number', 'default': 0},
        ],
    },
    'AvgAux': {
        'receives': 'multi',
        'fields': [
            {'key': 'unfair_avg', 'label': 'Unweighted average [0=off]', 'type': 'number',
             'min': 0, 'default': 0},
        ],
    },
    'MaxAux': {
        'receives': 'multi',
        'fields': [],
    },
    'MinAux': {
        'receives': 'multi',
        'fields': [],
    },
    'ScaleAux': {
        'receives': 'single',
        'fields': [
            {'key': 'unit', 'label': 'Unit', 'type': 'text', 'default': ''},
            {'key': 'offset', 'label': 'Offset', 'type': 'number', 'default': 0.0},
            {'key': 'factor', 'label': 'Scale factor', 'type': 'number', 'default': 1.0},
        ],
    },
    'History': {
        'receives': 'multi',
        'fields': [
            {'key': 'duration', 'label': 'Duration [h]', 'type': 'number',
             'min': 1, 'default': 24},
        ],
    },
}


def _mk_receives_arg(receives_kind: str, receives: list[str]):
    """ shape the plain list of receiver ids the API accepts into what
        each node type's constructor expects
    """
    if receives_kind == 'none':
        return None
    if receives_kind == 'single':
        return receives[0] if receives else ''
    return list(receives)  # 'multi'


def build_node(type_name: str, name: str, receives: list[str],
              fields: dict[str, Any]) -> BusNode:
    """ construct a brand new node of a *creatable* type (see
        NODE_TYPE_SCHEMA) directly via its real constructor - used by the
        /config graph editor (aquaPi/api.py) to add nodes at runtime.
        Raises ValueError/KeyError on unknown type or missing fields.
    """
    schema = NODE_TYPE_SCHEMA.get(type_name)
    if not schema:
        raise ValueError(f'Unknown or non-creatable node type: {type_name!r}')

    rcv = _mk_receives_arg(schema['receives'], receives)

    if type_name == 'AnalogInput':
        return AnalogInput(name, fields['port'], fields['initval'], fields['unit'],
                           interval=fields['interval'], avg=int(fields['avg']))
    if type_name == 'SwitchInput':
        return SwitchInput(name, fields['port'],
                           interval=fields['interval'], inverted=fields['inverted'])
    if type_name == 'ScheduleInput':
        return ScheduleInput(name, fields['cronspec'])
    if type_name == 'AnalogDevice':
        return AnalogDevice(name, rcv, fields['port'], percept=fields['percept'],
                            minimum=fields['minimum'], maximum=fields['maximum'])
    if type_name == 'SlowPwmDevice':
        return SlowPwmDevice(name, rcv, fields['port'],
                             inverted=fields['inverted'], cycle=fields['cycle'])
    if type_name == 'SwitchDevice':
        return SwitchDevice(name, rcv, fields['port'], inverted=fields['inverted'])
    if type_name == 'MaximumCtrl':
        return MaximumCtrl(name, rcv, fields['setpoint'], hysteresis=fields['hysteresis'])
    if type_name == 'MinimumCtrl':
        return MinimumCtrl(name, rcv, fields['setpoint'], hysteresis=fields['hysteresis'])
    if type_name == 'PidCtrl':
        return PidCtrl(name, rcv, fields['setpoint'], p_fact=fields['p_fact'],
                       i_fact=fields['i_fact'], d_fact=fields['d_fact'])
    if type_name == 'SunCtrl':
        return SunCtrl(name, rcv, xscend=fields['xscend'])
    if type_name == 'FadeCtrl':
        return FadeCtrl(name, rcv, fade_time=fields['fade_time'], fade_out=fields['fade_out'])
    if type_name == 'AvgAux':
        return AvgAux(name, rcv, unfair_avg=int(fields['unfair_avg']))
    if type_name == 'MaxAux':
        return MaxAux(name, rcv)
    if type_name == 'MinAux':
        return MinAux(name, rcv)
    if type_name == 'ScaleAux':
        return ScaleAux(name, rcv, fields['unit'], offset=fields['offset'],
                        factor=fields['factor'])
    if type_name == 'History':
        return History(name, rcv, duration=int(fields['duration']))

    raise ValueError(f'Unknown or non-creatable node type: {type_name!r}')  # pragma: no cover


def compute_node_id(name: str) -> str:
    """ replicate BusNode.__init__'s id-from-name derivation, so the API
        can check for a collision *before* constructing (and thus
        side-effecting, e.g. driver creation) a new node.
    """
    node_id = name.lower()
    node_id = node_id.replace(' ', '').replace('.', '').replace(';', '')
    node_id = node_id.replace('Ä', 'Ae').replace('ä', 'ae')
    node_id = node_id.replace('Ö', 'Oe').replace('ö', 'oe')
    node_id = node_id.replace('Ü', 'Ue').replace('ü', 'ue')
    node_id = node_id.replace('-', '_').replace('ß', 'ss')
    return str(node_id.encode('ascii', 'xmlcharrefreplace'), errors='strict')


def would_create_cycle(bus: MsgBus, node_id: str, new_receives: list[str]) -> bool:
    """ True if wiring 'node_id' to receive from 'new_receives' would
        create a cycle, i.e. any of the new sources (directly or
        transitively, via its own 'receives') already depends on
        'node_id'.
    """
    for start in new_receives:
        if start == node_id:
            return True
        visited: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur == node_id:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            node = bus.get_node(cur)
            if node:
                stack.extend(node.receives)
    return False


def get_db_path(instance_path: str, filename: str = DEFAULT_DB_FILENAME) -> str:
    """ build the full path of the SQLite database file
    """
    return path.join(instance_path, filename)


def get_connection(db_path: str) -> sqlite3.Connection:
    """ open a SQLite connection with sane defaults and ensure the
        schema exists
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """ create the nodes table (and the related templates/snapshots
        tables) if they do not exist yet
    """
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id     TEXT PRIMARY KEY,
                type   TEXT NOT NULL,
                name   TEXT,
                params TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS node_templates (
                name  TEXT PRIMARY KEY,
                descr TEXT,
                data  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topology_snapshots (
                name       TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                data       TEXT NOT NULL
            )
        """)


def topology_exists(db_path: str) -> bool:
    """ True if a usable topology (with at least 1 node) is stored
    """
    if not path.exists(db_path):
        return False
    conn = get_connection(db_path)
    try:
        row = conn.execute('SELECT COUNT(*) AS n FROM nodes').fetchone()
        return bool(row and row['n'] > 0)
    finally:
        conn.close()


def _cond_to_dict(cond: Any) -> dict[str, Any]:
    """ convert an AlertCond (e.g. AlertAbove/AlertBelow) to a plain,
        JSON serializable dict
    """
    return {
        'class': type(cond).__name__,
        'node_id': cond.node_id,
        'limit': cond.limit,
        'duration': getattr(cond, 'duration', 0),
    }


def _dict_to_cond(d: dict[str, Any]) -> Any:
    """ reconstruct an AlertCond from a plain dict, restricted to the
        known AlertCond classes in ALERT_COND_FACTORY
    """
    cls = ALERT_COND_FACTORY.get(d['class'])
    if not cls:
        raise ValueError(f"Unknown alert condition class: {d['class']!r}")
    return cls(d['node_id'], limit=d['limit'], duration=d.get('duration', 0))


def serialize_node(node: BusNode) -> dict[str, Any]:
    """ build the JSON-able state dict for a single node,
        node-type specific quirks (currently only Alert.conditions)
        are normalized here. Used both for SQLite persistence
        (save_topology) and for the REST API (aquaPi/api.py), so the
        API never needs jsonpickle/object introspection.
    """
    state = dict(node.__getstate__())
    if isinstance(node, Alert):
        state['conditions'] = [_cond_to_dict(c) for c in state['conditions']]
    return state


def _deserialize_node(type_name: str, state: dict[str, Any]) -> BusNode:
    """ reconstruct a single node from its stored type name and state,
        using only the whitelisted NODE_FACTORY - never pickle/eval
    """
    cls = NODE_FACTORY.get(type_name)
    if not cls:
        raise ValueError(f'Unknown node type in database: {type_name!r}')

    state = dict(state)
    if cls is Alert:
        state['conditions'] = {_dict_to_cond(d) for d in state['conditions']}

    node = cls.__new__(cls)
    node.__setstate__(state)
    # every concrete node type overrides __setstate__() without calling
    # super() (they call their own __init__() instead), so the generic
    # 'group'/'pos_x'/'pos_y' attributes added to BusNode are restored
    # centrally here instead of touching every single node subclass
    node.group = state.get('group', '')
    node.pos_x = state.get('pos_x', 0.0)
    node.pos_y = state.get('pos_y', 0.0)
    return node


def save_topology(bus: MsgBus, db_path: str) -> None:
    """ persist all nodes currently registered on the bus to SQLite,
        replacing the previously stored topology
    """
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute('DELETE FROM nodes')
            for node in bus.nodes:
                state = serialize_node(node)
                params = json.dumps(state)
                conn.execute(
                    'INSERT INTO nodes (id, type, name, params) VALUES (?, ?, ?, ?)',
                    (node.id, type(node).__name__, node.name, params)
                )
        log.info('save_topology: %d nodes written to %s', len(bus.nodes), db_path)
    finally:
        conn.close()


def load_topology(db_path: str) -> MsgBus:
    """ (re-)create a MsgBus and all its nodes from SQLite
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute('SELECT id, type, name, params FROM nodes').fetchall()
    finally:
        conn.close()

    bus = MsgBus(threaded=False)
    nodes: list[BusNode] = []
    for row in rows:
        state = json.loads(row['params'])
        try:
            nodes.append(_deserialize_node(row['type'], state))
        except (ValueError, KeyError, TypeError, DriverError):
            log.exception('load_topology: failed to restore node %r (type %r), skipping',
                          row['id'], row['type'])

    for node in nodes:
        try:
            node.plugin(bus)
        except (ValueError, KeyError, TypeError, DriverError):
            log.exception('load_topology: failed to plug in node %r, skipping',
                          getattr(node, 'id', '?'))

    log.info('load_topology: %d nodes restored from %s', len(nodes), db_path)
    return bus


def migrate_pickle_to_sqlite(pickle_path: str, db_path: str) -> bool:
    """ one-time migration of an existing topo.pickle into the new
        SQLite database. The original file is kept as '<pickle_path>.bak',
        never deleted.
        Returns True if a migration was performed.
    """
    if not path.exists(pickle_path):
        return False
    if topology_exists(db_path):
        # already migrated (or a fresh SQLite topology exists) - don't overwrite
        return False

    import pickle  # local import: only ever used for this one-time migration
    log.brief('Migrating legacy %s to SQLite %s ...', pickle_path, db_path)
    try:
        with open(pickle_path, 'rb') as p:
            bus: MsgBus = pickle.load(p)
    except Exception:
        # a damaged or incompatible (e.g. from an older code version)
        # topo.pickle must never crash startup - just skip the migration,
        # the caller falls back to a fresh default topology instead.
        log.exception('Migration of %s failed, file is damaged or incompatible.'
                      ' Keeping it untouched and starting with a fresh topology.',
                      pickle_path)
        return False

    save_topology(bus, db_path)
    bus.teardown()

    backup_path = pickle_path + '.bak'
    replace(pickle_path, backup_path)
    log.brief('Migration done, legacy file kept as %s', backup_path)
    return True


# --- node-combination templates (/config, Step 13) ----------------------
#
# A template is a small, portable sub-graph of nodes (e.g. "pH control
# with CO2 valve") that can be inserted into the live topology multiple
# times. Alert nodes are intentionally excluded (same reasoning as
# NODE_TYPE_SCHEMA: their 'receives' is derived from 'conditions', a set
# of objects, not a plain field - out of scope for this generic editor).
# 'receives' references that point *outside* the captured node set are
# dropped, since the template must remain insertable without depending
# on specific, possibly absent, external node ids.

def capture_node_template(bus: MsgBus, node_ids: list[str]) -> dict[str, Any]:
    """ build a portable template dict from a set of currently live
        node ids. Raises ValueError if a node id is unknown or refers
        to an Alert node.
    """
    selected = set(node_ids)
    entries = []
    for node_id in node_ids:
        node = bus.get_node(node_id)
        if not node:
            raise ValueError(f'Unknown node id: {node_id}')
        if isinstance(node, Alert):
            raise ValueError('Alert nodes cannot be part of a template')
        state = serialize_node(node)
        state['receives'] = [r for r in state.get('receives', []) if r in selected]
        if 'port' in state:
            # hardware/driver ports are an exclusive resource (only one
            # node may own a given port at a time) - the captured node
            # is still live and keeps using its port, so a template must
            # not carry it along, or instantiating the template would
            # always fail with a 'port already in use' error. Users
            # re-assign a port after inserting the template instead.
            state['port'] = ''
        entries.append({'id': node.id, 'type': type(node).__name__, 'state': state})
    return {'nodes': entries}


def list_templates(db_path: str) -> list[dict[str, Any]]:
    """ list all templates (name, description, node count) """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            'SELECT name, descr, data FROM node_templates ORDER BY name'
        ).fetchall()
        result = []
        for row in rows:
            data = json.loads(row['data'])
            result.append({
                'name': row['name'],
                'descr': row['descr'],
                'node_count': len(data.get('nodes', [])),
            })
        return result
    finally:
        conn.close()


def get_template(db_path: str, name: str) -> dict[str, Any] | None:
    """ fetch one template including its full node data """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT name, descr, data FROM node_templates WHERE name = ?', (name,)
        ).fetchone()
        if not row:
            return None
        return {'name': row['name'], 'descr': row['descr'], 'data': json.loads(row['data'])}
    finally:
        conn.close()


def save_template(db_path: str, name: str, descr: str, data: dict[str, Any]) -> None:
    """ store (create or replace) a named template """
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO node_templates (name, descr, data) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET descr = excluded.descr, data = excluded.data
            """, (name, descr, json.dumps(data)))
    finally:
        conn.close()


def delete_template(db_path: str, name: str) -> bool:
    """ remove a template, returns True if it existed """
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute('DELETE FROM node_templates WHERE name = ?', (name,))
            return cur.rowcount > 0
    finally:
        conn.close()


def instantiate_template(bus: MsgBus, data: dict[str, Any]) -> list[BusNode]:
    """ insert a template's nodes into the live bus, assigning fresh,
        collision-free names/ids (the stored name, with a ' (2)',
        ' (3)', ... suffix appended if it - or its derived id - is
        already taken) and remapping the internal 'receives' wiring to
        the new ids. Nodes are reconstructed via the same whitelisted
        NODE_FACTORY used everywhere else in this module (never
        pickle/eval). Returns the list of newly created, plugged-in
        nodes.
    """
    entries = data.get('nodes', [])
    used_ids = {node.id for node in bus.nodes}
    id_map: dict[str, str] = {}
    new_names: dict[str, str] = {}

    for entry in entries:
        base_name = entry['state']['name']
        candidate = base_name
        candidate_id = compute_node_id(candidate)
        suffix = 2
        while candidate_id in used_ids:
            candidate = f'{base_name} ({suffix})'
            candidate_id = compute_node_id(candidate)
            suffix += 1
        used_ids.add(candidate_id)
        new_names[entry['id']] = candidate
        id_map[entry['id']] = candidate_id

    new_nodes = []
    for entry in entries:
        state = dict(entry['state'])
        state['name'] = new_names[entry['id']]
        state['receives'] = [id_map[r] for r in state.get('receives', []) if r in id_map]
        if 'port' in state:
            # defense in depth: also blank ports here, not just in
            # capture_node_template(), so templates saved before this
            # fix (which may still carry a real port) don't crash the
            # insert with a 'port already in use' error either
            state['port'] = ''
        new_nodes.append(_deserialize_node(entry['type'], state))

    for node in new_nodes:
        node.plugin(bus)

    return new_nodes


# --- topology snapshots (/config, Step 13) -------------------------------
#
# A snapshot is a full, named export of the 'nodes' table, used for
# "save the whole configuration now, try something, restore it later".

def list_snapshots(db_path: str) -> list[dict[str, Any]]:
    """ list all snapshots (name, created_at), newest first """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            'SELECT name, created_at FROM topology_snapshots ORDER BY created_at DESC'
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_snapshot(db_path: str, name: str) -> None:
    """ capture the entire current 'nodes' table as a named snapshot
        (create, or overwrite if the name already exists)
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute('SELECT id, type, name, params FROM nodes').fetchall()
        data = [dict(row) for row in rows]
        with conn:
            conn.execute("""
                INSERT INTO topology_snapshots (name, data) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET data = excluded.data,
                                               created_at = datetime('now')
            """, (name, json.dumps(data)))
    finally:
        conn.close()


def get_snapshot(db_path: str, name: str) -> dict[str, Any] | None:
    """ fetch one snapshot including its full node-table export """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            'SELECT name, created_at, data FROM topology_snapshots WHERE name = ?', (name,)
        ).fetchone()
        if not row:
            return None
        return {'name': row['name'], 'created_at': row['created_at'], 'data': json.loads(row['data'])}
    finally:
        conn.close()


def delete_snapshot(db_path: str, name: str) -> bool:
    """ remove a snapshot, returns True if it existed """
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute('DELETE FROM topology_snapshots WHERE name = ?', (name,))
            return cur.rowcount > 0
    finally:
        conn.close()


def restore_snapshot_into_bus(bus: MsgBus, snapshot_rows: list[dict[str, Any]]) -> None:
    """ replace the live bus' entire node set with the nodes stored in
        a snapshot: tears down every currently plugged-in node first,
        then reconstructs and plugs in every snapshot node (whitelisted
        NODE_FACTORY only, never pickle/eval). A node that fails to
        restore or to plug in (e.g. an unknown type from a foreign
        export, or a driver/port error) is skipped with a log entry
        rather than aborting the whole restore - once teardown() has
        run, aborting would leave the live bus permanently empty
        instead of just missing the one problematic node.
    """
    bus.teardown()
    nodes = []
    for row in snapshot_rows:
        try:
            nodes.append(_deserialize_node(row['type'], row['params']
                                           if isinstance(row['params'], dict)
                                           else json.loads(row['params'])))
        except (ValueError, KeyError, TypeError, DriverError):
            log.exception('restore_snapshot_into_bus: failed to restore node %r (type %r), skipping',
                          row.get('id'), row.get('type'))
    for node in nodes:
        try:
            node.plugin(bus)
        except (ValueError, KeyError, TypeError, DriverError):
            log.exception('restore_snapshot_into_bus: failed to plug in node %r, skipping',
                          getattr(node, 'id', '?'))


# --- users / authentication -------------------------------------------

def get_users_db_path(instance_path: str, filename: str = DEFAULT_USERS_DB_FILENAME) -> str:
    """ build the full path of the users SQLite database file
    """
    return path.join(instance_path, filename)


def get_users_connection(db_path: str) -> sqlite3.Connection:
    """ open a SQLite connection to the users database, ensuring the
        schema exists
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'viewer'
                    CHECK (role IN ('viewer', 'operator', 'admin')),
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_config (
                channel TEXT PRIMARY KEY,
                params  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_notification_prefs (
                user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                alert_node_id TEXT NOT NULL,
                channel       TEXT NOT NULL DEFAULT 'none'
                    CHECK (channel IN ('email', 'telegram', 'none')),
                PRIMARY KEY (user_id, alert_node_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dashboards (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                layout  TEXT NOT NULL
            )
        """)
    return conn


def create_user(db_path: str, username: str, password: str,
                role: str = 'viewer') -> int:
    """ create a new user with a securely hashed password.
        Raises ValueError if the username already exists or the role
        is invalid.
    """
    if role not in VALID_ROLES:
        raise ValueError(f'Invalid role: {role!r}')

    conn = get_users_connection(db_path)
    try:
        password_hash = generate_password_hash(password)
        try:
            with conn:
                cur = conn.execute(
                    'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                    (username, password_hash, role)
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f'Username already exists: {username!r}') from None
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int) -> dict[str, Any] | None:
    """ fetch a single user (without password hash exposure concerns,
        the caller decides what to expose)
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_username(db_path: str, username: str) -> dict[str, Any] | None:
    """ fetch a single user by username (case-sensitive)
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users(db_path: str) -> list[dict[str, Any]]:
    """ return all users, ordered by username
    """
    conn = get_users_connection(db_path)
    try:
        rows = conn.execute('SELECT * FROM users ORDER BY username').fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count_admins(db_path: str) -> int:
    """ number of users with role 'admin', used to prevent
        locking everyone out by removing the last admin
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'").fetchone()
        return row['n'] if row else 0
    finally:
        conn.close()


def ensure_default_admin(db_path: str) -> tuple[str, str] | None:
    """ on first start (no users table content yet), create a default
        admin account with a freshly generated random password.
        Returns (username, password) if a default admin was created,
        None if users already exist.
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute('SELECT COUNT(*) AS n FROM users').fetchone()
        if row and row['n'] > 0:
            return None
    finally:
        conn.close()

    username = 'admin'
    password = secrets.token_urlsafe(12)
    create_user(db_path, username, password, role='admin')
    return username, password


# --- notification config (Email/Telegram credentials) ------------------
#
# 'channel' here matches the keys used by aquaPi/driver/DriverText.py's
# driver_config dict: 'Email' and 'Telegram'. 'params' stores the JSON
# encoded *list* of credential dicts (multiple accounts per channel are
# supported, exactly like the previous config.json structure).

NOTIFICATION_CHANNELS = ('Email', 'Telegram')


def get_notification_config(db_path: str, channel: str) -> list[dict[str, Any]] | None:
    """ return the stored credential list for a channel ('Email'/'Telegram'),
        or None if nothing is configured for it
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute(
            'SELECT params FROM notification_config WHERE channel = ?', (channel,)
        ).fetchone()
        return json.loads(row['params']) if row else None
    finally:
        conn.close()


def set_notification_config(db_path: str, channel: str,
                            configs: list[dict[str, Any]]) -> None:
    """ store (create or replace) the credential list for a channel
    """
    if channel not in NOTIFICATION_CHANNELS:
        raise ValueError(f'Invalid notification channel: {channel!r}')

    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO notification_config (channel, params) VALUES (?, ?)
                ON CONFLICT(channel) DO UPDATE SET params = excluded.params
            """, (channel, json.dumps(configs)))
    finally:
        conn.close()


def migrate_notification_config_from_json(globals_cfg: dict[str, Any],
                                          db_path: str) -> bool:
    """ one-time migration of Email/Telegram credentials, previously read
        directly from config.json into MachineRoom.globals, into the
        notification_config table. Idempotent: does nothing once any
        channel is already present in the DB.
        Returns True if anything was migrated.
    """
    migrated = False
    for channel in NOTIFICATION_CHANNELS:
        if channel not in globals_cfg:
            continue
        if get_notification_config(db_path, channel) is not None:
            continue
        configs = globals_cfg[channel]
        if not isinstance(configs, list):
            configs = [configs]
        set_notification_config(db_path, channel, configs)
        log.brief('Migrated %s notification config from config.json to %s',
                  channel, db_path)
        migrated = True
    return migrated


# --- per-user, per-alert notification preferences -----------------------

def set_user_notification_pref(db_path: str, user_id: int, alert_node_id: str,
                               channel: str) -> None:
    """ set (create or replace) the preferred notification channel a
        user wants for a given Alert node ('email'/'telegram'/'none')
    """
    if channel not in ('email', 'telegram', 'none'):
        raise ValueError(f'Invalid notification channel: {channel!r}')

    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO user_notification_prefs (user_id, alert_node_id, channel)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, alert_node_id) DO UPDATE SET channel = excluded.channel
            """, (user_id, alert_node_id, channel))
    finally:
        conn.close()


def get_user_notification_pref(db_path: str, user_id: int, alert_node_id: str) -> str:
    """ return the preferred channel of a user for a given alert,
        defaults to 'none' if nothing was ever configured
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute(
            'SELECT channel FROM user_notification_prefs '
            'WHERE user_id = ? AND alert_node_id = ?',
            (user_id, alert_node_id)
        ).fetchone()
        return row['channel'] if row else 'none'
    finally:
        conn.close()


def list_user_notification_prefs(db_path: str, user_id: int) -> list[dict[str, Any]]:
    """ return all (alert_node_id, channel) prefs configured by one user
    """
    conn = get_users_connection(db_path)
    try:
        rows = conn.execute(
            'SELECT alert_node_id, channel FROM user_notification_prefs '
            'WHERE user_id = ? ORDER BY alert_node_id',
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_prefs_for_alert(db_path: str, alert_node_id: str) -> list[dict[str, Any]]:
    """ return all users (with their preferred channel) that want to be
        notified for a given Alert node, excluding those set to 'none'
    """
    conn = get_users_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.id AS user_id, u.username AS username, p.channel AS channel
            FROM user_notification_prefs p
            JOIN users u ON u.id = p.user_id
            WHERE p.alert_node_id = ? AND p.channel != 'none'
        """, (alert_node_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# --- user-specific dashboards --------------------------------------------
#
# Each user's dashboard (visible controllers/groups, layout, ordering) is
# stored as a single JSON blob, keyed by user_id. This keeps the schema
# minimal and flexible, matching the heterogeneous widget structure of
# the Vuetify frontend - no dashboard row means the frontend falls back
# to its own default view (all controllers, no grouping).

DEFAULT_DASHBOARD_LAYOUT: list[dict[str, Any]] = []


def get_dashboard(db_path: str, user_id: int) -> list[dict[str, Any]]:
    """ return the stored dashboard layout for a user, or the default
        (empty) layout if the user never saved one
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute(
            'SELECT layout FROM dashboards WHERE user_id = ?', (user_id,)
        ).fetchone()
        return json.loads(row['layout']) if row else list(DEFAULT_DASHBOARD_LAYOUT)
    finally:
        conn.close()


def set_dashboard(db_path: str, user_id: int, layout: list[dict[str, Any]]) -> None:
    """ store (create or replace) the dashboard layout of a user
    """
    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO dashboards (user_id, layout) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET layout = excluded.layout
            """, (user_id, json.dumps(layout)))
    finally:
        conn.close()


# --- module-level 'current' users DB path, mirrors the driver_config
#     pattern in aquaPi/driver/__init__.py: set once at startup by
#     MachineRoom, then read by alert_nodes.py to look up per-user
#     notification preferences without needing Flask's app context.

_current_users_db_path: str | None = None


def set_current_users_db_path(db_path: str | None) -> None:
    # pylint: disable-next=W0603
    global _current_users_db_path
    _current_users_db_path = db_path


def get_current_users_db_path() -> str | None:
    return _current_users_db_path
