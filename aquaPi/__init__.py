#!/usr/bin/env python3

import os
from os import path
import sys
from flask import Flask
import logging
# from logging.handlers import SMTPHandler


log = logging.getLogger('werkzeug')

log.brief = log.warning  # alias, warning used as brief info, info is verbose
logging.addLevelName(logging.WARN, 'LOG')  # this makes log.warn kind of useless
# better:
#  logging.BRIEF = logging.INFO + 1
#  logging.addLevelName(logging.BRIEF, 'LOG')
#  log.brief = log.log( ...  need to implant a methods into logging for this
# or:
#  logging.VERBOSE = logging.INFO - 1
#  logging.addLevelName(logging.VERBOSE, 'LOG')
#  log.verbose = log.log( ...  need to implant a methods into logging for this

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)

#TODO remove sqlite completely
#TODO remove test_config & config.py, use ArgumentParser instead, see https://stackoverflow.com/questions/48346025/how-to-pass-an-arbitrary-argument-to-flask-through-app-run
# args:  -c "config"[.pickle]

def create_app(test_config=None):
    logging.basicConfig(format='%(asctime)s %(levelname).3s %(name)s: %(message)s'
                       , datefmt='%H:%M:%S', stream=sys.stdout, level=logging.WARNING)

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

    # in debug mode, app starts a 2nd instance and thus we
    # would duplicate all our threads, which then compete,  AVOID THIS!
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

    from . import api
    app.register_blueprint(api.bp)

    from .pages import home
    app.register_blueprint(home.bp)

    from .pages import settings
    app.register_blueprint(settings.bp)

    from .pages import config
    app.register_blueprint(config.bp)

    from .pages import about
    app.register_blueprint(about.bp)

    from .pages import spa
    app.register_blueprint(spa.bp)

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
