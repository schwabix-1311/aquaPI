#!/usr/bin/env python3
""" Tests for the app version shown on /about:
    - aquaPi/__init__.py: _read_app_version()
"""

import os

from aquaPi import _read_app_version


def test_read_app_version_missing_file_returns_dev(tmp_path):
    assert _read_app_version(str(tmp_path)) == 'dev'


def test_read_app_version_reads_and_strips_file(tmp_path):
    with open(os.path.join(tmp_path, 'VERSION'), 'w', encoding='utf8') as f:
        f.write('v1.2.3\n')

    assert _read_app_version(str(tmp_path)) == 'v1.2.3'
