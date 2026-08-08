#!/usr/bin/env python3
""" Tests for Step 24: database backup/export (aquaPi/db.py's
    backup_sqlite_file()/create_backup_archive()/rotate_backups()/
    create_scheduled_backup(), plus the admin-only GET /api/backup
    download endpoint).
"""

import os
import sqlite3
import time
import zipfile
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, db, api
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput
from aquaPi.machineroom.out_nodes import SwitchDevice
from aquaPi.machineroom.ctrl_nodes import MinimumCtrl


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)

    ctrl = MinimumCtrl('Heizen', sensor.id, setpoint=24.0, hysteresis=0.5)
    ctrl.plugin(bus)

    out = SwitchDevice('Heizstab', ctrl.id, '')
    out.plugin(bus)

    yield bus
    bus.teardown()


class _FakeMachineRoom:
    def __init__(self, bus: MsgBus, topo_db_path: str, users_db_path: str):
        self.bus = bus
        self.globals = {'BUS_TOPO': topo_db_path, 'USERS_DB': users_db_path}
        self.saved = 0

    def save_nodes(self, container):
        self.saved += 1
        db.save_topology(container, self.globals['BUS_TOPO'])


@pytest.fixture
def topo_db_path(tmp_path, bus):
    topo_path = str(tmp_path / 'topo.sqlite')
    db.save_topology(bus, topo_path)
    return topo_path


@pytest.fixture
def app(tmp_path, bus, topo_db_path):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)

    users_db_path = db.get_users_db_path(app.config['INSTANCE_PATH'])
    # make sure the users DB file actually exists on disk before any
    # backup attempt (get_users_connection() creates the schema)
    db.get_users_connection(users_db_path).close()

    app.extensions['machineroom'] = _FakeMachineRoom(bus, topo_db_path, users_db_path)

    @app.route('/', endpoint='spa.spa')
    def spa_stub():
        return 'spa'

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users_db_path(app):
    return db.get_users_db_path(app.config['INSTANCE_PATH'])


@pytest.fixture
def users(users_db_path):
    db.create_user(users_db_path, 'operator1', 'operatorPass1', role='operator')
    db.create_user(users_db_path, 'admin1', 'adminPass123', role='admin')


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


def _assert_valid_sqlite(path_: str) -> None:
    """ a loadable SQLite file must open and allow a trivial query """
    conn = sqlite3.connect(path_)
    try:
        conn.execute('SELECT 1').fetchone()
    finally:
        conn.close()


# --- db.py unit tests ----------------------------------------------------

def test_backup_sqlite_file_creates_loadable_copy(topo_db_path, tmp_path):
    dest = str(tmp_path / 'copy.sqlite')
    db.backup_sqlite_file(topo_db_path, dest)

    assert os.path.exists(dest)
    _assert_valid_sqlite(dest)
    # the copy must contain the same nodes as the source
    conn = sqlite3.connect(dest)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT id FROM nodes').fetchall()
    finally:
        conn.close()
    assert {row['id'] for row in rows} == {'wasser', 'heizen', 'heizstab'}


def test_create_backup_archive_contains_both_databases(topo_db_path, users_db_path, tmp_path):
    dest_dir = str(tmp_path / 'backups')
    archive_path = db.create_backup_archive(topo_db_path, users_db_path, dest_dir)

    assert os.path.exists(archive_path)
    assert archive_path.startswith(dest_dir)

    with zipfile.ZipFile(archive_path) as zf:
        names = set(zf.namelist())
        assert os.path.basename(topo_db_path) in names
        assert os.path.basename(users_db_path) in names

        with zf.open(os.path.basename(topo_db_path)) as f_in:
            extracted = tmp_path / 'extracted.sqlite'
            extracted.write_bytes(f_in.read())
    _assert_valid_sqlite(str(extracted))


def test_create_backup_archive_skips_missing_db(topo_db_path, tmp_path):
    dest_dir = str(tmp_path / 'backups')
    archive_path = db.create_backup_archive(
        topo_db_path, str(tmp_path / 'does-not-exist.sqlite'), dest_dir)

    with zipfile.ZipFile(archive_path) as zf:
        assert zf.namelist() == [os.path.basename(topo_db_path)]


def test_rotate_backups_keeps_only_newest_n(tmp_path):
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()

    paths = []
    for i in range(5):
        p = backup_dir / f'aquapi-backup-{i}.zip'
        p.write_text('x')
        # ensure distinct, increasing mtimes so ordering is deterministic
        os.utime(p, (time.time() + i, time.time() + i))
        paths.append(p)

    db.rotate_backups(str(backup_dir), keep=2)

    remaining = sorted(os.listdir(backup_dir))
    assert len(remaining) == 2
    # the 2 newest (highest index) files must survive
    assert remaining == sorted(p.name for p in paths[-2:])


def test_rotate_backups_ignores_unrelated_files(tmp_path):
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    (backup_dir / 'aquapi-backup-1.zip').write_text('x')
    (backup_dir / 'not-a-backup.txt').write_text('x')

    db.rotate_backups(str(backup_dir), keep=0)

    remaining = os.listdir(backup_dir)
    assert remaining == ['not-a-backup.txt']


def test_rotate_backups_missing_dir_is_noop(tmp_path):
    # must not raise even if the directory was never created
    db.rotate_backups(str(tmp_path / 'nonexistent'), keep=3)


def test_create_scheduled_backup_creates_and_rotates(topo_db_path, users_db_path, tmp_path):
    backup_dir = str(tmp_path / 'backups')

    first = db.create_scheduled_backup(topo_db_path, users_db_path, backup_dir, keep=2)
    time.sleep(1.05)  # filenames are second-granular, force a distinct name
    second = db.create_scheduled_backup(topo_db_path, users_db_path, backup_dir, keep=2)
    time.sleep(1.05)
    third = db.create_scheduled_backup(topo_db_path, users_db_path, backup_dir, keep=2)

    assert first != second != third
    remaining = os.listdir(backup_dir)
    assert len(remaining) == 2
    assert os.path.basename(third) in remaining
    assert os.path.basename(second) in remaining
    assert os.path.basename(first) not in remaining


# --- GET /api/backup endpoint --------------------------------------------

def test_backup_endpoint_requires_admin(client, users):
    _login(client, 'operator1', 'operatorPass1')
    resp = client.get('/api/backup')
    assert resp.status_code == HTTPStatus.FORBIDDEN


def test_backup_endpoint_requires_login(client):
    resp = client.get('/api/backup')
    assert resp.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FOUND)


def test_backup_endpoint_returns_loadable_archive(client, users, users_db_path, tmp_path):
    _login(client, 'admin1', 'adminPass123')

    resp = client.get('/api/backup')
    assert resp.status_code == HTTPStatus.OK
    assert resp.mimetype in ('application/zip', 'application/x-zip-compressed')
    assert 'attachment' in resp.headers.get('Content-Disposition', '')

    # extract into a dedicated subdir - NOT tmp_path itself, which is
    # also the app's INSTANCE_PATH, so extracting there would overwrite
    # (and falsify) the live databases with this backup snapshot
    extract_dir = tmp_path / 'extracted'
    extract_dir.mkdir()

    downloaded = extract_dir / 'downloaded.zip'
    downloaded.write_bytes(resp.data)

    with zipfile.ZipFile(downloaded) as zf:
        names = zf.namelist()
        assert any(name.endswith('.sqlite') for name in names)
        # every archived member must itself be a loadable SQLite file
        for name in names:
            extracted = extract_dir / name
            extracted.write_bytes(zf.read(name))
            _assert_valid_sqlite(str(extracted))

    # the download must also have created an audit log entry
    result = db.list_audit_log(users_db_path)
    assert any(e['action'] == 'download_backup' for e in result['entries'])
