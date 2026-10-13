#!/usr/bin/env python3
""" aquaPi deployment/maintenance CLI: init-admin / reconfig / backup /
    list-backups / restore / service-unit. Invoked via the './manage' wrapper at the repo
    root.

    Deliberately imports only aquaPi.db (+ stdlib + click, + Flask only to
    read .instance_path) - never aquaPi.create_app()/MachineRoom - so this
    works even when config.json/wiring.sqlite is broken or missing, which
    is exactly when 'restore' is needed.
"""

import getpass
import glob
import re
import subprocess
import zipfile
from datetime import datetime
from os import environ, makedirs, path
from pathlib import Path

import click
from flask import Flask

from . import db


_SERVICE_NAME = 'aquapi'


def _systemd_service_active() -> bool:
    """ True if the aquapi systemd service is currently active - False if
        it was never installed, is inactive/failed, or systemd/systemctl
        isn't available at all (e.g. a dev machine, or a container without
        systemd as PID 1). Used by 'restore' to automatically stop/restart
        the service around the overwrite when it's the thing actually
        running aquaPi - there's no equivalent way to detect or signal a
        plain './run'/'./dbg' process kept alive in a shell (no PID file),
        so that case still just gets a manual warning.
    """
    try:
        result = subprocess.run(['systemctl', 'is-active', _SERVICE_NAME],
                                capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False
    return result.stdout.strip() == 'active'


def _default_instance_path() -> str:
    # mirrors aquaPi/__init__.py's own Flask(__name__, instance_relative_config=True)
    # (there, __name__ == 'aquaPi') - same import name, same computed path, no
    # need to duplicate Flask's own resolution algorithm. Deliberately the
    # literal string 'aquaPi', not this module's own __name__ ('aquaPi.cli').
    return Flask('aquaPi', instance_relative_config=True).instance_path


@click.group()
@click.option('--instance-path', default=None, type=click.Path(),
             help="Override instance/ dir (default: same as the running app).")
@click.pass_context
def cli(ctx, instance_path):
    """ aquaPi deployment & maintenance tool. """
    instance_path = instance_path or _default_instance_path()
    # a fresh release install has no instance/ yet (it isn't shipped, the
    # app creates its files on first start) - install.sh runs init-admin
    # and reconfig before that, and SQLite can't create the directory
    makedirs(instance_path, exist_ok=True)
    backup_dir = environ.get('AQUAPI_BACKUP_DIR', path.join(instance_path, 'backups'))
    backup_keep = int(environ.get('AQUAPI_BACKUP_KEEP', db.DEFAULT_BACKUP_KEEP))
    ctx.obj = {
        'instance_path': instance_path,
        'backup_dir': backup_dir,
        'backup_keep': backup_keep,
        'users_db': db.get_users_db_path(instance_path),
    }


@cli.command()
@click.pass_context
def backup(ctx):
    """ create an on-demand backup archive. """
    wiring_db = db.resolve_wiring_db_path(ctx.obj['instance_path'])
    archive = db.create_scheduled_backup(
        wiring_db, ctx.obj['users_db'], ctx.obj['backup_dir'],
        keep=ctx.obj['backup_keep'])
    click.echo(f'Backup created: {archive}')


@cli.command('list-backups')
@click.pass_context
def list_backups_cmd(ctx):
    """ list existing backup archives. """
    backups = db.list_backups(ctx.obj['backup_dir'])
    if not backups:
        click.echo(f"No backups found in {ctx.obj['backup_dir']} yet. "
                  "Run './manage backup' to create one.")
        return
    for i, b in enumerate(backups, 1):
        click.echo(f"{i:3d}  {b['filename']:<45} "
                  f"{b['created_at']:%Y-%m-%d %H:%M:%S}  {b['size'] / 1024:.0f} KB")


@cli.command()
@click.argument('archive')
@click.option('--only', type=click.Choice(['wiring', 'users']), default=None,
             help='Restore only this database, leave the other untouched.')
@click.option('--yes', '-y', is_flag=True,
             help='Skip the confirmation prompt (for scripted use).')
@click.pass_context
def restore(ctx, archive, only, yes):
    """ restore from a backup ARCHIVE (a bare filename is looked up inside
        the backup directory; a path is used as given), overwriting the
        live database(s) in place.
    """
    instance_path = ctx.obj['instance_path']
    backup_dir = ctx.obj['backup_dir']

    archive_path = archive
    if not path.isabs(archive) and not path.exists(archive):
        candidate = path.join(backup_dir, archive)
        if path.exists(candidate):
            archive_path = candidate
    if not path.exists(archive_path):
        raise click.ClickException(f'Backup archive not found: {archive!r}')

    try:
        with zipfile.ZipFile(archive_path) as zf:
            infos = {i.filename: i.file_size for i in zf.infolist()}
    except zipfile.BadZipFile as exc:
        raise click.ClickException(f'{archive_path!r} is not a valid zip archive') from exc

    click.echo(f'Archive: {archive_path}')
    for name, size in infos.items():
        kind = 'users' if name == db.DEFAULT_USERS_DB_FILENAME else 'wiring'
        click.echo(f'  {name} ({kind}, {size / 1024:.0f} KB)')

    if only:
        wants_users = only == 'users'
        wanted = [n for n in infos if (n == db.DEFAULT_USERS_DB_FILENAME) == wants_users]
        if not wanted:
            raise click.ClickException(
                f'Archive has no {only!r} database to restore (--only {only})')

    service_active = _systemd_service_active()
    if service_active:
        click.secho(
            f'\nThis OVERWRITES the live database file(s) in {instance_path} in place.\n'
            f'The {_SERVICE_NAME}.service is currently active - it will be stopped '
            'before restoring and started again afterward automatically.', fg='yellow')
    else:
        click.secho(
            f'\nThis OVERWRITES the live database file(s) in {instance_path} in place.\n'
            'No systemd service is active to stop automatically - if aquaPi is '
            'running some other way (e.g. ./run/./dbg in a shell), stop it '
            'yourself first.', fg='yellow')

    safety_backup = db.create_backup_archive(
        db.resolve_wiring_db_path(instance_path), ctx.obj['users_db'], backup_dir,
        filename=f'{db.BACKUP_FILENAME_PREFIX}{datetime.now():%Y%m%d-%H%M%S}-pre-restore.zip')
    db.rotate_backups(backup_dir, keep=ctx.obj['backup_keep'])
    click.echo(f'Safety backup of the current state saved to: {safety_backup}')

    if not yes and not click.confirm('\nProceed with restore?', default=False):
        click.echo('Aborted.')
        return

    if service_active:
        click.echo(f'\nStopping {_SERVICE_NAME}.service ...')
        try:
            subprocess.run(['sudo', 'systemctl', 'stop', _SERVICE_NAME], check=True)
        except subprocess.CalledProcessError as exc:
            raise click.ClickException(
                f'Failed to stop {_SERVICE_NAME}.service - aborting before touching '
                'any database file.') from exc

    try:
        restored = db.restore_backup_archive(archive_path, instance_path, only=only)
    finally:
        if service_active:
            click.echo(f'Restarting {_SERVICE_NAME}.service ...')
            subprocess.run(['sudo', 'systemctl', 'start', _SERVICE_NAME], check=True)

    click.echo('\nRestored:')
    for p in restored:
        click.echo(f'  {p}')

    active_wiring = db.resolve_wiring_db_path(instance_path)
    restored_wiring = [p for p in restored if path.basename(p) != db.DEFAULT_USERS_DB_FILENAME]
    if restored_wiring and path.basename(restored_wiring[0]) != path.basename(active_wiring):
        click.secho(
            f'\nNote: the restored wiring database is named '
            f'{path.basename(restored_wiring[0])!r}, but the currently active one '
            f"is {path.basename(active_wiring)!r}. You may need to point "
            "AQUAPI_WIRING / config.json's DEFAULT_CONFIG at the restored name.",
            fg='yellow')

    if service_active:
        click.echo(f'\n{_SERVICE_NAME}.service restarted with the restored data.')
    else:
        click.echo('\nRestart aquaPi for the restored data to take effect.')


@cli.command('init-admin')
@click.pass_context
def init_admin(ctx):
    """ create the initial admin account and print its password - only
        while no user exists yet, otherwise nothing changes.

        install.sh runs this before the service first starts; the app
        would otherwise create the account itself and only log the
        password (journalctl under systemd), where a new user never
        finds it.
    """
    # German-only output, like reconfig: part of the guided install.sh flow
    created = db.ensure_default_admin(ctx.obj['users_db'])
    if not created:
        click.echo('Es gibt bereits Benutzerkonten - es wurde kein neues Admin-Konto angelegt.')
        return
    username, password = created
    click.echo('Ihr Admin-Zugang für die aquaPi-Oberfläche:')
    click.echo(f'   Benutzername: {username}')
    click.echo(f'   Passwort:     {password}')
    click.echo('Bitte notieren Sie das Passwort und ändern Sie es nach der ersten Anmeldung')
    click.echo('(Menü "Benutzer"). Es wird nicht noch einmal angezeigt.')


@cli.command()
@click.pass_context
def reconfig(ctx):
    """ interactively (re)configure Email/Telegram notification credentials.

        Replaces the entire stored account list for a channel with the one
        entered here - if a channel already has multiple accounts
        configured, running this collapses it down to one.
    """
    # Prompts/messages here are German-only, deliberately - this command is
    # what a (German-speaking, non-technical) customer hits during the
    # guided install.sh flow. Everything else in this CLI (--help text,
    # other commands) stays English, aimed at the maintainer. See
    # ROADMAP.md if English support is ever needed here too.
    users_db = ctx.obj['users_db']
    changed = False

    for channel in db.NOTIFICATION_CHANNELS:
        existing = db.get_notification_config(users_db, channel)
        if existing:
            n = len(existing)
            status = f'{n} Konto eingerichtet' if n == 1 else f'{n} Konten eingerichtet'
        else:
            status = 'nicht eingerichtet'
        click.echo(f'\n{channel}: {status}')

        if not click.confirm(f'{channel} jetzt einrichten?', default=False):
            continue

        if channel == 'Email':
            account = {
                'server': click.prompt('SMTP-Server (z.B. smtp.gmail.com)'),
                'login': click.prompt('Benutzername'),
                'pwd': click.prompt('Passwort', hide_input=True),
                'from': click.prompt('Absenderadresse'),
                'to': click.prompt('Empfängeradresse'),
            }
        else:  # 'Telegram'
            account = {
                'bot_token': click.prompt('Bot-Token', hide_input=True),
                'chat_name': click.prompt('Chat-Name'),
            }
            # a blank chat_id is omitted entirely (not stored as '') -
            # DriverTelegram.find_ports() already auto-detects a missing
            # chat_id on next app start, no need to reimplement that here
            chat_id = click.prompt(
                'Chat-ID (leer lassen, um sie beim nächsten Start automatisch zu ermitteln)',
                default='', show_default=False)
            if chat_id:
                account['chat_id'] = chat_id

        db.set_notification_config(users_db, channel, [account])
        click.echo(f'{channel}-Konfiguration gespeichert.')
        changed = True

    if not changed:
        click.echo('\nKeine Änderungen vorgenommen.')
        return

    # MachineRoom.__init__ reads notification config once at construction,
    # no live-reload path exists - unlike 'restore', this doesn't need to
    # stop the service first (writing ordinary rows to users.sqlite while
    # the app has it open is fine), just restart it afterward so the new
    # config actually takes effect instead of silently sitting unused
    # until whenever the next restart happens to occur.
    if _systemd_service_active():
        click.echo(f'\n{_SERVICE_NAME}.service wird neu gestartet, damit die neue '
                  'Konfiguration wirksam wird ...')
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', _SERVICE_NAME], check=True)
        except subprocess.CalledProcessError:
            click.secho(
                f'{_SERVICE_NAME}.service konnte nicht automatisch neu gestartet werden - '
                f'starten Sie ihn manuell neu (`sudo systemctl restart {_SERVICE_NAME}`).',
                fg='yellow')
        else:
            click.echo(f'{_SERVICE_NAME}.service neu gestartet.')
    else:
        click.echo('\nStarten Sie aquaPi neu, damit die neue Benachrichtigungs-Konfiguration '
                  'wirksam wird.')


_SERVICE_UNIT_PATH = '/etc/systemd/system/aquapi.service'

_QUESTDB_SERVICE_NAME = 'questdb'
_QUESTDB_UNIT_PATH = '/etc/systemd/system/questdb.service'

# QuestDB's own `questdb.sh start -c` ("container mode") runs the JVM in the
# foreground - what systemd wants - with the usual root ~/.questdb
_QUESTDB_UNIT_TEMPLATE = """\
[Unit]
Description=QuestDB, history database for aquaPi
After=local-fs.target

[Service]
Type=simple
User={user}
{java_home}ExecStart={questdb_sh} start -c
Restart=on-failure
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""


def _find_questdb(repo_root: str) -> tuple[str, str | None] | None:
    """ (questdb.sh path, JAVA_HOME or None) of the QuestDB that ./init
        installed next to the repo, or None without one (e.g. 32-bit Pi,
        where aquaPi keeps its history in memory)
    """
    release = None
    try:
        with open(path.join(repo_root, 'init'), encoding='utf8') as f:
            m = re.search(r'^QuestRel="([^"]+)"', f.read(), re.M)
            release = m.group(1) if m else None
    except OSError:
        pass
    dirs = ([path.join(repo_root, f'questdb-{release}')] if release
            else sorted(glob.glob(path.join(repo_root, 'questdb-*/'))))
    for qdb_dir in reversed(dirs):
        for script in (path.join(qdb_dir, 'questdb.sh'), path.join(qdb_dir, 'bin', 'questdb.sh')):
            if path.isfile(script):
                if path.exists(path.join(path.dirname(script), 'java')):
                    return script, None     # bundled JRE (amd64 package)
                jvms = sorted(glob.glob('/usr/lib/jvm/java-*-openjdk-*'))
                return script, (jvms[-1] if jvms else None)
    return None


_SERVICE_UNIT_TEMPLATE = """\
[Unit]
Description=aquaPi aquarium controller
After=network-online.target{after}
Wants=network-online.target{after}

[Service]
Type=simple
User={user}
WorkingDirectory={repo_root}
Environment=FLASK_APP=aquaPi
Environment=FLASK_DEBUG=0
ExecStart={repo_root}/venv/bin/flask run --host {host} --port {port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


@cli.command('service-unit')
@click.option('--host', default='0.0.0.0',
             help='Bind address (default: all interfaces).')
@click.option('--port', default=5000, type=int)
@click.option('--install', is_flag=True,
             help='Write the unit, daemon-reload, enable+start it (needs sudo).')
@click.option('--uninstall', is_flag=True,
             help='Stop+disable+remove an installed unit (needs sudo).')
@click.option('--yes', '-y', is_flag=True, help='Skip the confirmation prompt.')
def service_unit(host, port, install, uninstall, yes):
    """ generate (and optionally install) a systemd unit for aquaPi.

        Runs the Werkzeug dev server as a single simple process - never a
        multi-worker WSGI server. MsgBus/MachineRoom assume exactly one
        process holds the live bus state in memory; multiple workers would
        each build their own disconnected bus.
    """
    if install and uninstall:
        raise click.ClickException('--install and --uninstall are mutually exclusive.')

    if uninstall:
        click.echo(f'This will stop, disable, and remove {_SERVICE_UNIT_PATH} '
                  f'and {_QUESTDB_UNIT_PATH} (if present).')
        if not yes and not click.confirm('Proceed?', default=False):
            click.echo('Aborted.')
            return
        for name, unit_path in ((_SERVICE_NAME, _SERVICE_UNIT_PATH),
                                (_QUESTDB_SERVICE_NAME, _QUESTDB_UNIT_PATH)):
            if name == _QUESTDB_SERVICE_NAME and not path.exists(unit_path):
                continue
            for cmd in (['sudo', 'systemctl', 'stop', name],
                       ['sudo', 'systemctl', 'disable', name],
                       ['sudo', 'rm', '-f', unit_path]):
                subprocess.run(cmd, check=True)
            click.echo(f'{name}.service removed.')
        subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
        return

    repo_root = str(Path(__file__).resolve().parent.parent)
    user = getpass.getuser()
    # QuestDB gets its own unit so it is up after every boot too - without
    # it, a reboot left aquaPi running without its history database
    questdb = _find_questdb(repo_root)
    units = []
    if questdb:
        questdb_sh, java_home = questdb
        units.append((_QUESTDB_SERVICE_NAME, _QUESTDB_UNIT_PATH, _QUESTDB_UNIT_TEMPLATE.format(
            user=user, questdb_sh=questdb_sh,
            java_home=f'Environment=JAVA_HOME={java_home}\n' if java_home else '')))
    units.append((_SERVICE_NAME, _SERVICE_UNIT_PATH, _SERVICE_UNIT_TEMPLATE.format(
        user=user, repo_root=repo_root, host=host, port=port,
        after=f' {_QUESTDB_SERVICE_NAME}.service' if questdb else '')))

    for name, unit_path, content in units:
        click.echo(f'# {unit_path}\n{content}')
    if not install:
        return

    names = ' and '.join(f'{name}.service' for name, _, _ in units)
    click.echo(f'This will write the above, then run \'systemctl daemon-reload\' and '
              f'enable and start {names}.')
    if not yes and not click.confirm('Proceed?', default=False):
        click.echo('Aborted.')
        return

    for _, unit_path, content in units:
        subprocess.run(['sudo', 'tee', unit_path], input=content.encode(),
                       stdout=subprocess.DEVNULL, check=True)
    subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
    if questdb:
        # ./init may have started QuestDB by hand - the unit's own start
        # would then fail with "Already running", so hand it over
        env = dict(environ, **({'JAVA_HOME': questdb[1]} if questdb[1] else {}))
        subprocess.run([questdb[0], 'stop'], env=env, check=False)
    for name, _, _ in units:
        subprocess.run(['sudo', 'systemctl', 'enable', '--now', name], check=True)

    click.echo(f'\n{_SERVICE_NAME}.service installed and started.')
    subprocess.run(['systemctl', 'status', _SERVICE_NAME, '--no-pager'], check=False)
    click.echo('\nUseful commands:')
    click.echo(f'  systemctl status {_SERVICE_NAME}')
    click.echo(f'  sudo systemctl restart {_SERVICE_NAME}')
    click.echo(f'  sudo systemctl stop {_SERVICE_NAME}')
    click.echo(f'  journalctl -u {_SERVICE_NAME} -f')


if __name__ == '__main__':
    # nicer --help/usage output than "python -m aquaPi.cli". cli is a
    # click.Group (see the decorators above), not the raw function - Click's
    # own __call__ parses argv and supplies ctx/instance_path itself, so
    # pylint's no-value-for-parameter here is a false positive.
    cli(prog_name='./manage')  # pylint: disable=no-value-for-parameter
