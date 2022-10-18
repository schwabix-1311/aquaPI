#!/usr/bin/env python3

import logging
import importlib.util
import sys
import os
from os import path
import glob

from .base import *


log = logging.getLogger('Driver Base')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== IoRegistry is a singleton -> 1 global isntance ==========


DRIVER_FILE_PREFIX = 'Driver'
CUSTOM_DRIVERS = 'CustomDrivers'

# import all files named Driver*,py into our package, icluding a subfolder CustomDrivers
__path__.append(path.join(__path__[0], CUSTOM_DRIVERS))

for drv_path in __path__:
    for drv_file in glob.glob(path.join(drv_path, DRIVER_FILE_PREFIX + '*.py')):
        log.debug('Found driver file ' + drv_file)

        drv_name = path.basename(drv_file).removeprefix(DRIVER_FILE_PREFIX).removesuffix('.py')
        drv_name = __name__ + '.' + drv_name.lower()
        drv_spec = importlib.util.spec_from_file_location(drv_name, drv_file)
        log.debug('Driver spec ' + str(drv_spec))

        drv_mod = importlib.util.module_from_spec(drv_spec)
        log.debug('Driver module ' + str(drv_mod))

        sys.modules[drv_name] = drv_mod
        drv_spec.loader.exec_module(drv_mod)


io_registry = IoRegistry()
