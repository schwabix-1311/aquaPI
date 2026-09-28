#!/usr/bin/env python3
""" Tests for aquaPi/db.py's backup-archive listing/restore and wiring-db
    path resolution - the new backend pieces behind the `./manage` CLI
    (aquaPi/cli.py): list_backups(), restore_backup_archive(),
    resolve_wiring_db_path().
"""

import json
import os
import sqlite3
import time

import pytest

from aquaPi import db
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def wiring_db_path(tmp_path):
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)
    path_ = str(tmp_path / 'wiring.sqlite')
    db.save_wiring(bus, path_)
    bus.teardown()
    return path_


@pytest.fixture
def users_db_path(tmp_path):
    path_ = str(tmp_path / 'users.sqlite')
    db.get_users_connection(path_).close()  # create the schema on disk
    return path_


def _assert_valid_sqlite(path_: str) -> None:
    conn = sqlite3.connect(path_)
    try:
        conn.execute('SELECT 1').fetchone()
    finally:
        conn.close()


# --- list_backups() -------------------------------------------------------

def test_list_backups_empty_dir_returns_empty_list(tmp_path):
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    assert db.list_backups(str(backup_dir)) == []


def test_list_backups_missing_dir_returns_empty_list(tmp_path):
    # a fresh install with no backups taken yet - normal, not an error
    assert db.list_backups(str(tmp_path / 'nonexistent')) == []


def test_list_backups_ignores_unrelated_files(tmp_path):
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    (backup_dir / 'aquapi-backup-1.zip').write_text('x')
    (backup_dir / 'not-a-backup.txt').write_text('x')

    result = db.list_backups(str(backup_dir))
    assert [b['filename'] for b in result] == ['aquapi-backup-1.zip']


def test_list_backups_sorted_newest_first_with_correct_fields(tmp_path):
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()

    older = backup_dir / 'aquapi-backup-older.zip'
    older.write_text('xx')
    newer = backup_dir / 'aquapi-backup-newer.zip'
    newer.write_text('x')
    now = time.time()
    os.utime(older, (now, now))
    os.utime(newer, (now + 5, now + 5))

    result = db.list_backups(str(backup_dir))
    assert [b['filename'] for b in result] == ['aquapi-backup-newer.zip', 'aquapi-backup-older.zip']
    assert result[0]['path'] == str(newer)
    assert result[0]['size'] == 1
    assert result[1]['size'] == 2
    assert result[0]['created_at'] > result[1]['created_at']


# --- restore_backup_archive() ---------------------------------------------

def test_restore_backup_archive_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        db.restore_backup_archive(str(tmp_path / 'nope.zip'), str(tmp_path))


def test_restore_backup_archive_restores_both_by_default(wiring_db_path, users_db_path, tmp_path):
    archive = db.create_backup_archive(wiring_db_path, users_db_path, str(tmp_path / 'backups'))

    dest_dir = tmp_path / 'restored'
    dest_dir.mkdir()
    restored = db.restore_backup_archive(archive, str(dest_dir))

    assert sorted(os.path.basename(p) for p in restored) == \
        sorted([os.path.basename(wiring_db_path), os.path.basename(users_db_path)])
    for p in restored:
        _assert_valid_sqlite(p)


def test_restore_backup_archive_only_users_leaves_wiring_untouched(wiring_db_path, users_db_path, tmp_path):
    archive = db.create_backup_archive(wiring_db_path, users_db_path, str(tmp_path / 'backups'))

    dest_dir = tmp_path / 'restored'
    dest_dir.mkdir()
    wiring_name = os.path.basename(wiring_db_path)
    users_name = os.path.basename(users_db_path)
    sentinel = dest_dir / wiring_name
    sentinel.write_text('untouched')

    restored = db.restore_backup_archive(archive, str(dest_dir), only='users')

    assert [os.path.basename(p) for p in restored] == [users_name]
    assert sentinel.read_text() == 'untouched'  # wiring file was NOT restored
    _assert_valid_sqlite(str(dest_dir / users_name))


def test_restore_backup_archive_only_wiring_leaves_users_untouched(wiring_db_path, users_db_path, tmp_path):
    archive = db.create_backup_archive(wiring_db_path, users_db_path, str(tmp_path / 'backups'))

    dest_dir = tmp_path / 'restored'
    dest_dir.mkdir()
    users_name = os.path.basename(users_db_path)
    wiring_name = os.path.basename(wiring_db_path)
    sentinel = dest_dir / users_name
    sentinel.write_text('untouched')

    restored = db.restore_backup_archive(archive, str(dest_dir), only='wiring')

    assert [os.path.basename(p) for p in restored] == [wiring_name]
    assert sentinel.read_text() == 'untouched'


def test_restore_backup_archive_only_matching_nothing_raises(wiring_db_path, tmp_path):
    # an archive with only a wiring db - 'only=users' matches nothing in it
    archive = db.create_backup_archive(wiring_db_path, str(tmp_path / 'no-such-users.sqlite'),
                                       str(tmp_path / 'backups'))
    with pytest.raises(ValueError):
        db.restore_backup_archive(archive, str(tmp_path / 'restored'), only='users')


def test_restore_backup_archive_overwrites_existing_file(wiring_db_path, users_db_path, tmp_path):
    archive = db.create_backup_archive(wiring_db_path, users_db_path, str(tmp_path / 'backups'))

    dest_dir = tmp_path / 'restored'
    dest_dir.mkdir()
    wiring_name = os.path.basename(wiring_db_path)
    (dest_dir / wiring_name).write_text('stale content, must be overwritten')

    db.restore_backup_archive(archive, str(dest_dir), only='wiring')
    _assert_valid_sqlite(str(dest_dir / wiring_name))


def test_restore_backup_archive_roundtrips_real_content(wiring_db_path, users_db_path, tmp_path):
    archive = db.create_backup_archive(wiring_db_path, users_db_path, str(tmp_path / 'backups'))

    dest_dir = tmp_path / 'restored'
    dest_dir.mkdir()
    db.restore_backup_archive(archive, str(dest_dir))

    restored_wiring = dest_dir / os.path.basename(wiring_db_path)
    conn = sqlite3.connect(str(restored_wiring))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT id FROM nodes').fetchall()
    finally:
        conn.close()
    assert {row['id'] for row in rows} == {'wasser'}


# --- resolve_wiring_db_path() ----------------------------------------------

def test_resolve_wiring_db_path_defaults_to_wiring(tmp_path):
    assert db.resolve_wiring_db_path(str(tmp_path)) == str(tmp_path / 'wiring.sqlite')


def test_resolve_wiring_db_path_uses_caller_supplied_default(tmp_path):
    # e.g. MachineRoom.__init__ passing its own already-merged
    # self.globals.get('DEFAULT_CONFIG', 'wiring') - a value that never
    # touched a config.json file at all
    assert db.resolve_wiring_db_path(str(tmp_path), default_config='pytest') == \
        str(tmp_path / 'pytest.sqlite')


def test_resolve_wiring_db_path_config_json_overrides_default(tmp_path):
    (tmp_path / 'config.json').write_text(json.dumps({'DEFAULT_CONFIG': 'dev'}))
    assert db.resolve_wiring_db_path(str(tmp_path), default_config='pytest') == \
        str(tmp_path / 'dev.sqlite')


def test_resolve_wiring_db_path_env_var_overrides_everything(tmp_path, monkeypatch):
    (tmp_path / 'config.json').write_text(json.dumps({'DEFAULT_CONFIG': 'dev'}))
    monkeypatch.setenv('AQUAPI_WIRING', 'override.pickle')
    # extension is stripped regardless of what's supplied
    assert db.resolve_wiring_db_path(str(tmp_path)) == str(tmp_path / 'override.sqlite')


def test_resolve_wiring_db_path_respects_aquapi_cfg_override(tmp_path, monkeypatch):
    (tmp_path / 'custom.json').write_text(json.dumps({'DEFAULT_CONFIG': 'renamed'}))
    monkeypatch.setenv('AQUAPI_CFG', 'custom.json')
    assert db.resolve_wiring_db_path(str(tmp_path)) == str(tmp_path / 'renamed.sqlite')
