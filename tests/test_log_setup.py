#!/usr/bin/env python3
""" create_app()'s logging setup must work on a fresh install: logs/ is
    git-ignored, so neither a clone nor the release bundle contains it
"""

import copy
import logging.handlers

from aquaPi import _make_log_dirs, log_default


def test_missing_log_dir_is_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)         # handler path 'logs/aquaPi.log' is relative
    config = copy.deepcopy(log_default)
    _make_log_dirs(config)
    assert (tmp_path / 'logs').is_dir()
    # what dictConfig() failed on ("Unable to configure handler 'file'"),
    # opened directly so the global logging setup stays untouched
    handler = logging.handlers.RotatingFileHandler(config['handlers']['file']['filename'])
    handler.close()
    assert (tmp_path / 'logs' / 'aquaPi.log').exists()


def test_handlers_without_file_are_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_log_dirs({'handlers': {'stdout': {'class': 'logging.StreamHandler'}}})
    assert list(tmp_path.iterdir()) == []
