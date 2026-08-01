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
    """ create the nodes table if it does not exist yet
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


def _serialize_node(node: BusNode) -> dict[str, Any]:
    """ build the JSON-able state dict for a single node,
        node-type specific quirks (currently only Alert.conditions)
        are normalized here
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
                state = _serialize_node(node)
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
        except (ValueError, KeyError, TypeError):
            log.exception('load_topology: failed to restore node %r (type %r), skipping',
                          row['id'], row['type'])

    for node in nodes:
        node.plugin(bus)

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
