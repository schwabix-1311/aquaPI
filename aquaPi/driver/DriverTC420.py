#!/usr/bin/env python3

import logging
import sys
import os
from os import path
from threading import Lock, Timer

# not nice, but how else do you import a package from a git submodule?
sys.path.insert(1, path.join(os.path.dirname(os.path.abspath(__file__)),'tc420','tc420'))
from tc420 import TC420, PlayInitPacket, PlaySetChannels, ModeStopPacket, NoDeviceFoundError

from .base import (OutDriver, IoPort, PortFunc)


log = logging.getLogger('driver.DriverTC420')
log.brief = log.warning  # alias, warning is used as brief info, level info is verbose


# ========== PWM ==========


class DriverTC420(OutDriver):
    """ the popular 5-channel LED controller TC420/421
        connected via USB - no clue whether it could be driven via WiFi
    """
    devices = []   # each entry is a tupel: (TC420, [o1,o2,o3,o4,o5])
    _writer_lock = Lock()
    _writer_timer = None

    @staticmethod
    def find_ports():
        io_ports = {}
        try:
            idx = 0
            while True:
                tc = TC420(dev_index=idx)
                tc.time_sync()
                #DriverTC420.devices[idx] = (tc, [0, 0, 0, 0, 0])
                DriverTC420.devices.append((tc, [0, 0, 0, 0, 0]))
                for ch in range(1, 6):
                    port_name = f'TC420 #{idx + 1} CH{ch}'
                    io_ports[port_name] = IoPort(PortFunc.Aout,
                                                 DriverTC420,
                                                 {'device': idx, 'channel': ch},
                                                 [])
                idx += 1
        except NoDeviceFoundError:
            if idx == 0:  # fake when no TC420 found
                io_ports = {
                    'TC420 #1 CH1': IoPort(PortFunc.Aout, DriverTC420,
                                           {'device': 0, 'channel': 1, 'fake': True}, []),
                    'TC420 #1 CH2': IoPort(PortFunc.Aout, DriverTC420,
                                           {'device': 0, 'channel': 2, 'fake': True}, [])
                }
        return io_ports

    def __init__(self, cfg, func):
        super().__init__(cfg, func)
        # class Driver assumes !is_raspi() -> fake, this driver can do better!
        if not 'fake' in cfg:
            self._fake = False
        self._idx = int(cfg['device'])
        self._channel = int(cfg['channel'])

        self.name = f'TC420 #{self._idx} CH{self._channel}'
        if self._fake:
            self.name = '!' + self.name

        if not self._fake:
            log.debug('  PlayInitPacket %r' , self)
            tc =  DriverTC420.devices[self._idx][0]
            tc.send(PlayInitPacket('aquaPi'))

        self.write(0)

    def close(self):
        if not self._fake:
            self.write('0')
            log.debug('  ModeStopPacket %r', self)
            tc =  DriverTC420.devices[self._idx][0]
            tc.send(ModeStopPacket())

    def write(self, value):
        log.info('%s -> %r', self.name, value)
        value = int(value + .9999)  if value else 0  # lowest dim value -> 1%
        if not self._fake:
            with self._writer_lock:
                tc_out =  DriverTC420.devices[self._idx][1]
                tc_out[self._channel - 1] = value
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

            idx = 0
            for device in DriverTC420.devices:
                log.debug('  PlaySetChannels #%d: %r', idx + 1, device[1])
                device[0].send(PlaySetChannels(device[1]))
                idx += 1

            DriverTC420._writer_timer = Timer(9, DriverTC420._writer)
            DriverTC420._writer_timer.start()
