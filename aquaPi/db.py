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

import copy
import json
import logging
import smtplib
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from os import path, replace, makedirs, remove, listdir
from typing import Any

from werkzeug.security import generate_password_hash

from .machineroom.msg_bus import MsgBus, BusNode, BusRole
from .machineroom.ctrl_nodes import (MaximumCtrl, MinimumCtrl, PidCtrl,
                                     SunCtrl, FadeCtrl)
from .passphrase import generate_aquatic_passphrase, generate_url_token
from .machineroom.in_nodes import (AnalogInput, SwitchInput, ScheduleInput,
                                   UiSwitchInput, UiAnalogInput)
from .machineroom.out_nodes import (AnalogDevice, SlowPwmDevice, SwitchDevice)
from .machineroom.aux_nodes import (AvgAux, MaxAux, MinAux, ScaleAux, UiDisplay)
from .machineroom.hist_nodes import History
from .machineroom.alert_nodes import (Alert, AlertAbove, AlertBelow)
from .driver import IoRegistry
from .driver.base import DriverError


log = logging.getLogger('aquaPi.db')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


DEFAULT_DB_FILENAME = 'topo.sqlite'
DEFAULT_USERS_DB_FILENAME = 'users.sqlite'

VALID_ROLES = ('viewer', 'operator', 'admin')

# reserved account auto-logged-in for requests with no session (see
# auth.py's before_request hook) - lets the SPA show a dashboard without
# requiring login, while still going through the normal role machinery
ANONYMOUS_USERNAME = '<anonymous>'

# --- login security (Step 22) ---------------------------------------
PASSWORD_RESET_TOKEN_TTL_MINUTES = 30
LOGIN_MAX_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 15
LOGIN_LOCKOUT_MINUTES = 15

# Fixed, explicit whitelist of node classes that may be reconstructed
# from the database. This is the core safety guarantee: only these
# classes can ever be instantiated, and only via their own __setstate__.
NODE_FACTORY: dict[str, type[BusNode]] = {
    cls.__name__: cls for cls in (
        MaximumCtrl, MinimumCtrl, PidCtrl, SunCtrl, FadeCtrl,
        AnalogInput, SwitchInput, ScheduleInput,
        UiSwitchInput, UiAnalogInput,
        AnalogDevice, SlowPwmDevice, SwitchDevice,
        AvgAux, MaxAux, MinAux, ScaleAux, UiDisplay,
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
            {'key': 'port', 'label': 'Input port', 'type': 'select', 'default': ''},
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
            {'key': 'port', 'label': 'Input port', 'type': 'select', 'default': ''},
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
    'UiSwitchInput': {
        'receives': 'none',
        'fields': [
            {'key': 'initval', 'label': 'Initial value', 'type': 'checkbox', 'default': False},
        ],
    },
    'UiAnalogInput': {
        'receives': 'none',
        'fields': [
            {'key': 'initval', 'label': 'Initial value', 'type': 'number', 'default': 0.0},
            {'key': 'unit', 'label': 'Unit', 'type': 'text', 'default': ''},
            {'key': 'vmin', 'label': 'Minimum', 'type': 'number', 'default': 0.0},
            {'key': 'vmax', 'label': 'Maximum', 'type': 'number', 'default': 100.0},
            {'key': 'step', 'label': 'Step', 'type': 'number', 'default': 1.0},
        ],
    },
    'AnalogDevice': {
        'receives': 'single',
        'fields': [
            {'key': 'port', 'label': 'Output port', 'type': 'select', 'default': ''},
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
            {'key': 'port', 'label': 'Output port', 'type': 'select', 'default': ''},
            {'key': 'cycle', 'label': 'PWM cycle time [s]', 'type': 'number',
             'min': 10, 'max': 300, 'default': 60.0},
            {'key': 'inverted', 'label': 'Inverted', 'type': 'checkbox', 'default': False},
        ],
    },
    'SwitchDevice': {
        'receives': 'single',
        'fields': [
            {'key': 'port', 'label': 'Output port', 'type': 'select', 'default': ''},
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
    'UiDisplay': {
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
            {'key': 'capacity', 'label': 'Capacity [h]', 'type': 'number',
             'min': 1, 'default': 24},
        ],
    },
}


def get_node_type_schema() -> dict[str, dict[str, Any]]:
    """ Deep-copy NODE_TYPE_SCHEMA and populate live 'options' lists for
        node types that have a 'port' field, sourced from IoRegistry.
    """
    schema = copy.deepcopy(NODE_TYPE_SCHEMA)
    for type_name, cls in NODE_FACTORY.items():
        if type_name not in schema:
            continue
        port_funcs = getattr(cls, '_port_funcs', None)
        if not port_funcs:
            continue
        try:
            free = IoRegistry.get().get_ports_by_function(port_funcs, in_use=False)
            options = sorted(free)
        except Exception:
            options = []
        for field in schema[type_name].get('fields', []):
            if field.get('key') == 'port':
                field['type'] = 'select'
                field['options'] = options
    return schema


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
    if type_name == 'UiSwitchInput':
        return UiSwitchInput(name, initval=fields['initval'])
    if type_name == 'UiAnalogInput':
        return UiAnalogInput(name, fields['unit'], initval=fields['initval'],
                             vmin=fields['vmin'], vmax=fields['vmax'], step=fields['step'])
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
    if type_name == 'UiDisplay':
        return UiDisplay(name, rcv)
    if type_name == 'ScaleAux':
        return ScaleAux(name, rcv, fields['unit'], offset=fields['offset'],
                        factor=fields['factor'])
    if type_name == 'History':
        return History(name, rcv, capacity=int(fields['capacity']))

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
    node_id = node_id.replace('/', '_').replace('\\', '_')
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


def prune_dangling_references(bus: MsgBus, deleted_id: str) -> None:
    """ remove every reference to 'deleted_id' from every other live
        node's wiring, right before it is actually deleted. Plain nodes:
        drop it from their 'receives' list directly. Alert nodes: their
        'receives' is derived from 'conditions' (never directly editable -
        see NODE_TYPE_SCHEMA's Alert exclusion), so instead drop every
        AlertCond that watches 'deleted_id' and recompute 'receives' from
        what's left, or a deleted node would leave an orphaned/dangling
        AlertCond and a stale 'receives' entry behind forever.
    """
    for other in bus.get_nodes():
        if other.id == deleted_id:
            continue
        if other.ROLE == BusRole.ALERTS:
            remaining = {c for c in other.conditions if c.node_id != deleted_id}
            if len(remaining) != len(other.conditions):
                other.conditions = remaining
                other.receives = [c.node_id for c in other.conditions]
            continue
        if deleted_id in other.receives:
            other.receives = [r for r in other.receives if r != deleted_id]


class ConfigDiffError(ValueError):
    """ raised by apply_config_diff() when any single part of a diff is
        invalid. Carries the offending 'entry' (the create/update dict,
        or a small identifying dict for deletes/cycle errors) so the
        API can report which part of the diff failed.
    """
    def __init__(self, message: str, entry: dict[str, Any] | None = None):
        super().__init__(message)
        self.entry = entry


# TODO(config-receives-type-filtering): only cardinality is checked here -
# nothing validates the resolved sources' data_range compatibility (e.g. a
# STRING-typed Alert can be wired into a History, which can't store it).
# See .junie/plans/config-receives-type-filtering.md
def _check_receives_cardinality(schema: dict[str, Any], resolved: list[str],
                                entry: dict[str, Any]) -> None:
    if schema['receives'] == 'none' and resolved:
        raise ConfigDiffError('This node type does not accept any receives', entry)
    if schema['receives'] == 'single' and len(resolved) > 1:
        raise ConfigDiffError('This node type accepts at most 1 receives entry', entry)


def _would_create_cycle_virtual(graph: dict[str, list[str]], node_id: str,
                                new_receives: list[str]) -> bool:
    """ would_create_cycle(), but operating on a caller-supplied,
        already-post-diff {id: receives} graph instead of the live bus
        - used by apply_config_diff() to validate the *result* of a
        diff before anything is actually applied.
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
            stack.extend(graph.get(cur, []))
    return False


def apply_config_diff(bus: MsgBus, diff: dict[str, Any], validate_fields) -> dict[str, Any]:
    """ atomically validate and apply a bulk create/update/delete diff
        against the live bus - the backend counterpart of the /config
        editor's client-side draft ("Speichern" button, POST
        /api/config/apply in aquaPi/api.py). Either the *entire* diff
        is applied, or (on any validation error) *none* of it is - the
        live bus is left completely untouched in that case.

        'diff' is a dict with optional list entries:
          'creates': [{'temp_id'?, 'type', 'name', 'receives'?, 'fields'?,
                       'group'?, 'pos_x'?, 'pos_y'?}, ...]
          'updates': [{'id', 'receives'?, 'fields'?, 'group'?, 'pos_x'?,
                       'pos_y'?}, ...]
          'deletes': ['id', ...]

        A 'receives' entry (in both creates and updates) may reference
        either an existing (and not concurrently deleted) node id, or
        the 'temp_id' of another entry of the same 'creates' list -
        those client-side temp ids are remapped to the real, freshly
        assigned node id of that entry.

        'validate_fields' is the caller-supplied, api._validate_fields
        compatible callable (schema_fields, raw_fields, require_all) ->
        dict; injected here to reuse the existing per-type field
        validation without introducing a circular import between
        aquaPi.api and aquaPi.db.

        Returns {'id_map': {temp_id: real_id, ...}} on success.
        Raises ConfigDiffError (without having changed anything) on
        any validation failure.
    """
    creates = diff.get('creates') or []
    updates = diff.get('updates') or []
    deletes = diff.get('deletes') or []
    if not isinstance(creates, list) or not isinstance(updates, list) \
            or not isinstance(deletes, list):
        raise ConfigDiffError("'creates', 'updates' and 'deletes' must each be a list")

    live_nodes = {n.id: n for n in bus.get_nodes()}

    deleted_ids: set[str] = set()
    for del_id in deletes:
        if not isinstance(del_id, str) or del_id not in live_nodes:
            raise ConfigDiffError(f'Unknown node id to delete: {del_id!r}', {'id': del_id})
        deleted_ids.add(del_id)

    remaining_ids = set(live_nodes) - deleted_ids

    updates_by_id: dict[str, dict[str, Any]] = {}
    for upd in updates:
        if not isinstance(upd, dict):
            raise ConfigDiffError('Each update entry must be an object', upd)
        upd_id = upd.get('id')
        if not isinstance(upd_id, str) or upd_id not in remaining_ids:
            raise ConfigDiffError(f'Unknown or deleted node id to update: {upd_id!r}', upd)
        if upd_id in updates_by_id:
            raise ConfigDiffError(f'Duplicate update for node id: {upd_id!r}', upd)
        updates_by_id[upd_id] = upd

    # --- creates: type/name/collision/field validation. build_node()
    #     only constructs the node object, it never plugin()s it onto
    #     the bus, so this has no side effect on the live bus yet.
    temp_id_map: dict[str, str] = {}
    new_ids: set[str] = set()
    prepared_creates: list[dict[str, Any]] = []

    for entry in creates:
        if not isinstance(entry, dict):
            raise ConfigDiffError('Each create entry must be an object', entry)

        type_name = entry.get('type')
        schema = NODE_TYPE_SCHEMA.get(type_name)
        if not schema:
            raise ConfigDiffError(f'Unknown or non-creatable node type: {type_name!r}', entry)

        name = (entry.get('name') or '').strip()
        if not name:
            raise ConfigDiffError('name must not be empty', entry)

        node_id = compute_node_id(name)
        if node_id in remaining_ids or node_id in new_ids:
            raise ConfigDiffError(f'A node named {name!r} already exists', entry)
        new_ids.add(node_id)

        temp_id = entry.get('temp_id')
        if temp_id is not None:
            if str(temp_id) in temp_id_map:
                raise ConfigDiffError(f'Duplicate temp_id: {temp_id!r}', entry)
            temp_id_map[str(temp_id)] = node_id

        raw_receives = entry.get('receives', [])
        if not isinstance(raw_receives, list) or not all(isinstance(r, str) for r in raw_receives):
            raise ConfigDiffError('receives must be a list of node ids', entry)

        raw_fields = entry.get('fields', {})
        if not isinstance(raw_fields, dict):
            raise ConfigDiffError('fields must be a JSON object', entry)
        try:
            fields = validate_fields(schema['fields'], raw_fields, require_all=True)
        except (ValueError, KeyError) as ex:
            raise ConfigDiffError(str(ex), entry) from ex

        prepared_creates.append({
            'entry': entry, 'node_id': node_id, 'schema': schema,
            'raw_receives': raw_receives, 'fields': fields,
        })

    all_ids = remaining_ids | new_ids

    def resolve_ref(ref: str, err_entry: dict[str, Any]) -> str:
        if ref in temp_id_map:
            return temp_id_map[ref]
        if ref in all_ids:
            return ref
        raise ConfigDiffError(f'Unknown receives node id: {ref!r}', err_entry)

    # --- resolve receives (temp-id remap) + cardinality checks, and
    #     build the virtual, post-diff {id: receives} wiring graph
    #     used for cycle detection below ---
    virtual_receives: dict[str, list[str]] = {
        node_id: list(node.receives)
        for node_id, node in live_nodes.items() if node_id in remaining_ids
    }

    for prep in prepared_creates:
        resolved = [resolve_ref(r, prep['entry']) for r in prep['raw_receives']]
        _check_receives_cardinality(prep['schema'], resolved, prep['entry'])
        prep['resolved_receives'] = resolved
        virtual_receives[prep['node_id']] = resolved

    for upd_id, upd in updates_by_id.items():
        node = live_nodes[upd_id]
        schema = NODE_TYPE_SCHEMA.get(type(node).__name__)

        if 'receives' in upd:
            raw_receives = upd['receives']
            if not isinstance(raw_receives, list) or not all(isinstance(r, str) for r in raw_receives):
                raise ConfigDiffError('receives must be a list of node ids', upd)
            if not schema:
                raise ConfigDiffError(f'{type(node).__name__} does not support changing receives', upd)
            resolved = [resolve_ref(r, upd) for r in raw_receives]
            _check_receives_cardinality(schema, resolved, upd)
            upd['_resolved_receives'] = resolved
            virtual_receives[upd_id] = resolved

        if 'fields' in upd:
            raw_fields = upd['fields']
            if not isinstance(raw_fields, dict):
                raise ConfigDiffError('fields must be a JSON object', upd)
            if not schema:
                raise ConfigDiffError(f'{type(node).__name__} does not support editing fields', upd)
            try:
                upd['_fields'] = validate_fields(schema['fields'], raw_fields, require_all=False)
            except ValueError as ex:
                raise ConfigDiffError(str(ex), upd) from ex

        for key in ('pos_x', 'pos_y'):
            if key in upd:
                try:
                    upd['_' + key] = float(upd[key])
                except (TypeError, ValueError):
                    raise ConfigDiffError(f'{key} must be a number', upd)

    for node_id, receives in virtual_receives.items():
        if _would_create_cycle_virtual(virtual_receives, node_id, receives):
            raise ConfigDiffError('This wiring would create a cycle', {'id': node_id})

    # --- everything about this diff has been validated: apply it for
    #     real, deletes first, then updates, then creates ---
    for del_id in deleted_ids:
        node = live_nodes[del_id]
        prune_dangling_references(bus, del_id)
        node.pullout()

    for upd_id, upd in updates_by_id.items():
        node = live_nodes[upd_id]
        if '_resolved_receives' in upd:
            node.receives = upd['_resolved_receives']
        if '_fields' in upd:
            for key, value in upd['_fields'].items():
                setattr(node, key, value)
        if 'group' in upd:
            node.group = str(upd['group'] or '')
        if '_pos_x' in upd:
            node.pos_x = upd['_pos_x']
        if '_pos_y' in upd:
            node.pos_y = upd['_pos_y']

    for prep in prepared_creates:
        entry = prep['entry']
        node = build_node(entry['type'], entry.get('name', '').strip(),
                          prep['resolved_receives'], prep['fields'])
        node.group = str(entry.get('group', '') or '')
        try:
            node.pos_x = float(entry.get('pos_x', 0.0) or 0.0)
            node.pos_y = float(entry.get('pos_y', 0.0) or 0.0)
        except (TypeError, ValueError):
            node.pos_x = node.pos_y = 0.0
        node.plugin(bus)

    return {'id_map': temp_id_map}


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


def _notify_startup_failures(failures: list[str]) -> bool:
    """ best-effort: send one summary message via every configured
        Email/Telegram channel about node(s) that failed to load - a
        silently missing controller can be dangerous (e.g. a heater/pH
        regulation), so this doesn't rely on the user having created
        an Alert node or a browser being open to notice a log line.

        Uses the raw system-wide channel slots (driver_config['Email']/
        ['Telegram'], the same 'Email #1'/'Telegram #1'... ports Alert
        nodes use directly) rather than any specific Alert node's own
        config or per-user preferences, so this works even if the user
        never set up any Alert node at all. Does nothing (beyond the
        error already logged by the caller) if no Email/Telegram
        credentials are configured at all - there is no channel to
        reach the user through in that case.

        Returns True if at least one channel actually sent the
        message - callers that need a hard guarantee the user will be
        reached (see load_topology()) should escalate instead of
        continuing when this comes back False.
    """
    if not failures:
        return True

    from .driver import driver_config, IoRegistry
    from .driver.base import OutDriver, PortFunc

    text = ('aquaPi: %d node(s) failed to load at startup and are now '
            'MISSING from the running system:\n' % len(failures)
            + '\n'.join(failures))

    notified = False
    for channel in ('Email', 'Telegram'):
        for idx in range(len(driver_config.get(channel, []))):
            port_name = f'{channel} #{idx + 1}'
            driver = None
            try:
                driver = IoRegistry.get().driver_factory(port_name)
                if isinstance(driver, OutDriver) and driver.func == PortFunc.Tout:
                    driver.write(text)
                    log.info('Notified startup node-load failures via %s', port_name)
                    notified = True
            except Exception:
                log.exception('Failed to notify startup node-load failures via %s', port_name)
            finally:
                if driver:
                    IoRegistry.get().driver_destruct(port_name, driver)
    return notified


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
    failures: list[str] = []
    for row in rows:
        state = json.loads(row['params'])
        try:
            nodes.append(_deserialize_node(row['type'], state))
        except DriverError as ex:
            # expected/actionable (e.g. an unknown or already-used port) -
            # ex.msg alone says exactly what's wrong, a full traceback
            # would only bury that behind noise
            log.error('load_topology: failed to restore node %r (type %r), skipping: %s',
                      row['id'], row['type'], ex.msg)
            failures.append(f"{row['id']!r} ({row['type']}): {ex.msg}")
        except (ValueError, KeyError, TypeError) as ex:
            log.exception('load_topology: failed to restore node %r (type %r), skipping',
                          row['id'], row['type'])
            failures.append(f"{row['id']!r} ({row['type']}): {ex}")

    for node in nodes:
        try:
            node.plugin(bus)
        except DriverError as ex:
            log.error('load_topology: failed to plug in node %r, skipping: %s',
                      getattr(node, 'id', '?'), ex.msg)
            failures.append(f"{getattr(node, 'id', '?')!r}: {ex.msg}")
        except (ValueError, KeyError, TypeError) as ex:
            log.exception('load_topology: failed to plug in node %r, skipping',
                          getattr(node, 'id', '?'))
            failures.append(f"{getattr(node, 'id', '?')!r}: {ex}")

    log.info('load_topology: %d nodes restored from %s', len(nodes), db_path)

    if failures and not _notify_startup_failures(failures):
        # nobody could be reached remotely either (no Email/Telegram
        # configured, or every send attempt failed) - running with a
        # silently missing controller (e.g. heater/pH regulation) is
        # dangerous and no one would know. Abort startup loudly instead
        # of pretending everything is fine - whoever started this
        # process is far more likely to notice a hard failure right in
        # front of them than a quietly degraded running system.
        raise RuntimeError(
            'load_topology: %d node(s) failed to load, and no Email/Telegram '
            'notification could be sent either (nothing configured, or every '
            'attempt failed) - refusing to start with silently missing '
            'controllers. Fix the underlying issue (often another process, '
            'e.g. a different aquarium controller, holding the same port) '
            'and restart:\n%s' % (len(failures), '\n'.join(failures)))

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

    # avoid template nodes landing exactly on top of nodes already
    # present on the /config canvas: a template's positions are those
    # it was captured with, so a plain re-insert would overlap the
    # very nodes it was captured from. Shift the whole template
    # diagonally by a growing offset until none of its (approximate)
    # node-box footprints overlaps an already placed node.
    NODE_BOX_WIDTH = 190
    NODE_BOX_HEIGHT = 76
    OFFSET_STEP = 40.0
    existing_positions = [
        (float(node.pos_x or 0.0), float(node.pos_y or 0.0)) for node in bus.nodes
    ]
    offset_x = offset_y = 0.0
    for _ in range(50):
        collision = any(
            abs(float(entry['state'].get('pos_x', 0.0) or 0.0) + offset_x - ux) < NODE_BOX_WIDTH
            and abs(float(entry['state'].get('pos_y', 0.0) or 0.0) + offset_y - uy) < NODE_BOX_HEIGHT
            for entry in entries
            for (ux, uy) in existing_positions
        )
        if not collision:
            break
        offset_x += OFFSET_STEP
        offset_y += OFFSET_STEP

    new_nodes = []
    for entry in entries:
        state = dict(entry['state'])
        state['name'] = new_names[entry['id']]
        state['receives'] = [id_map[r] for r in state.get('receives', []) if r in id_map]
        state['pos_x'] = float(state.get('pos_x', 0.0) or 0.0) + offset_x
        state['pos_y'] = float(state.get('pos_y', 0.0) or 0.0) + offset_y
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
    failures: list[str] = []
    for row in snapshot_rows:
        try:
            nodes.append(_deserialize_node(row['type'], row['params']
                                           if isinstance(row['params'], dict)
                                           else json.loads(row['params'])))
        except DriverError as ex:
            log.error('restore_snapshot_into_bus: failed to restore node %r (type %r), skipping: %s',
                      row.get('id'), row.get('type'), ex.msg)
            failures.append(f"{row.get('id')!r} ({row.get('type')}): {ex.msg}")
        except (ValueError, KeyError, TypeError) as ex:
            log.exception('restore_snapshot_into_bus: failed to restore node %r (type %r), skipping',
                          row.get('id'), row.get('type'))
            failures.append(f"{row.get('id')!r} ({row.get('type')}): {ex}")
    for node in nodes:
        try:
            node.plugin(bus)
        except DriverError as ex:
            log.error('restore_snapshot_into_bus: failed to plug in node %r, skipping: %s',
                      getattr(node, 'id', '?'), ex.msg)
            failures.append(f"{getattr(node, 'id', '?')!r}: {ex.msg}")
        except (ValueError, KeyError, TypeError) as ex:
            log.exception('restore_snapshot_into_bus: failed to plug in node %r, skipping',
                          getattr(node, 'id', '?'))
            failures.append(f"{getattr(node, 'id', '?')!r}: {ex}")

    _notify_startup_failures(failures)


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
        # 'email' was added in Step 22 (password reset delivery) - migrate
        # existing DBs that were created before this column existed
        user_cols = {row['name'] for row in conn.execute('PRAGMA table_info(users)')}
        if 'email' not in user_cols:
            conn.execute('ALTER TABLE users ADD COLUMN email TEXT')
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
        # 'escalation_channel'/'escalation_after_minutes' were added in
        # Step 28 (alarm escalation) - migrate existing DBs
        pref_cols = {row['name'] for row in conn.execute('PRAGMA table_info(user_notification_prefs)')}
        if 'escalation_channel' not in pref_cols:
            conn.execute("ALTER TABLE user_notification_prefs "
                        "ADD COLUMN escalation_channel TEXT NOT NULL DEFAULT 'none'")
        if 'escalation_after_minutes' not in pref_cols:
            conn.execute('ALTER TABLE user_notification_prefs '
                        'ADD COLUMN escalation_after_minutes INTEGER NOT NULL DEFAULT 0')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dashboards (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                layout  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                used       INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                key          TEXT PRIMARY KEY,
                count        INTEGER NOT NULL DEFAULT 0,
                window_start TEXT NOT NULL,
                locked_until TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username  TEXT NOT NULL,
                action    TEXT NOT NULL,
                target    TEXT NOT NULL DEFAULT '',
                details   TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log (timestamp DESC)
        """)
    return conn


def create_user(db_path: str, username: str, password: str,
                role: str = 'viewer', email: str | None = None) -> int:
    """ create a new user with a securely hashed password.
        Raises ValueError if the username already exists or the role
        is invalid. 'email' is optional and only used to deliver
        self-service password reset links (Step 22).
    """
    if role not in VALID_ROLES:
        raise ValueError(f'Invalid role: {role!r}')

    conn = get_users_connection(db_path)
    try:
        password_hash = generate_password_hash(password)
        try:
            with conn:
                cur = conn.execute(
                    'INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)',
                    (username, password_hash, role, email or None)
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


def update_user_role(db_path: str, user_id: int, role: str) -> None:
    """ change a user's role. Raises ValueError if the role is invalid
        or the user does not exist. Allowed (not blocked) for the
        reserved ANONYMOUS_USERNAME account too - an admin may deliberately
        grant unauthenticated visitors more than viewer access - but it's
        logged, since it's an easy-to-forget, wide-reaching change.
    """
    if role not in VALID_ROLES:
        raise ValueError(f'Invalid role: {role!r}')

    conn = get_users_connection(db_path)
    try:
        row = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
        if row and row['username'] == ANONYMOUS_USERNAME and role != 'viewer':
            log.warning('Reserved account %r role changed to %r - this now applies to '
                        'every unauthenticated visitor', ANONYMOUS_USERNAME, role)
        with conn:
            cur = conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
            if cur.rowcount == 0:
                raise ValueError(f'No such user: {user_id!r}')
    finally:
        conn.close()


def set_user_password(db_path: str, user_id: int, password: str) -> None:
    """ set (reset) a user's password. Raises ValueError if the user
        does not exist.
    """
    password_hash = generate_password_hash(password)
    conn = get_users_connection(db_path)
    try:
        with conn:
            cur = conn.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                               (password_hash, user_id))
            if cur.rowcount == 0:
                raise ValueError(f'No such user: {user_id!r}')
    finally:
        conn.close()


def set_user_email(db_path: str, user_id: int, email: str | None) -> None:
    """ set (or clear, if email is falsy) a user's email address, used
        to deliver self-service password reset links (Step 22).
        Raises ValueError if the user does not exist.
    """
    conn = get_users_connection(db_path)
    try:
        with conn:
            cur = conn.execute('UPDATE users SET email = ? WHERE id = ?',
                               (email or None, user_id))
            if cur.rowcount == 0:
                raise ValueError(f'No such user: {user_id!r}')
    finally:
        conn.close()


def delete_user(db_path: str, user_id: int) -> None:
    """ remove a user. Raises ValueError if the user does not exist, or
        if it is the reserved ANONYMOUS_USERNAME account (would break
        auth.py's before_request auto-login for unauthenticated visitors).
        Callers are responsible for preventing removal of the last
        remaining admin (see count_admins()).
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
        if row and row['username'] == ANONYMOUS_USERNAME:
            raise ValueError(f'Cannot delete the reserved {ANONYMOUS_USERNAME!r} account')
        with conn:
            cur = conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
            if cur.rowcount == 0:
                raise ValueError(f'No such user: {user_id!r}')
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
    password = generate_aquatic_passphrase()
    create_user(db_path, username, password, role='admin')
    return username, password


def ensure_anonymous_user(db_path: str) -> None:
    """ on first start, create the reserved ANONYMOUS_USERNAME account
        (role 'viewer') that auth.py's before_request hook auto-logs-in
        for requests with no session, so the SPA works without login.
        Idempotent - does nothing once the account exists. The generated
        password is never revealed/needed: the account is only ever
        logged into directly via login_user(), never through the normal
        password-checking /login path.
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute('SELECT id FROM users WHERE username = ?',
                           (ANONYMOUS_USERNAME,)).fetchone()
        if row:
            return
    finally:
        conn.close()

    create_user(db_path, ANONYMOUS_USERNAME, generate_url_token(), role='viewer')


def _utcnow() -> datetime:
    """ naive (no tzinfo) current UTC time, matching the now-deprecated
        datetime.utcnow() exactly - stored expires_at/window_start values
        are naive ISO strings, so switching to timezone-aware datetimes
        outright would break comparisons against already-stored rows.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- self-service password reset (Step 22) -------------------------------

def create_password_reset_token(db_path: str, user_id: int,
                                ttl_minutes: int = PASSWORD_RESET_TOKEN_TTL_MINUTES) -> str:
    """ create a fresh, single-use password reset token for a user,
        valid for ttl_minutes. Old, still-valid tokens of the same user
        remain valid too (simplicity over strict single-token-per-user).
    """
    token = generate_url_token()
    expires_at = (_utcnow() + timedelta(minutes=ttl_minutes)).isoformat()
    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO password_reset_tokens (token, user_id, expires_at, used)
                VALUES (?, ?, ?, 0)
            """, (token, user_id, expires_at))
    finally:
        conn.close()
    return token


def get_password_reset_token(db_path: str, token: str) -> dict[str, Any] | None:
    """ return the token row if it exists, is unused and not expired,
        else None
    """
    conn = get_users_connection(db_path)
    try:
        row = conn.execute(
            'SELECT * FROM password_reset_tokens WHERE token = ?', (token,)
        ).fetchone()
        if not row or row['used']:
            return None
        if datetime.fromisoformat(row['expires_at']) < _utcnow():
            return None
        return dict(row)
    finally:
        conn.close()


def consume_password_reset_token(db_path: str, token: str, new_password: str) -> None:
    """ validate the token (raises ValueError if invalid/expired/used),
        set the new password for its user and mark the token as used
        (single-use)
    """
    row = get_password_reset_token(db_path, token)
    if not row:
        raise ValueError('Invalid or expired token')

    password_hash = generate_password_hash(new_password)
    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                        (password_hash, row['user_id']))
            conn.execute('UPDATE password_reset_tokens SET used = 1 WHERE token = ?', (token,))
    finally:
        conn.close()


def send_password_reset_email(db_path: str, to_email: str, reset_url: str) -> bool:
    """ send a password reset link by email, reusing the Email
        credentials already configured for alert notifications
        (aquaPi/db.py: notification_config table, channel 'Email').
        Returns True if the email was handed off to the SMTP server,
        False if no Email channel is configured or sending failed
        (both are logged, never raised - the caller always shows the
        same generic "check your email" message to avoid leaking
        account existence, see auth.py).
    """
    configs = get_notification_config(db_path, 'Email')
    if not configs:
        log.error('Password reset requested but no Email notification channel is configured')
        return False

    cfg = configs[0]
    msg = EmailMessage()
    msg['Subject'] = 'aquaPi Passwort zurücksetzen'
    msg['From'] = cfg['from']
    msg['To'] = to_email
    msg.set_content(
        'Für dein aquaPi-Konto wurde ein Zurücksetzen des Passworts angefordert.\n'
        f'Klicke auf folgenden Link, um ein neues Passwort zu setzen:\n\n{reset_url}\n\n'
        f'Dieser Link ist {PASSWORD_RESET_TOKEN_TTL_MINUTES} Minuten gültig.\n'
        'Falls du das nicht angefordert hast, kannst du diese Email ignorieren.'
    )

    try:
        with smtplib.SMTP(cfg['server']) as smtp:
            smtp.starttls()
            smtp.login(cfg['login'], cfg['pwd'])
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception('Failed to send password reset email to %r', to_email)
        return False


def send_user_password_email(db_path: str, to_email: str, username: str,
                             password: str) -> bool:
    """ email a newly generated/reset account password to a user,
        reusing the same Email channel as send_password_reset_email().
        Returns True/False like send_password_reset_email(), never raises.
    """
    configs = get_notification_config(db_path, 'Email')
    if not configs:
        log.error('Password delivery requested but no Email channel is configured')
        return False

    cfg = configs[0]
    msg = EmailMessage()
    msg['Subject'] = 'aquaPi Zugangsdaten'
    msg['From'] = cfg['from']
    msg['To'] = to_email
    msg.set_content(
        f'Für dich wurde ein aquaPi-Konto angelegt/aktualisiert.\n\n'
        f'Benutzername: {username}\nPasswort: {password}\n\n'
        'Bei Bedarf kannst du es über den Link "Forgot your password?" '
        'auf der Login-Seite ändern.'
    )

    try:
        with smtplib.SMTP(cfg['server']) as smtp:
            smtp.starttls()
            smtp.login(cfg['login'], cfg['pwd'])
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception('Failed to send account password email to %r', to_email)
        return False


# --- login rate limiting / lockout (Step 22) ------------------------------

def is_login_locked_out(db_path: str, key: str) -> tuple[bool, int]:
    """ return (locked, seconds_remaining) for a given lockout key
        (typically the lower-cased username, or the remote IP as
        fallback for unknown usernames). ANONYMOUS_USERNAME is exempt -
        it never goes through the password-checking /login path (see
        auth.py's before_request hook), so it can never legitimately
        fail a login, but is exempted here too as defense in depth.
    """
    if key == ANONYMOUS_USERNAME:
        return False, 0

    conn = get_users_connection(db_path)
    try:
        row = conn.execute(
            'SELECT locked_until FROM login_attempts WHERE key = ?', (key,)
        ).fetchone()
        if row and row['locked_until']:
            locked_until = datetime.fromisoformat(row['locked_until'])
            now = _utcnow()
            if now < locked_until:
                return True, int((locked_until - now).total_seconds()) + 1
        return False, 0
    finally:
        conn.close()


def register_failed_login(db_path: str, key: str,
                          max_attempts: int = LOGIN_MAX_ATTEMPTS,
                          window_minutes: int = LOGIN_ATTEMPT_WINDOW_MINUTES,
                          lockout_minutes: int = LOGIN_LOCKOUT_MINUTES) -> None:
    """ record one failed login attempt for a key, locking it out for
        lockout_minutes once max_attempts is reached within
        window_minutes; the attempt counter/window resets if the
        window has already expired. ANONYMOUS_USERNAME is exempt - see
        is_login_locked_out().
    """
    if key == ANONYMOUS_USERNAME:
        return

    now = _utcnow()
    conn = get_users_connection(db_path)
    try:
        with conn:
            row = conn.execute(
                'SELECT count, window_start FROM login_attempts WHERE key = ?', (key,)
            ).fetchone()

            if row and now - datetime.fromisoformat(row['window_start']) <= timedelta(minutes=window_minutes):
                count = row['count'] + 1
                window_start = datetime.fromisoformat(row['window_start'])
            else:
                count = 1
                window_start = now

            locked_until = (now + timedelta(minutes=lockout_minutes)).isoformat() \
                if count >= max_attempts else None

            conn.execute("""
                INSERT INTO login_attempts (key, count, window_start, locked_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET count = excluded.count,
                    window_start = excluded.window_start, locked_until = excluded.locked_until
            """, (key, count, window_start.isoformat(), locked_until))
    finally:
        conn.close()


def clear_login_attempts(db_path: str, key: str) -> None:
    """ reset a key's failed-attempt counter/lockout, called on a
        successful login
    """
    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute('DELETE FROM login_attempts WHERE key = ?', (key,))
    finally:
        conn.close()


# --- audit log (Step 23) -------------------------------------------------
#
# Records who did what to which configuration/setpoint/user entity and
# when, for admins to review via GET /api/audit-log. 'details' is an
# optional, free-form JSON-serializable dict (e.g. changed field names),
# stored as a JSON string; 'username' is denormalized (kept even if the
# user is later deleted, unlike 'user_id' which is nulled via ON DELETE
# SET NULL) so historic entries stay readable.

def add_audit_log_entry(db_path: str, user_id: int | None, username: str,
                        action: str, target: str = '',
                        details: dict[str, Any] | None = None) -> None:
    """ append one entry to the audit log. Never raises on its own
        (logging an audit entry must not break the operation it is
        auditing) - failures are only logged.
    """
    try:
        conn = get_users_connection(db_path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO audit_log (user_id, username, action, target, details)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, username, action, target,
                      json.dumps(details) if details is not None else None))
        finally:
            conn.close()
    except sqlite3.Error:
        log.exception('Failed to write audit log entry: user=%r action=%r target=%r',
                      username, action, target)


def list_audit_log(db_path: str, *, limit: int = 50, offset: int = 0,
                   action: str | None = None,
                   username: str | None = None) -> dict[str, Any]:
    """ return a page of audit log entries (newest first), optionally
        filtered by exact 'action' and/or 'username', along with the
        total number of matching entries (for pagination).
    """
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    where = []
    params: list[Any] = []
    if action:
        where.append('action = ?')
        params.append(action)
    if username:
        where.append('username = ?')
        params.append(username)
    where_clause = f'WHERE {" AND ".join(where)}' if where else ''

    conn = get_users_connection(db_path)
    try:
        total = conn.execute(
            f'SELECT COUNT(*) AS n FROM audit_log {where_clause}', params
        ).fetchone()['n']

        rows = conn.execute(f"""
            SELECT id, timestamp, user_id, username, action, target, details
            FROM audit_log {where_clause}
            ORDER BY id DESC LIMIT ? OFFSET ?
        """, [*params, limit, offset]).fetchall()

        entries = []
        for row in rows:
            entry = dict(row)
            entry['details'] = json.loads(entry['details']) if entry['details'] else None
            entries.append(entry)

        return {'entries': entries, 'total': total, 'limit': limit, 'offset': offset}
    finally:
        conn.close()


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
                               channel: str, escalation_channel: str = 'none',
                               escalation_after_minutes: int = 0) -> None:
    """ set (create or replace) the preferred notification channel a
        user wants for a given Alert node ('email'/'telegram'/'none').
        Optionally also sets a 2nd, escalation channel that gets
        additionally notified once the alert has stayed active for at
        least 'escalation_after_minutes' (Step 28), 0 disables escalation.
    """
    if channel not in ('email', 'telegram', 'none'):
        raise ValueError(f'Invalid notification channel: {channel!r}')
    if escalation_channel not in ('email', 'telegram', 'none'):
        raise ValueError(f'Invalid escalation channel: {escalation_channel!r}')
    if escalation_after_minutes < 0:
        raise ValueError('escalation_after_minutes must be >= 0')

    conn = get_users_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO user_notification_prefs
                    (user_id, alert_node_id, channel, escalation_channel, escalation_after_minutes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, alert_node_id) DO UPDATE SET
                    channel = excluded.channel,
                    escalation_channel = excluded.escalation_channel,
                    escalation_after_minutes = excluded.escalation_after_minutes
            """, (user_id, alert_node_id, channel, escalation_channel, escalation_after_minutes))
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
    """ return all (alert_node_id, channel, escalation_*) prefs configured
        by one user
    """
    conn = get_users_connection(db_path)
    try:
        rows = conn.execute(
            'SELECT alert_node_id, channel, escalation_channel, escalation_after_minutes '
            'FROM user_notification_prefs '
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
            SELECT u.id AS user_id, u.username AS username, p.channel AS channel,
                   p.escalation_channel AS escalation_channel,
                   p.escalation_after_minutes AS escalation_after_minutes
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


# --- database backup & restore (Step 24) ---------------------------------
#
# Creates a consistent, point-in-time backup of both SQLite databases
# (topology + users) using sqlite3.Connection.backup() - the correct way
# to copy a SQLite database that may be open/in use by the running app,
# unlike a plain file copy which could grab a half-written page. Both
# backups are packaged together into a single, downloadable/rotatable
# .zip archive, so a manual GET /api/backup and the daily scheduled
# backup share the exact same code path.

BACKUP_FILENAME_PREFIX = 'aquapi-backup-'
DEFAULT_BACKUP_KEEP = 7


def backup_sqlite_file(src_path: str, dest_path: str) -> None:
    """ create a consistent copy of the SQLite database at 'src_path'
        into a new file at 'dest_path', using sqlite3's own online
        backup API (safe to call while 'src_path' is open/in use by
        the running app, unlike a plain file copy).
    """
    makedirs(path.dirname(dest_path) or '.', exist_ok=True)
    src_conn = sqlite3.connect(src_path)
    try:
        dest_conn = sqlite3.connect(dest_path)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def create_backup_archive(topo_db_path: str, users_db_path: str,
                          dest_dir: str, filename: str | None = None) -> str:
    """ create one .zip archive in 'dest_dir', containing a consistent
        backup of both the topology and the users SQLite databases
        (whichever of the two actually exist), named after their
        original basenames. Returns the full path of the created
        archive.
    """
    makedirs(dest_dir, exist_ok=True)
    if not filename:
        filename = f'{BACKUP_FILENAME_PREFIX}{datetime.now():%Y%m%d-%H%M%S}.zip'
    archive_path = path.join(dest_dir, filename)

    with tempfile.TemporaryDirectory() as tmp_dir:
        entries = []
        for src_db_path in (topo_db_path, users_db_path):
            if src_db_path and path.exists(src_db_path):
                tmp_copy = path.join(tmp_dir, path.basename(src_db_path))
                backup_sqlite_file(src_db_path, tmp_copy)
                entries.append(tmp_copy)

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for entry in entries:
                zf.write(entry, arcname=path.basename(entry))

    return archive_path


def rotate_backups(backup_dir: str, keep: int = DEFAULT_BACKUP_KEEP) -> None:
    """ delete the oldest backup archives (matched by
        BACKUP_FILENAME_PREFIX) in 'backup_dir' until at most 'keep'
        generations remain
    """
    if not path.isdir(backup_dir):
        return
    backups = sorted(
        (path.join(backup_dir, f) for f in listdir(backup_dir)
         if f.startswith(BACKUP_FILENAME_PREFIX) and f.endswith('.zip')),
        key=path.getmtime,
    )
    for old in backups[:max(0, len(backups) - keep)]:
        try:
            remove(old)
        except OSError:
            log.exception('Failed to remove old backup %r', old)


def create_scheduled_backup(topo_db_path: str, users_db_path: str,
                            backup_dir: str, keep: int = DEFAULT_BACKUP_KEEP) -> str:
    """ create a new dated backup archive in 'backup_dir' and rotate
        away old generations beyond 'keep'. Returns the path of the
        newly created archive. Used both by the daily scheduler
        (MachineRoom) and can be called manually/from tests.
    """
    archive_path = create_backup_archive(topo_db_path, users_db_path, backup_dir)
    rotate_backups(backup_dir, keep=keep)
    return archive_path
