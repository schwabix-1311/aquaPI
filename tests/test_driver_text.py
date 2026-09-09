#!/usr/bin/env python3
""" Tests for DriverText (aquaPi/driver/DriverText.py): the sending host
    is folded into the 1st line only - the email *subject*, and the
    Telegram message's leading line - never as an extra line, and the
    email *body* stays untouched.
"""

import pytest

import aquaPi.driver.DriverText as dt_mod
from aquaPi.driver.DriverText import DriverEmail, DriverTelegram
from aquaPi.driver.base import PortFunc


@pytest.fixture(autouse=True)
def fake_host(monkeypatch):
    # FQDN in -> short label out
    monkeypatch.setattr(dt_mod, 'gethostname', lambda: 'testhost.fritz.box')


# --- Email -------------------------------------------------------------


class _FakeSMTP:
    """ context-manager stand-in for smtplib.SMTP; records the last msg """
    last_msg = None

    def __init__(self, server):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, pwd):
        pass

    def send_message(self, msg):
        _FakeSMTP.last_msg = msg


@pytest.fixture
def email_driver(monkeypatch):
    monkeypatch.setattr(dt_mod.smtplib, 'SMTP', _FakeSMTP)
    _FakeSMTP.last_msg = None
    cfg = {'server': 's', 'login': 'l', 'pwd': 'p',
           'from': 'a@x', 'to': 'b@x'}
    return DriverEmail(cfg, PortFunc.Tout)


def test_email_subject_gets_host_tag_body_unchanged(email_driver):
    email_driver.write('Warnung: AlertAbove(>=7)\nMesswert zu HOCH: 7.30')

    msg = _FakeSMTP.last_msg
    assert msg['Subject'] == '[testhost] Warnung: AlertAbove(>=7)'
    body = msg.get_content()
    assert body.strip() == 'Messwert zu HOCH: 7.30'
    assert 'testhost' not in body


def test_email_single_line_tags_subject_only(email_driver):
    email_driver.write('kurze Meldung')

    msg = _FakeSMTP.last_msg
    assert msg['Subject'] == '[testhost] kurze Meldung'
    assert msg.get_content().strip() == 'kurze Meldung'


# --- Telegram --------------------------------------------------------------


class _FakeResp:
    def json(self):
        return {'ok': True, 'result': 'sent'}


@pytest.fixture
def telegram_driver(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({'url': url, 'json': json})
        return _FakeResp()

    monkeypatch.setattr(dt_mod.requests, 'post', fake_post)
    cfg = {'url': 'https://api.telegram.org/botTOKEN/',
           'chat_name': 'aquaBroadcast', 'chat_id': -1}
    drv = DriverTelegram(cfg, PortFunc.Tout)
    drv._sent = calls
    return drv


def test_telegram_message_gets_host_prefix_no_extra_line(telegram_driver):
    telegram_driver.write('Warnung: AlertAbove(>=7)\nMesswert zu HOCH: 7.30')

    payload = telegram_driver._sent[-1]['json']
    assert payload['chat_id'] == -1
    assert payload['text'] == (
        '[testhost] Warnung: AlertAbove(>=7)\nMesswert zu HOCH: 7.30')
    # tag is folded into the existing 1st line, not prepended as its own
    assert payload['text'].count('\n') == 1
