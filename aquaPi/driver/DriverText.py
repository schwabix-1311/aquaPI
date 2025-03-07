#!/usr/bin/env python3

import logging
import smtplib
from email.message import EmailMessage

from . import driver_config
from .base import (OutDriver, IoPort, PortFunc, DriverEmailError)


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
        if 'EMAIL' not in driver_config:
            log.error('You have no email configuration. Email delivery will not work!')
            return io_ports

        idx = 0
        for cfg in driver_config['EMAIL']:
            if not cfg['to']:
                raise DriverEmailError(f'Email configuration #{idx} contains no recipient: {cfg}')

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

#TODO: test email connection, raise DriverEmailError
#  try:
#  except DriverEmailError ex:
#      log.exception('Failed to connect to email server:')
#      raise

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
                #smtp.set_debuglevel(1)
                smtp.starttls()
                smtp.login(self.cfg['login'], self.cfg['pwd'])
                smtp.send_message(msg)
        except Exception:
            log.exception('Atempt to send email: ')
        self._val = subj_text


"""
=== for DriverTelegram ===

Extract from medium.com "using-python-to-send-telegram-messages-in-3-simple-steps"

2. Getting your chat ID

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
3. Sending your Telegram message using Python

Copy and paste 1) your Telegram bot token and 2) your chat ID from the previous 2 steps into the following Python script. (And do customize your message too)

import requests
TOKEN = "YOUR TELEGRAM BOT TOKEN"
chat_id = "YOUR CHAT ID"
message = "hello from your telegram bot"
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
print(requests.get(url).json()) # this sends the message
"""
