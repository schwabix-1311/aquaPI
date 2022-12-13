#!/usr/bin/env python3

import os
from os import path
import sys
from flask import Flask
import logging
# from logging.handlers import SMTPHandler


log = logging.getLogger('werkzeug')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


def create_app(test_config=None):
    logging.basicConfig(format='%(asctime)s %(levelname).3s %(name)s: %(message)s', datefmt='%I:%M:%S', stream=sys.stdout, level=logging.WARNING)

# TODO wrap in try/catch, but how should exceptions be handled?

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='ToDo during installation',   # TODO !!
        DATABASE=os.path.join(app.instance_path, 'aquaPi.sqlite'),
        CONFIG=os.path.join(app.instance_path, 'config.pickle')
    )
    if test_config:
        app.config.from_mapping(test_config)
    else:
        app.config.from_pyfile('config.py', silent=True)

    # FIXME: this would use app.debug before assignment
    # if False:
    #    mail_handler = SMTPHandler(
    #        mailhost='127.0.0.1',
    #        fromaddr='server-error@example.com',
    #        toaddrs=['admin@example.com'],
    #        subject='Application Error'
    #    )
    #    mail_handler.setLevel(logging.ERROR)
    #    mail_handler.setFormatter(logging.Formatter(
    #        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    #    ))
    #    if not app.debug:
    #        app.logger.addHandler(mail_handler)

    # in debug mode, app is restarted in a 2nd interpreter and thus we
    # duplicate all our threads, which then compete :-(
    # https://stackoverflow.com/questions/17552482/hook-when-flask-restarts-in-debug-mode
    import werkzeug
    if app.debug and not werkzeug.serving.is_running_from_reloader():
        return app

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db
    db.init_app(app)

    from .pages import home
    app.register_blueprint(home.bp)

    from .pages import settings
    app.register_blueprint(settings.bp)

    from .pages import config
    app.register_blueprint(config.bp)

    from .pages import about
    app.register_blueprint(about.bp)

    from . import api
    app.register_blueprint(api.bp)

    # from . import auth
    # app.register_blueprint(auth.bp)

    # from .hello import hello as hello_blueprint
    # app.register_blueprint(hello_blueprint)

    # Is there a better way? We won't start, so no reason to construct
    # and finally save the bus.
    if 'routes' in sys.argv:
        return app

    from . import machineroom
    app.machineroom = machineroom.init(app.config['CONFIG'])
    app.bus = app.machineroom.bus

    @app.context_processor
    def inject_globals():
        return dict(bus=app.bus)

    return app
