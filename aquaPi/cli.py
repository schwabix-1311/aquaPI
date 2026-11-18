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
import platform
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


# ---- language of the end-user facing commands (init-admin, reconfig) ----
# install.sh asks for it and saves it to instance/language, so a later
# `./manage reconfig` keeps talking the same language. Everything else in
# this CLI (--help text, other commands) is English, aimed at the
# maintainer.

_LANG_FILE = 'language'
_lang = 'en'


def _detect_lang(instance_path: str) -> str:
    """ AQUAPI_LANG, else instance/language, else the locale ($LANG) """
    lang = environ.get('AQUAPI_LANG', '')
    if not lang:
        try:
            with open(path.join(instance_path, _LANG_FILE), encoding='utf-8') as f:
                lang = f.read().strip()
        except OSError:
            lang = environ.get('LC_ALL') or environ.get('LC_MESSAGES') or environ.get('LANG', '')
    return 'de' if lang.lower().startswith('de') else 'en'


def _t(de: str, en: str) -> str:
    return de if _lang == 'de' else en


def _confirm(text: str, default: bool = False) -> bool:
    """ like click.confirm, but German answers with j - accepts j, y and n
        in either language, Enter takes the default
    """
    yes = _t('j', 'y')
    suffix = f' [{yes.upper()}/n]' if default else f' [{yes}/N]'
    while True:
        answer = click.prompt(text + suffix, default='', show_default=False).strip().lower()
        if not answer:
            return default
        if answer[0] in 'jy':
            return True
        if answer[0] == 'n':
            return False


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
    global _lang  # pylint: disable=global-statement
    _lang = _detect_lang(instance_path)
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
    # output in the user's language (see _detect_lang): part of the
    # guided install.sh flow
    created = db.ensure_default_admin(ctx.obj['users_db'])
    if not created:
        click.echo(_t('Es gibt bereits Benutzerkonten - es wurde kein neues Admin-Konto angelegt.',
                      'User accounts already exist - no new admin account was created.'))
        return
    username, password = created
    click.echo(_t('Dein Admin-Zugang für die aquaPi-Oberfläche:',
                  'Your admin login for the aquaPi interface:'))
    click.echo(_t(f'   Benutzername: {username}', f'   Username: {username}'))
    click.echo(_t(f'   Passwort:     {password}', f'   Password: {password}'))
    click.echo(_t('Bitte notiere das Passwort und ändere es nach der ersten Anmeldung',
                  'Please write the password down and change it after your first login'))
    click.echo(_t('(Menü "Benutzer"). Es wird nicht noch einmal angezeigt.',
                  '("Users" menu). It will not be shown again.'))


def _prompt_telegram_account() -> dict:
    """ bot token, then find the chat by a message the user sends there
        (see DriverText.find_telegram_chat). Without a connection to
        Telegram, or if the user gives up, chat name and id are entered
        by hand; a blank chat id is omitted, not stored as '' - the app
        then retries the detection at each start.
    """
    from .driver.DriverText import (DriverConfigError, find_telegram_chat,
                                    telegram_bot_name)

    while True:
        token = click.prompt(_t('Bot-Token (von @BotFather)', 'Bot token (from @BotFather)'),
                             hide_input=True)
        try:
            bot_name = telegram_bot_name(token)
            break
        except DriverConfigError:
            click.secho(_t('Telegram kennt diesen Bot-Token nicht, bitte erneut eingeben.',
                           'Telegram doesn\'t know this bot token, please enter it again.'),
                        fg='red')
        except Exception:
            click.secho(_t('Telegram ist nicht erreichbar - Chat bitte von Hand eintragen.',
                           'Telegram can\'t be reached - please enter the chat by hand.'),
                        fg='yellow')
            bot_name = ''
            break

    account: dict = {'bot_token': token}
    if bot_name:
        click.echo(_t(f'\nJetzt den Chat festlegen, in den aquaPi schreiben soll:\n'
                      f'- Gruppe: @{bot_name} zur Gruppe hinzufügen und dort\n'
                      f'  /aquapi@{bot_name} senden\n'
                      f'- Direktchat: @{bot_name} in Telegram öffnen und "aquaPi" senden',
                      f'\nNow choose the chat aquaPi should write to:\n'
                      f'- group: add @{bot_name} to the group and send\n'
                      f'  /aquapi@{bot_name} there\n'
                      f'- direct chat: open @{bot_name} in Telegram and send "aquaPi"'))
        while True:
            click.prompt(_t('Enter drücken, sobald die Nachricht gesendet ist',
                            'Press Enter once the message is sent'),
                         default='', show_default=False)
            try:
                chat = find_telegram_chat(token)
            except Exception:
                chat = None
            if chat:
                if _confirm(_t(f'Chat "{chat["chat_name"]}" gefunden. Diesen verwenden?',
                               f'Found chat "{chat["chat_name"]}". Use it?'), default=True):
                    account.update(chat)
                    return account
            else:
                click.echo(_t('Keine Nachricht mit "aquaPi" gefunden.',
                              'No message containing "aquaPi" found.'))
            if not _confirm(_t('Erneut versuchen?', 'Try again?'), default=True):
                break

    account['chat_name'] = click.prompt(_t('Chat-Name', 'Chat name'))
    chat_id = click.prompt(_t('Chat-ID (leer lassen, um sie beim Start zu ermitteln)',
                              'Chat ID (leave empty to detect it at startup)'),
                           default='', show_default=False)
    if chat_id:
        account['chat_id'] = chat_id
    return account


@cli.command()
@click.pass_context
def reconfig(ctx):
    """ interactively (re)configure Email/Telegram notification credentials.

        Replaces the entire stored account list for a channel with the one
        entered here - if a channel already has multiple accounts
        configured, running this collapses it down to one.
    """
    # prompts/messages in the user's language (see _detect_lang) - this
    # command is what a non-technical user hits during install.sh
    users_db = ctx.obj['users_db']
    changed = False

    for channel in db.NOTIFICATION_CHANNELS:
        existing = db.get_notification_config(users_db, channel)
        if existing:
            n = len(existing)
            status = (_t(f'{n} Konto eingerichtet', f'{n} account set up') if n == 1
                      else _t(f'{n} Konten eingerichtet', f'{n} accounts set up'))
        else:
            status = _t('nicht eingerichtet', 'not set up')
        click.echo(f'\n{channel}: {status}')

        if not _confirm(_t(f'{channel} jetzt einrichten?', f'Set up {channel} now?')):
            continue

        if channel == 'Email':
            account = {
                'server': click.prompt(_t('SMTP-Server (z.B. smtp.gmail.com)',
                                          'SMTP server (e.g. smtp.gmail.com)')),
                'login': click.prompt(_t('Benutzername', 'Username')),
                'pwd': click.prompt(_t('Passwort', 'Password'), hide_input=True),
                'from': click.prompt(_t('Absenderadresse', 'Sender address')),
                'to': click.prompt(_t('Empfängeradresse', 'Recipient address')),
            }
        else:  # 'Telegram'
            account = _prompt_telegram_account()

        db.set_notification_config(users_db, channel, [account])
        click.echo(_t(f'{channel}-Konfiguration gespeichert.', f'{channel} configuration saved.'))
        changed = True

    if not changed:
        click.echo(_t('\nKeine Änderungen vorgenommen.', '\nNo changes made.'))
        return

    # MachineRoom.__init__ reads notification config once at construction,
    # no live-reload path exists - unlike 'restore', this doesn't need to
    # stop the service first (writing ordinary rows to users.sqlite while
    # the app has it open is fine), just restart it afterward so the new
    # config actually takes effect instead of silently sitting unused
    # until whenever the next restart happens to occur.
    if _systemd_service_active():
        click.echo(_t(f'\n{_SERVICE_NAME}.service wird neu gestartet, damit die neue '
                      'Konfiguration wirksam wird ...',
                      f'\nRestarting {_SERVICE_NAME}.service so the new configuration '
                      'takes effect ...'))
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', _SERVICE_NAME], check=True)
        except subprocess.CalledProcessError:
            click.secho(_t(
                f'{_SERVICE_NAME}.service konnte nicht automatisch neu gestartet werden - '
                f'starte ihn manuell neu (`sudo systemctl restart {_SERVICE_NAME}`).',
                f'{_SERVICE_NAME}.service could not be restarted automatically - '
                f'restart it by hand (`sudo systemctl restart {_SERVICE_NAME}`).'),
                fg='yellow')
        else:
            click.echo(_t(f'{_SERVICE_NAME}.service neu gestartet.',
                          f'{_SERVICE_NAME}.service restarted.'))
    else:
        click.echo(_t('\nStarte aquaPi neu, damit die neue Benachrichtigungs-Konfiguration '
                      'wirksam wird.',
                      '\nRestart aquaPi for the new notification configuration to take '
                      'effect.'))


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
# the JVM needs a while on a Pi Zero before it accepts connections; count as
# started only once port 8812 answers, so aquapi.service (ordered after this
# unit) doesn't find it unreachable and fall back to in-memory history.
# Never fails the unit: after 90 s aquaPi starts anyway.
ExecStartPost=/bin/bash -c 'for i in {{1..90}}; do (echo > /dev/tcp/127.0.0.1/8812) 2>/dev/null && exit 0; sleep 1; done; echo "QuestDB not reachable on port 8812 after 90 s" >&2'
TimeoutStartSec=150
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
    # QuestDB only exists for 64-bit systems (hist_nodes.py checks the same);
    # a leftover questdb-* dir on a 32-bit Pi must not become a dead service
    if '64' not in platform.architecture()[0]:
        return None
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
