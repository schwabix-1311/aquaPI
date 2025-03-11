#!/usr/bin/env python3

import logging
import smtplib
from email.message import EmailMessage
import requests

from . import driver_config
from .base import (OutDriver, IoPort, PortFunc, DriverConfigError)


log = logging.getLogger('driver.DriverText')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== PWM ==========


class DriverText(OutDriver):
    """ abstract base of text (output) drivers such as email, Telegram, display
    """

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self.name: str = '!abstract TEXT'
        self._val = ''

    # pylint: disable-next=arguments-renamed
    def write(self, subj_text: str) -> None:
        """ 1st line of subj_text is headline, rest is body
        """
        self._val = subj_text

    def read(self) -> list[str]:
        """ read previously written text
        """
        return self._val


class DriverEmail(DriverText):
    """ this driver produces email from a text
    """

    @staticmethod
    def find_ports() -> dict[str, IoPort]:
        io_ports = {}
        if 'Email' not in driver_config:
            log.error('You have no Email configuration. Email delivery will not work!')
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
            except Exception as ex:
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
                                         [])
            idx += 1
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._cfg = cfg.copy()
        self.name = f'Email({self._cfg["to"]})'

    def write(self, subj_text: str) -> None:
        """ 1st line is used as subject, rest is body
            If only single line, body will repeat the subject.
        """
        msg = EmailMessage()
        lines = subj_text.split('\n')
        if len(lines) > 1:
            msg['Subject'] = lines[0]
            msg.set_content('\n'.join(lines[1:]))
        else:
            msg['Subject'] = lines[0]
            msg.set_content(lines[0])
        msg['From'] = self.cfg["from"]
        msg['To'] = self.cfg["to"]

        log.info('%s -> %r', self.name, subj_text)
        try:
            with smtplib.SMTP(self.cfg['server']) as smtp:
                # smtp.set_debuglevel(1)
                smtp.starttls()
                smtp.login(self.cfg['login'], self.cfg['pwd'])
                smtp.send_message(msg)
        except Exception:
            log.exception('Atempt to send email: ')
        self._val = subj_text


class DriverTelegram(DriverText):
    """ this driver produces messages on Telegram
=== for DriverTelegram ===
Extract from medium.com "using-python-to-send-telegram-messages-in-3-simple-steps"
2. Getting your chat ID  -  TODO: automate this??
In Telegram, every chat has a chat ID, and we need this chat ID to send Telegram messages using Python.
Send your Telegram bot a message (any random message)
Run this Python script to find your chat ID
  import requests
  TOKEN = "YOUR TELEGRAM BOT TOKEN"
  url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
  print(requests.get(url).json())
This script calls the getUpdates function, which kinda checks for new messages. We can find our chat ID from the returned JSON (the one in red)
Note: if you don’t send your Telegram bot a message, your results might be empty.
3. Copy and paste the chat ID into our next step

A bad caveat:
see _local/telegram_supergroup.log for sequence of supergroup upgrade messages
    """

    @staticmethod
    def _bot_request(url: str, api: str, json: str = "") -> str:
        res = requests.post(f"{url}{api}", json=json, timeout=10).json()
        if not res['ok']:
            raise DriverConfigError()
        return res['result']

    @staticmethod
    def find_ports() -> dict[str, IoPort]:

        def _auto_detect_chat(url: str, cfg: dict[str, str]) -> bool:
            res = DriverTelegram._bot_request(url, 'getUpdates')
# res = [{...},{"update_id":23832555,"message": {"message_id":39,"from":{"id":126177523, "is_bot":false, "first_name":"Markus", "username":"schwabix", "language_code":"de"},"chat":{"id":-1002400534091,"title":"aquaBroadcast","type":"supergroup"},"date":1741614412,"text":"setup aquaPi"}}]
            if res:
                log.warning("auto-detect %s", res)
                for upd in res:
                    try:
                        if upd['message']:
                            if 'aquapi' in upd['message']['text'].lower():
                                cfg['chat_id'] = upd['message']['chat']['id']
                                cfg['chat_name'] = upd['message']['chat']['title']
                                return True
                    except Exception:
                        pass
            return False

        res = ''
        io_ports = {}
        if 'Telegram' not in driver_config:
            log.error('You have no Telegram configuration. Message delivery will not work!')
            return io_ports

        idx = 0
        for cfg in driver_config['Telegram']:
            if not cfg['bot_token']:
                log.error("The global configuration #%d contains no bot token for Telegram: %r",
                          idx + 1, cfg)
                raise DriverConfigError()

            url = f"https://api.telegram.org/bot{cfg['bot_token']}/"
            try:
                res = DriverTelegram._bot_request(url, 'getMe')
# res = {"id":813504918,"is_bot":true,"first_name":"zuHause","username":"Schwabix_bot","can_join_groups":true,"can_read_all_group_messages":false,"supports_inline_queries":false,"can_connect_to_business":false,"has_main_web_app":false}
            except DriverConfigError:
                log.error("The bot token %s for Telegram is invalid! Server replied: %s",
                          cfg['bot_token'], res)

            # try user-assisted detection,
            # user must send the word "aquaPi" to a chat or group chat where his bot has membership
            if 'chat_id' not in cfg:
                if _auto_detect_chat(url, cfg):
                    log.warning("Found chat name %s", cfg['chat_name'])

            req = {'bot_token', 'chat_name', 'chat_id'}
            if not req <= cfg.keys():
                log.error("Incomplete Telegram configuration #%d!\n"
                          "Please add values for %r to the global config file.",
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
                                         [])
            idx += 1
        return io_ports

    def __init__(self, cfg: dict[str, str], func: PortFunc):
        super().__init__(cfg, func)
        self._cfg = cfg.copy()
        self.name = f'Telegram({self._cfg["chat_name"]})'

    def write(self, subj_text: str) -> None:
        """ all lines are sent as one message
        """
        try:
            payload = {"chat_id": self.cfg['chat_id'], 'text': subj_text}
            res = DriverTelegram._bot_request(self.cfg['url'], 'sendMessage', json=payload)
        except Exception:
            log.exception('%s failed to send Telegram message with error: ', self.name)

        log.info('%s -> %r : %r', self.name, subj_text, res)
        self._val = subj_text
