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
      "handlers": ["stdout", "file"]
    },

    # the following list should occasionally be synced
    # with the result of 'grep logging.getLogger $(git ls-files *.py)'

    "aquaPi":     {"level": "NOTSET"},
    # "aquaPi.api":  {"level": "NOTSET"},
    # "aquaPi.auth": {"level": "NOTSET"},
    # "aquaPi.db":   {"level": "NOTSET"},

    "machineroom":             {"level": "NOTSET"},
    # "machineroom.alert_nodes": {"level": "NOTSET"},
    # "machineroom.aux_nodes":   {"level": "NOTSET"},
    # "machineroom.ctrl_nodes":  {"level": "NOTSET"},
    # "machineroom.hist_nodes":  {"level": "NOTSET"},
    # "machineroom.in_nodes":    {"level": "NOTSET"},
    # "machineroom.msg_bus":     {"level": "NOTSET"},
    # "machineroom.msg_types":   {"level": "NOTSET"},
    # "machineroom.out_nodes":   {"level": "NOTSET"},

    "driver":               {"level": "NOTSET"},
    # "driver.base":          {"level": "NOTSET"},
    # "driver.DriverADC":     {"level": "NOTSET"},
    # "driver.DriverGPIO":    {"level": "NOTSET"},
    # "driver.DriverOneWire": {"level": "NOTSET"},
    # "driver.DriverPWM":     {"level": "NOTSET"},
    # "driver.DriverTC420":   {"level": "NOTSET"},
    # "driver.DriverText":    {"level": "NOTSET"},

    "pages":          {"level": "NOTSET"},
    # "pages.spa":      {"level": "NOTSET"},
    # "pages.sse_util": {"level": "NOTSET"},

    "werkzeug": {
      "comment": "werkzeug is noisy, reduce to >=WARNING, INFO shows all https requests. propagate must stay True, else even WARNING+ never reaches any handler (root's) - found 2026-08-09 while diagnosing a dbg startup hang, where this had silenced werkzeug completely",
      "level": "WARNING",
      "propagate": True
    }
  }
}


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY='ToDo during installation',   # TODO !!
        INSTANCE_PATH=app.instance_path,
        APP_NAME='aquaPi',
    )

    # in debug mode, app starts a 2nd instance and thus we
    # would duplicate all our threads, which then compete,  AVOID THIS!
    # https://stackoverflow.com/questions/17552482/hook-when-flask-restarts-in-debug-mode
    import werkzeug
    if app.debug and not werkzeug.serving.is_running_from_reloader():
        return app

    # Is there a better way? We won't start, so no reason to construct
    # and finally save the bus.
    if 'routes' in sys.argv:
        return app

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    logcfg_file = path.join(app.instance_path, "log_config.json")
    if path.exists(logcfg_file):
        with open(logcfg_file, 'r', encoding='ascii') as f_in:
            log_config = json.load(f_in)
    else:
        log_config = log_default
    logging.config.dictConfig(log_config)

    logging.warning("Press CTRL+C to quit")

    from . import auth
    auth.init_app(app)

    from .machineroom import MachineRoom
    try:
        app.extensions['machineroom'] = MachineRoom(app.config)
    except Exception:
        log.exception('Oops')
        log.fatal("Fatal error in App.__init__. Subsequent errors are a side effect.")
        return None

    app.register_blueprint(auth.bp)

    from . import api
    app.register_blueprint(api.bp)

    from .pages import spa
    app.register_blueprint(spa.bp)

    return app
