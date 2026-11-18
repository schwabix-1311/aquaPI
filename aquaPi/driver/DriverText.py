#!/usr/bin/env python3

import logging
from socket import gaierror, gethostname
import smtplib
from email.message import EmailMessage
from typing import Any
import requests

from . import driver_config
from .base import (OutDriver, IoPort, PortFunc, DriverConfigError)


log = logging.getLogger('driver.DriverText')


def _host_label() -> str:
    """ short hostname for tagging outgoing messages, e.g. 'aquapi2' -
        lets recipients tell which aquaPi a mail/message came from when
        several share an inbox or Telegram chat
    """
    return gethostname().split('.')[0]


# ========== text (Email/Telegram) ==========


class DriverText(OutDriver):
    """ abstract base of text (output) drivers such as email, Telegram, display
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.name = '!abstract TEXT'
        self._val: str = ''

    @staticmethod
    def _host_tag(line: str) -> str:
        """ fold the sending host into a single line (email subject or the
            message's 1st line), no extra line - see _host_label()
        """
        return f'[{_host_label()}] {line}'

    # pylint: disable-next=arguments-renamed
    def write(self, subj_text: str) -> None:
        """ 1st line of subj_text is headline, rest is body
        """
        self._val = subj_text

    def read(self) -> str:
        """ read previously written text
        """
        return self._val


class DriverEmail(DriverText):
    """ this driver produces email from a text
    """

    _BUS = 'web API'

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if 'Email' not in driver_config:
            log.info('Email is not configured, no Email alerts (set up with ./manage reconfig)')
            return io_ports

        idx = 0
        for cfg in driver_config['Email']:
            req = {'server', 'login', 'pwd', 'from', 'to'}
            if not req <= cfg.keys():
                log.error("Incomplete email configuration #%d!\n"
                          "Please add values for %s to the global config file.",
                          idx + 1, req - cfg.keys())
                raise DriverConfigError()

            try:
                with smtplib.SMTP(cfg['server']) as smtp:
                    # smtp.set_debuglevel(1)
                    smtp.starttls()
                    smtp.login(cfg['login'], cfg['pwd'])

            except gaierror:
                log.error("There's no connection to the internet, thus no email")
                return io_ports

            except Exception as ex:
                log.error(str(ex))
                raise DriverConfigError('Email failure! Check error message:'
                                        + str(ex)) from ex

            port_name = f'Email #{idx + 1}'
            io_ports[port_name] = IoPort(PortFunc.Tout,
                                         DriverEmail,
                                         {'idx': str(idx),
                                          'server': cfg['server'],
                                          'login': cfg['login'],
                                          'pwd': cfg['pwd'],
                                          'from': cfg['from'],
                                          'to': cfg['to'],
                                          },
                                         [],
                                         shareable=True)
            idx += 1
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.name = f'Email({cfg["to"]})'

    def write(self, subj_text: str) -> None:
        """ 1st line is used as subject, rest is body
            If only single line, body will repeat the subject.
        """
        msg = EmailMessage()
        subject, _, body = subj_text.partition('\n')
        msg['Subject'] = self._host_tag(subject)
        msg.set_content(body if '\n' in subj_text else subject)
        msg['From'] = self.cfg["from"]
        msg['To'] = self.cfg["to"]

        log.verbose('%s -> %r', self.name, subj_text)
        try:
            with smtplib.SMTP(self.cfg['server']) as smtp:
                # smtp.set_debuglevel(1)
                smtp.starttls()
                smtp.login(self.cfg['login'], self.cfg['pwd'])
                smtp.send_message(msg)
        except Exception:
            log.exception('%s failed to send email', self.name)
        self._val = subj_text


def telegram_url(bot_token: str) -> str:
    return f'https://api.telegram.org/bot{bot_token}/'


def telegram_bot_name(bot_token: str) -> str:
    """ the bot's @username; raises DriverConfigError for an invalid
        token, requests' exceptions if Telegram can't be reached
    """
    return DriverTelegram._bot_request(telegram_url(bot_token), 'getMe')['username']


def find_telegram_chat(bot_token: str) -> dict[str, Any] | None:
    """ {'chat_id', 'chat_name'} of the latest message containing "aquaPi"
        the bot received (Telegram keeps them for 24 hours), or None.
        Works for groups, direct chats with the bot and channels. In a
        group, a bot in its default privacy mode only sees commands, so
        that is where '/aquapi@<bot name>' is needed.
    """
    updates = DriverTelegram._bot_request(telegram_url(bot_token), 'getUpdates')
    for upd in reversed(updates or []):
        msg = upd.get('message') or upd.get('channel_post') or {}
        if 'aquapi' in (msg.get('text') or '').lower():
            chat = msg['chat']
            name = (chat.get('title') or chat.get('username')
                    or chat.get('first_name') or str(chat['id']))
            return {'chat_id': chat['id'], 'chat_name': name}
    return None


class DriverTelegram(DriverText):
    """ this driver sends messages to a Telegram chat via a bot.
        `./manage reconfig` asks for the bot token and finds the chat id
        via find_telegram_chat(). A configuration without chat id is
        completed the same way at startup, but only for this run - it
        isn't saved.
        Caveat: when Telegram upgrades a group to a supergroup, the chat
        gets a new id and the configured one stops working.
    """

    _BUS = 'web API'

    @staticmethod
    def _bot_request(url: str, api: str, json: dict | None = None) -> Any:
        res = requests.post(f"{url}{api}", json=json, timeout=10).json()
        if not res['ok']:
            raise DriverConfigError()
        return res['result']

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if 'Telegram' not in driver_config:
            log.info('Telegram is not configured, no Telegram alerts (set up with ./manage reconfig)')
            return io_ports

        idx = 0
        for cfg in driver_config['Telegram']:
            if not cfg['bot_token']:
                log.error("The global configuration #%d contains no bot token for Telegram",
                          idx + 1)
                raise DriverConfigError()

            url = telegram_url(cfg['bot_token'])
            try:
                DriverTelegram._bot_request(url, 'getMe')
            except requests.exceptions.ConnectionError:
                log.error("There's no connection to the internet, thus no Telegram")
                return io_ports

            except DriverConfigError:
                # never log the token itself, it's a credential
                log.error("The bot token of Telegram configuration #%d is invalid!", idx + 1)

            except Exception as ex:
                log.error(str(ex))
                raise DriverConfigError('Telegram failure! Check error message:'
                                        + str(ex)) from ex

            if 'chat_id' not in cfg:
                chat = find_telegram_chat(cfg['bot_token'])
                if chat:
                    cfg.update(chat)
                    log.info("Found Telegram chat %s - run ./manage reconfig to keep it",
                             cfg['chat_name'])

            req = {'bot_token', 'chat_name', 'chat_id'}
            if not req <= cfg.keys():
                log.error("Incomplete Telegram configuration #%d!\n"
                          "Missing %r - set it up with ./manage reconfig.",
                          idx + 1, req - cfg.keys())
                raise DriverConfigError()

            port_name = f'Telegram #{idx + 1}'
            io_ports[port_name] = IoPort(PortFunc.Tout,
                                         DriverTelegram,
                                         {'idx': str(idx),
                                          'url': url,
                                          'chat_name': cfg['chat_name'],
                                          'chat_id': cfg['chat_id']
                                          },
                                         [],
                                         shareable=True)
            idx += 1
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.name = f'Telegram({cfg["chat_name"]})'

    def write(self, subj_text: str) -> None:
        """ all lines are sent as one message
        """
        try:
            payload = {"chat_id": self.cfg['chat_id'],
                       'text': self._host_tag(subj_text)}
            res = DriverTelegram._bot_request(self.cfg['url'], 'sendMessage', json=payload)
            log.verbose('%s -> %r : %r', self.name, subj_text, res)
        except Exception:
            log.exception('%s failed to send Telegram message with error: ', self.name)

        self._val = subj_text
