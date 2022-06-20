#!/usr/bin/env python

import os
import sys
from flask import Flask
import logging
#from logging.handlers import SMTPHandler


def create_app(test_config=None):
    logging.basicConfig(format='%(asctime)s %(levelname).3s %(name)s: %(message)s', datefmt='%I:%M:%S', stream=sys.stdout, level=logging.WARNING)
    if False:    #FIXME: using app.debug before assignment
        mail_handler = SMTPHandler(
            mailhost='127.0.0.1',
            fromaddr='server-error@example.com',
            toaddrs=['admin@example.com'],
            subject='Application Error'
        )
        mail_handler.setLevel(logging.ERROR)
        mail_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        ))
        if not app.debug:
            app.logger.addHandler(mail_handler)

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='ToDo during installation',   #TODO !!
        DATABASE=os.path.join(app.instance_path, 'aquaPI.sqlite'),
    )
    if test_config:
        app.config.from_mapping(test_config)
    else:
        app.config.from_pyfile('config.py', silent=True)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db
    db.init_app(app)

    from . import backend
    be = backend.BackEnd(app.config)
    app.broker = be.broker

    from . import dash
    app.register_blueprint(dash.bp)

    from . import config
    app.register_blueprint(config.bp)

    from . import about
    app.register_blueprint(about.bp)

    #from . import auth
    #app.register_blueprint(auth.bp)

    #from .hello import hello as hello_blueprint
    #app.register_blueprint(hello_blueprint)

    return app
