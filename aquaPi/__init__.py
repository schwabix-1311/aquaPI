#!/usr/bin/env python3

import os
from os import path
import sys
from flask import Flask

import json
import logging.config
import logging.handlers
# from logging.handlers import SMTPHandler


log = logging.getLogger('aquaPi')


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

# this is a json string to make it a template for log_config.json
log_default = {
  "version": 1,
  "disable_existing_loggers": False,
  "formatters": {
    "simple": {
      "format": "%(asctime)s %(levelname).3s %(name)s: %(message)s",
      "datefmt": "%H:%M:%S"
    }
  },
  "handlers": {
    "stdout": {
      "class": "logging.StreamHandler",
      "level": "INFO",
      "formatter": "simple",
      "stream": "ext://sys.stdout"
    },
    "file": {
      "class": "logging.handlers.RotatingFileHandler",
      "level": "WARNING",
      "formatter": "simple",
      "filename": "logs/aquaPi.log",
      "maxBytes": 1000000,
      "backupCount": 3
    }
  },
  "loggers": {
    "root": {
      "level": "WARNING",
      "handlers": ["stdout","file"]
    },

    "aquaPi":     {"level": "NOTSET"},
    #"aquaPi.api": {"level": "NOTSET"},

    "machineroom":             {"level": "NOTSET"},
    #"machineroom.alert_nodes": {"level": "NOTSET"},
    #"machineroom.aux_nodes":   {"level": "NOTSET"},
    #"machineroom.ctrl_nodes":  {"level": "NOTSET"},
    #"machineroom.hist_nodes":  {"level": "NOTSET"},
    #"machineroom.in_nodes":    {"level": "NOTSET"},
    #"machineroom.msg_bus":     {"level": "NOTSET"},
    #"machineroom.msg_types":   {"level": "NOTSET"},
    #"machineroom.out_nodes":   {"level": "NOTSET"},

    "driver":               {"level": "NOTSET"},
    #"driver.base":          {"level": "NOTSET"},
    #"driver.DriverADC":     {"level": "NOTSET"},
    #"driver.DriverAlert":   {"level": "NOTSET"},
    #"driver.DriverGPIO":    {"level": "NOTSET"},
    #"driver.DriverOneWire": {"level": "NOTSET"},
    #"driver.DriverPWM":     {"level": "NOTSET"},
    #"driver.DriverTC420":   {"level": "NOTSET"},

    "pages":          {"level": "NOTSET"},
    #"pages.about":    {"level": "NOTSET"},
    #"pages.config":   {"level": "NOTSET"},
    #"pages.home":     {"level": "NOTSET"},
    #"pages.settings": {"level": "NOTSET"},
    #"pages.spa":      {"level": "NOTSET"},
    #"pages.sse_util": {"level": "NOTSET"},

    "werkzeug": {
      "comment": "werkzeug is noisy, reduce to >=WARNING, INFO shows all https requests",
      "level": "WARNING",
      "propagate": False
    }
  }
}



def create_app():
    # TODO wrap in try/catch, but how should exceptions be handled?
    app = Flask(__name__, instance_relative_config=True)

    config_file = path.join(app.instance_path, "log_config.json")
    if path.exists(config_file):
        with open(config_file) as f_in:
            log_config = json.load(f_in)
    else:
        log_config = log_default
    logging.config.dictConfig(log_config)

    logging.warning("Press CTRL+C to quit")
    log.brief("... und los geht's")

    # no luck with command line parsing:
    # 1. Flask uses "click", which conflicts with the simple argparse
    # 2. click is complex, I simply didn't succeed to add options to Flask's command groups
    # for now use env. vars instead
    try:
        cfg_file = os.environ['AQUAPI_CFG']
    except KeyError:
        cfg_file = 'config.pickle'

    app.config.from_mapping(
        SECRET_KEY='ToDo during installation',   # TODO !!
        CONFIG=os.path.join(app.instance_path, cfg_file)
    )

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
