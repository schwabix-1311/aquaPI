#!/usr/bin/env python3

import logging
import sys
import os
from os import path
from threading import Thread, Lock, Timer
from time import sleep

# not nice, but how else do you import a package from a git submodule?
sys.path.insert(1, path.join(os.path.dirname(os.path.abspath(__file__)),'tc420','tc420'))
from tc420 import TC420, PlayInitPacket, PlaySetChannels, ModeStopPacket, NoDeviceFoundError

from .base import (OutDriver, IoPort, PortFunc)

log = logging.getLogger('DriverTC420')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


# ========== PWM ==========


class DriverTC420(OutDriver):
    """ the popular 5-channel LED controller TC420/421
        connected via USB
    """
    # these are shared across all instances, as we can't send a single channel
    device = None
    channels = [0, 0, 0, 0, 0]
    _writer_lock = Lock()
    _writer_timer = None

    @staticmethod
    def find_ports():
        io_ports = {}
        try:
            DriverTC420.device = TC420()
            DriverTC420.device.time_sync()
            # cnt = 0
            for ch in range(1, 6):
                port_name = 'TC420 %d' % ch  # 'TC420 #%d %d % (cnt, ch)
                io_ports[port_name] = IoPort(PortFunc.Aout,
                                             DriverTC420,
                                             {'channel': ch},
                                             [])
                # cnt += 1
        except NoDeviceFoundError:
            # name: IoPort('function', 'driver', 'cfg', 'dependants')
            io_ports = {
                'TC420 1': IoPort(PortFunc.Aout, DriverTC420,
                                  {'channel': 1, 'fake': True}, []),
                'TC420 2': IoPort(PortFunc.Aout, DriverTC420,
                                  {'channel': 2, 'fake': True}, [])
            }
        return io_ports

    def __init__(self, cfg, func):
        super().__init__(cfg, func)
        # base Driver assumes !is_raspi() -> fake, this driver can do better!
        if not 'fake' in cfg:
            self._fake = False
        self._channel = int(cfg['channel'])

        self.name = 'TC420 %d' % (self._channel)
        if self._fake:
            self.name = '!' + self.name

        if not self._fake:
            log.debug('  PlayInitPacket %r', self)
            self.device.send(PlayInitPacket('aquaPi'))

        self.write(0)

    def close(self):
        if not self._fake:
            self.write('0')
            log.debug('  ModeStopPacket %r', self)
            self.device.send(ModeStopPacket())

    def write(self, value):
        log.info('%s -> %r', self.name, value)
        value = int(value + .9999)  if value else 0
        if not self._fake:
            with self._writer_lock:
                DriverTC420.channels[self._channel - 1] = value
            DriverTC420._writer()
        else:
            self._val = value

    @staticmethod
    def _writer():
        ''' TC420 aborts play mode after ~10sec without communication.
            This function writes and reschedules itself until cancelled.
        '''
        with DriverTC420._writer_lock:
            if DriverTC420._writer_timer:
                DriverTC420._writer_timer.cancel()

            log.debug('  PlaySetChannels %r', DriverTC420.channels)
            DriverTC420.device.send(PlaySetChannels(DriverTC420.channels))

            DriverTC420._writer_timer = Timer(9, DriverTC420._writer)
            DriverTC420._writer_timer.start()
