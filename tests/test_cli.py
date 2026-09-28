#!/usr/bin/env python3
""" Tests for aquaPi/cli.py (the './manage' CLI): backup / list-backups /
    restore / reconfig / service-unit, via click.testing.CliRunner.
"""

import getpass
import os
import subprocess
import sqlite3

import pytest
from click.testing import CliRunner

import aquaPi.cli as cli_module
from aquaPi import db
from aquaPi.cli import cli
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus
from aquaPi.machineroom.in_nodes import AnalogInput


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def instance_dir(tmp_path):
    """ a minimal, realistic instance/ dir: a wiring.sqlite with one real
        node, a bare users.sqlite - enough for backup/restore to exercise
        real content, without booting a whole MachineRoom/Flask app.
    """
    bus = MsgBus(threaded=False)
    sensor = AnalogInput('Wasser', '', 25.0, '°C')
    sensor.plugin(bus)
    db.save_wiring(bus, str(tmp_path / 'wiring.sqlite'))
    bus.teardown()

    db.get_users_connection(str(tmp_path / 'users.sqlite')).close()
    return tmp_path


def _invoke(runner, instance_dir, args, **kwargs):
    return runner.invoke(cli, ['--instance-path', str(instance_dir)] + args, **kwargs)


def _write_marker_sqlite(path_, marker):
    """ overwrite path_ with a valid (but distinguishable) SQLite file -
        restore's automatic pre-restore safety backup legitimately backs
        up whatever's currently there via sqlite3's own online backup
        API, which requires a real database, not arbitrary bytes.
    """
    conn = sqlite3.connect(str(path_))
    try:
        conn.execute('CREATE TABLE marker (value TEXT)')
        conn.execute('INSERT INTO marker VALUES (?)', (marker,))
        conn.commit()
    finally:
        conn.close()


def _read_marker_sqlite(path_):
    conn = sqlite3.connect(str(path_))
    try:
        return conn.execute('SELECT value FROM marker').fetchone()[0]
    finally:
        conn.close()


# --- backup / list-backups --------------------------------------------------

def test_list_backups_empty_is_friendly_not_an_error(runner, instance_dir):
    result = _invoke(runner, instance_dir, ['list-backups'])
    assert result.exit_code == 0
    assert 'No backups found' in result.output
    assert './manage backup' in result.output


def test_backup_then_list_backups_shows_it(runner, instance_dir):
    result = _invoke(runner, instance_dir, ['backup'])
    assert result.exit_code == 0
    assert 'Backup created:' in result.output

    result = _invoke(runner, instance_dir, ['list-backups'])
    assert result.exit_code == 0
    backups = db.list_backups(str(instance_dir / 'backups'))
    assert len(backups) == 1
    assert backups[0]['filename'] in result.output


def test_backup_respects_aquapi_backup_dir_env_override(runner, instance_dir, monkeypatch, tmp_path):
    custom_dir = tmp_path / 'elsewhere'
    monkeypatch.setenv('AQUAPI_BACKUP_DIR', str(custom_dir))
    result = _invoke(runner, instance_dir, ['backup'])
    assert result.exit_code == 0
    assert db.list_backups(str(custom_dir)) != []
    assert db.list_backups(str(instance_dir / 'backups')) == []


def test_backup_respects_aquapi_backup_keep_env_override(runner, instance_dir, monkeypatch):
    monkeypatch.setenv('AQUAPI_BACKUP_KEEP', '1')
    _invoke(runner, instance_dir, ['backup'])
    _invoke(runner, instance_dir, ['backup'])
    assert len(db.list_backups(str(instance_dir / 'backups'))) == 1


# --- restore -----------------------------------------------------------------

def test_restore_missing_archive_errors_cleanly(runner, instance_dir):
    result = _invoke(runner, instance_dir, ['restore', 'no-such-backup.zip'])
    assert result.exit_code != 0
    assert 'not found' in result.output


def test_restore_full_with_bare_filename_resolves_against_backup_dir(runner, instance_dir):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    os.remove(instance_dir / 'wiring.sqlite')
    result = _invoke(runner, instance_dir, ['restore', archive_name, '--yes'])
    assert result.exit_code == 0
    assert (instance_dir / 'wiring.sqlite').exists()
    assert 'Restart aquaPi' in result.output


def test_restore_takes_an_automatic_safety_backup_first(runner, instance_dir):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    _invoke(runner, instance_dir, ['restore', archive_name, '--yes'])
    backups = db.list_backups(str(instance_dir / 'backups'))
    assert any('pre-restore' in b['filename'] for b in backups)


def test_restore_only_wiring_leaves_users_untouched(runner, instance_dir):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    _write_marker_sqlite(instance_dir / 'users.sqlite', 'sentinel-untouched')
    result = _invoke(runner, instance_dir, ['restore', archive_name, '--only', 'wiring', '--yes'])
    assert result.exit_code == 0
    assert _read_marker_sqlite(instance_dir / 'users.sqlite') == 'sentinel-untouched'


def test_restore_only_kind_absent_from_archive_errors(runner, instance_dir, tmp_path):
    # an archive with only a wiring db present
    archive = db.create_backup_archive(
        str(instance_dir / 'wiring.sqlite'), str(tmp_path / 'no-users-here.sqlite'),
        str(instance_dir / 'backups'))
    result = _invoke(runner, instance_dir, ['restore', os.path.basename(archive), '--only', 'users', '--yes'])
    assert result.exit_code != 0
    assert 'no' in result.output.lower()


def test_restore_declining_confirmation_aborts_without_restoring(runner, instance_dir):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    _write_marker_sqlite(instance_dir / 'wiring.sqlite', 'not-yet-overwritten')
    result = _invoke(runner, instance_dir, ['restore', archive_name], input='n\n')
    assert result.exit_code == 0
    assert 'Aborted' in result.output
    assert _read_marker_sqlite(instance_dir / 'wiring.sqlite') == 'not-yet-overwritten'


def _fake_run_recorder(calls, fail_on=None):
    """ a stand-in for subprocess.run() that records every command it was
        called with instead of executing it, optionally raising
        CalledProcessError for a command matching 'fail_on' (a substring
        of the joined argv) - lets tests exercise the stop/restart flow
        without a real systemd/sudo.
    """
    def _run(cmd, *args, **kwargs):
        calls.append(cmd)
        if fail_on and fail_on in ' '.join(cmd):
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0)
    return _run


def test_restore_stops_and_restarts_an_active_systemd_service(runner, instance_dir, monkeypatch):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: True)
    calls = []
    monkeypatch.setattr(cli_module.subprocess, 'run', _fake_run_recorder(calls))

    result = _invoke(runner, instance_dir, ['restore', archive_name, '--yes'])
    assert result.exit_code == 0
    assert 'will be stopped before restoring and started again' in result.output
    assert f'{cli_module._SERVICE_NAME}.service restarted with the restored data' in result.output

    joined = [' '.join(c) for c in calls]
    assert any(f'systemctl stop {cli_module._SERVICE_NAME}' in c for c in joined)
    assert any(f'systemctl start {cli_module._SERVICE_NAME}' in c for c in joined)
    stop_idx = next(i for i, c in enumerate(joined) if 'stop' in c)
    start_idx = next(i for i, c in enumerate(joined) if 'start' in c)
    assert stop_idx < start_idx


def test_restore_restarts_service_even_if_the_restore_itself_fails(runner, instance_dir, monkeypatch):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: True)
    calls = []
    monkeypatch.setattr(cli_module.subprocess, 'run', _fake_run_recorder(calls))
    monkeypatch.setattr(cli_module.db, 'restore_backup_archive',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))

    result = _invoke(runner, instance_dir, ['restore', archive_name, '--yes'])
    assert result.exit_code != 0  # the underlying failure still surfaces
    joined = [' '.join(c) for c in calls]
    assert any(f'systemctl stop {cli_module._SERVICE_NAME}' in c for c in joined)
    assert any(f'systemctl start {cli_module._SERVICE_NAME}' in c for c in joined)


def test_restore_aborts_without_touching_databases_if_stopping_the_service_fails(
        runner, instance_dir, monkeypatch):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']

    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: True)
    calls = []
    monkeypatch.setattr(cli_module.subprocess, 'run', _fake_run_recorder(calls, fail_on='stop'))
    restore_called = []
    monkeypatch.setattr(cli_module.db, 'restore_backup_archive',
                        lambda *a, **kw: restore_called.append(1))

    result = _invoke(runner, instance_dir, ['restore', archive_name, '--yes'])
    assert result.exit_code != 0
    assert not restore_called  # never got anywhere near touching a database


def test_restore_no_automatic_stop_message_when_service_inactive(runner, instance_dir, monkeypatch):
    _invoke(runner, instance_dir, ['backup'])
    archive_name = db.list_backups(str(instance_dir / 'backups'))[0]['filename']
    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: False)

    result = _invoke(runner, instance_dir, ['restore', archive_name, '--yes'])
    assert result.exit_code == 0
    assert 'stop it yourself first' in result.output
    assert 'Restart aquaPi for the restored data' in result.output


# --- reconfig -----------------------------------------------------------------

def test_reconfig_configures_email_and_skips_telegram(runner, instance_dir):
    stdin = 'y\nsmtp.example.com\nme@example.com\nsecret\nme@example.com\nyou@example.com\nn\n'
    result = _invoke(runner, instance_dir, ['reconfig'], input=stdin)
    assert result.exit_code == 0

    users_db = str(instance_dir / 'users.sqlite')
    email_cfg = db.get_notification_config(users_db, 'Email')
    assert email_cfg == [{
        'server': 'smtp.example.com', 'login': 'me@example.com', 'pwd': 'secret',
        'from': 'me@example.com', 'to': 'you@example.com',
    }]
    assert db.get_notification_config(users_db, 'Telegram') is None


def test_reconfig_blank_telegram_chat_id_is_omitted_not_stored_empty(runner, instance_dir):
    stdin = 'n\ny\n12345:token\nMy Chat\n\n'
    result = _invoke(runner, instance_dir, ['reconfig'], input=stdin)
    assert result.exit_code == 0

    telegram_cfg = db.get_notification_config(str(instance_dir / 'users.sqlite'), 'Telegram')
    assert telegram_cfg == [{'bot_token': '12345:token', 'chat_name': 'My Chat'}]
    assert 'chat_id' not in telegram_cfg[0]


def test_reconfig_declining_a_channel_leaves_existing_config_untouched(runner, instance_dir):
    users_db = str(instance_dir / 'users.sqlite')
    db.set_notification_config(users_db, 'Email', [{'server': 'old', 'login': 'x',
                                                     'pwd': 'y', 'from': 'a', 'to': 'b'}])
    result = _invoke(runner, instance_dir, ['reconfig'], input='n\nn\n')
    assert result.exit_code == 0
    assert db.get_notification_config(users_db, 'Email')[0]['server'] == 'old'


def test_reconfig_declining_everything_reports_no_changes_and_skips_restart(runner, instance_dir):
    result = _invoke(runner, instance_dir, ['reconfig'], input='n\nn\n')
    assert result.exit_code == 0
    assert 'Keine Änderungen vorgenommen.' in result.output
    assert 'neu gestartet' not in result.output


def test_reconfig_restarts_an_active_systemd_service_after_a_real_change(runner, instance_dir, monkeypatch):
    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: True)
    calls = []
    monkeypatch.setattr(cli_module.subprocess, 'run', _fake_run_recorder(calls))

    stdin = 'y\nsmtp.example.com\nme@example.com\nsecret\nme@example.com\nyou@example.com\nn\n'
    result = _invoke(runner, instance_dir, ['reconfig'], input=stdin)
    assert result.exit_code == 0
    assert f'{cli_module._SERVICE_NAME}.service neu gestartet.' in result.output
    assert any(f'systemctl restart {cli_module._SERVICE_NAME}' in ' '.join(c) for c in calls)


def test_reconfig_no_restart_attempted_when_nothing_changed_even_if_service_active(
        runner, instance_dir, monkeypatch):
    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: True)
    calls = []
    monkeypatch.setattr(cli_module.subprocess, 'run', _fake_run_recorder(calls))

    result = _invoke(runner, instance_dir, ['reconfig'], input='n\nn\n')
    assert result.exit_code == 0
    assert 'Keine Änderungen vorgenommen.' in result.output
    assert calls == []  # no systemctl call at all - nothing to take effect


def test_reconfig_warns_but_does_not_fail_if_restart_itself_fails(runner, instance_dir, monkeypatch):
    monkeypatch.setattr(cli_module, '_systemd_service_active', lambda: True)
    monkeypatch.setattr(cli_module.subprocess, 'run', _fake_run_recorder([], fail_on='restart'))

    stdin = 'n\ny\n12345:token\nMy Chat\n\n'
    result = _invoke(runner, instance_dir, ['reconfig'], input=stdin)
    assert result.exit_code == 0  # the config was still saved successfully
    assert 'konnte nicht automatisch neu gestartet werden' in result.output
    # the actual save must not have been rolled back just because the
    # follow-up restart failed
    telegram_cfg = db.get_notification_config(str(instance_dir / 'users.sqlite'), 'Telegram')
    assert telegram_cfg[0]['chat_name'] == 'My Chat'


# --- service-unit --------------------------------------------------------------

def test_service_unit_renders_expected_content(runner, instance_dir):
    result = runner.invoke(cli, ['service-unit'])
    assert result.exit_code == 0
    assert 'Type=simple' in result.output
    assert 'gunicorn' not in result.output.lower()
    assert f'User={getpass.getuser()}' in result.output
    assert 'ExecStart=' in result.output and '/venv/bin/flask run --host 0.0.0.0 --port 5000' in result.output
    assert '[Install]' in result.output and 'WantedBy=multi-user.target' in result.output


def test_service_unit_custom_host_and_port(runner):
    result = runner.invoke(cli, ['service-unit', '--host', '127.0.0.1', '--port', '8080'])
    assert result.exit_code == 0
    assert '--host 127.0.0.1 --port 8080' in result.output


def test_service_unit_install_and_uninstall_together_is_rejected(runner):
    result = runner.invoke(cli, ['service-unit', '--install', '--uninstall'])
    assert result.exit_code != 0
    assert 'mutually exclusive' in result.output
