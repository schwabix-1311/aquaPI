#!/usr/bin/env python3
""" Tests for GET /api/ (api_index): the self-documenting route list,
    returned as JSON by default and as a human-readable HTML page when
    a browser's Accept header asks for text/html.
"""

import os
from html import escape
from http import HTTPStatus

import pytest
from flask import Flask

import aquaPi
from aquaPi import auth, api
from aquaPi.api import _api_group_label
from aquaPi.driver import create_io_registry
from aquaPi.machineroom.msg_bus import MsgBus


_TEMPLATE_FOLDER = os.path.join(os.path.dirname(aquaPi.__file__), 'templates')


@pytest.fixture(autouse=True, scope='session')
def _io_registry():
    create_io_registry()


@pytest.fixture
def bus():
    bus = MsgBus(threaded=False)
    yield bus
    bus.teardown()


class _FakeMachineRoom:
    def __init__(self, bus: MsgBus):
        self.bus = bus


@pytest.fixture
def app(tmp_path, bus):
    app = Flask(__name__, template_folder=_TEMPLATE_FOLDER)
    app.config['INSTANCE_PATH'] = str(tmp_path)
    app.config['TESTING'] = True

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)
    app.extensions['machineroom'] = _FakeMachineRoom(bus)

    @app.route('/', endpoint='spa.spa')
    def spa_stub():
        return 'spa'

    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_default_accept_returns_json(client):
    # no session at all still auto-logs-in as the reserved anonymous
    # viewer account (see auth.py's before_request hook), satisfying
    # this route's plain @login_required
    resp = client.get('/api/')
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type.startswith('application/json')

    routes = resp.get_json()
    assert isinstance(routes, list)
    assert any(r['path'] == '/api/nodes/' for r in routes)


def test_explicit_json_accept_returns_json(client):
    resp = client.get('/api/', headers={'Accept': 'application/json'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type.startswith('application/json')


def test_html_accept_returns_human_readable_page(client):
    resp = client.get('/api/', headers={'Accept': 'text/html'})
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type.startswith('text/html')

    body = resp.get_data(as_text=True)
    assert '<table' in body
    assert '/api/users/me' in body


def test_html_and_json_list_the_same_routes(client):
    json_routes = {r['path'] for r in client.get('/api/').get_json()}
    html_body = client.get('/api/', headers={'Accept': 'text/html'}).get_data(as_text=True)
    for route_path in json_routes:
        assert escape(route_path) in html_body


def test_html_groups_routes_under_section_headers(client):
    body = client.get('/api/', headers={'Accept': 'text/html'}).get_data(as_text=True)
    assert 'User management' in body
    assert body.index('User management') < body.index('/api/users/me')


def test_group_label_known_segment_uses_friendly_name():
    assert _api_group_label('/api/users/<int:user_id>') == 'User management'


def test_group_label_unknown_segment_falls_back_to_title_case():
    assert _api_group_label('/api/some-new-thing/') == 'Some New Thing'
