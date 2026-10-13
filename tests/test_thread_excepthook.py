#!/usr/bin/env python3
""" Tests for aquaPi's threading.excepthook: an exception ending any thread
    is logged (and so reaches the log file), not only printed to stderr.
"""

import logging
import threading

import aquaPi


def _boom():
    raise RuntimeError('boom in a worker thread')


def test_unhandled_thread_exception_is_logged(caplog, monkeypatch):
    monkeypatch.setattr(threading, 'excepthook', aquaPi._log_thread_exception)
    with caplog.at_level(logging.ERROR, logger='aquaPi'):
        t = threading.Thread(target=_boom, name='PIDpulse')
        t.start()
        t.join()
    assert 'Unhandled exception in thread PIDpulse' in caplog.text
    assert 'boom in a worker thread' in caplog.text


def test_system_exit_in_a_thread_is_not_logged(caplog, monkeypatch):
    monkeypatch.setattr(threading, 'excepthook', aquaPi._log_thread_exception)
    with caplog.at_level(logging.ERROR, logger='aquaPi'):
        t = threading.Thread(target=lambda: (_ for _ in ()).throw(SystemExit))
        t.start()
        t.join()
    assert caplog.text == ''
