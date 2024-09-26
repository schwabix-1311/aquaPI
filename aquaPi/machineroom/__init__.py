#!/usr/bin/env python3

import logging
from os import path
import pickle
import atexit

from .msg_bus import MsgBus, BusRole
from .ctrl_nodes import MinimumCtrl, MaximumCtrl, SunCtrl, FadeCtrl
from .in_nodes import AnalogInput, ScheduleInput
from .out_nodes import SwitchDevice, AnalogDevice
from .aux_nodes import ScaleAux, MinAux, MaxAux, AvgAux
from .hist_nodes import History
from .alert_nodes import Alert, AlertAbove, AlertBelow


log = logging.getLogger('MachineRoom')
log.brief = log.warning  # alias, warning used as brief info, info is verbose

log.setLevel(logging.WARNING)
# log.setLevel(logging.INFO)
# log.setLevel(logging.DEBUG)


mr = None


def init(storage):
    global mr  # pylint: disable=W0603

    mr = MachineRoom(storage)
    return mr


# This is brute force, as a destructor AKA __del__ is not called after Ctrl-C.
# However, the concept of shutting down a web server by app code is a no-no.
# A development server might allow this, but this was removed from werkzeug
# with v2.1. Instead, I could crete a route /flush and a button (debug-only).
# This should save_nodes and bring all nodes to a safe state, e.g. heater OFF
# Seen as an appliance aquaPi should somehow allow a restart for updates,
# or to recover SW state

@atexit.register
def cleanup():
    log.brief('Preparing shutdown ...')
    if mr and mr.bus:
        # this does not work completely, teardown aborts half-way.
        # My theory: we run multi-threaded as a daemon and have only
        # limited time until we're killed.
        mr.save_nodes(mr.bus)
        mr.bus.teardown()
        mr.bus = None


class MachineRoom:
    """ The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        The Bus also provides the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    """

    def __init__(self, bus_storage):
        """ Create everything needed to get the machinery going.
            So far the only thing here is the bus.
        """
        self.bus_storage = bus_storage

        if not path.exists(self.bus_storage):
            self.bus = MsgBus()  # threaded=True)

            log.brief("=== There are no controllers defined, creating default")
            self.create_default_nodes()
            self.save_nodes(self.bus)
            log.brief("=== Successfully created Bus and default Nodes")
            log.brief("  ... and saved to %s", self.bus_storage)

        else:
            log.brief("=== Loading Bus & Nodes from %s", self.bus_storage)
            self.bus = self.restore_nodes()

        log.brief("%s", str(self.bus))
        log.info(self.bus.get_nodes())

    def save_nodes(self, container, fname=None):
        """ save the Bus, Nodes and Drivers to storage
            Parameters allow usage for controller templates,
            contained in "something", not a bus
        """
        if container:
            if not fname:
                fname = self.bus_storage
            with open(fname, 'wb') as p:
                pickle.dump(container, p, protocol=pickle.HIGHEST_PROTOCOL)

    def restore_nodes(self, fname=None):
        """ recreate the Bus, Nodes and Drivers from storage,
            or a controller template in a container from some file
        """
        if not fname:
            fname = self.bus_storage
        with open(fname, 'rb') as p:
            container = pickle.load(p)
        return container

    def create_default_nodes(self):
        """ "let there be light" and heating of course, what
            else do my fish(es) need?
            Distraction: interesting fact on English:
              "fish" is plural, "fishes" is several species of fish
        """
        REAL_CONFIG = True  #False  # this disables the other test configs

        TEST_ALERT = False  #True

        TEST_PH = False  #True

        SIM_LIGHT = True
        DAWN_LIGHT = SIM_LIGHT and False  # True

        SIM_TEMP = False  #True
        COMPLEX_TEMP = SIM_TEMP and True

        if REAL_CONFIG:
            # single PWM dimmed LED bar, perceptive correction
            light_schedule = ScheduleInput('Zeitplan Licht', '* 14-21 * * *')

            # ... with linear dawn & dusk for 15mins
            # light_c = FadeCtrl('Beleuchtung', light_schedule.id,
            #                    fade_time=15 * 60)

            # ... with "realistic" dawn & dusk for 1h each
            light_c = SunCtrl('Beleuchtung', light_schedule.id, xscend=1.0)

            light_pwm = AnalogDevice('Dimmer', light_c.id,
                                     'PWM 0', percept=1, maximum=85)
            light_schedule.plugin(self.bus)
            light_c.plugin(self.bus)
            light_pwm.plugin(self.bus)

            # ... and history for a diagram
            history = History('Licht',
                              [light_schedule.id, light_c.id]) #, light_pwm.id])
            history.plugin(self.bus)

            # single water temp sensor, switched relay
            wasser_i = AnalogInput('Wasser', 'DS1820 xA2E9C', 25.0, '°C',
                                   avg=3, interval=30)
            wasser = MinimumCtrl('Temperatur', wasser_i.id, 25.0)
            wasser_o = SwitchDevice('Heizstab', wasser.id,
                                    'GPIO 12 out', inverted=1)
            wasser_i.plugin(self.bus)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)

            # air temperature, just for the diagram
            wasser_i2 = AnalogInput('Wasser 2', 'DS1820 x7A71E', 25.0, '°C',
                                    avg=2, interval=60)
            wasser_i2.plugin(self.bus)

            # fancy: if water temp >26 a cooling fan spins dynamically up
            coolspeed = ScaleAux('Lüftergeschwindigkeit', wasser_i.id, '%',
                                 limit=True,
                                 points=[(26.0, 0), (28.0, 100)])
            cool = AnalogDevice('Lüfter', coolspeed.id,
                                'PWM 1', minimum=10, maximum=80)
            cool.plugin(self.bus)
            coolspeed.plugin(self.bus)

            # ... and history for a diagram
            t_history = History('Temperaturen',
                                [wasser_i.id, wasser_i2.id,
                                 wasser.id, #wasser_o.id,
                                 coolspeed.id]) #, cool.id])
            t_history.plugin(self.bus)

            adc_ph = AnalogInput('pH Sonde', 'ADC #1 in 3', 2.49, 'V',
                                 avg=3, interval=30)
            calib_ph = ScaleAux('pH Kalibrierung', adc_ph.id, 'pH',
                                points=[(2.99, 4.0), (2.51, 6.9)])
            ph = MaximumCtrl('pH', calib_ph.id, 6.7)

            ph_broken = True
            if ph_broken:
                # WAR broken CO2 vent:
                # open/close repeatedly, as CO2 only flows when partially opened
                ph_ticker = ScheduleInput('pH Blinker', '* * * * * */15')
                ph_ticker_or = MinAux('pH Toggle', [ph.id, ph_ticker.id])
                out_ph = SwitchDevice('CO2 Ventil', ph_ticker_or.id, 'GPIO 20 out')
            else:
                out_ph = SwitchDevice('CO2 Ventil', ph.id, 'GPIO 20 out')
            out_ph.plugin(self.bus)
            ph.plugin(self.bus)
            if ph_broken:
                ph_ticker_or.plugin(self.bus)
                ph_ticker.plugin(self.bus)
            calib_ph.plugin(self.bus)
            adc_ph.plugin(self.bus)

            # ... and history for a diagram
            ph_history = History('pH Verlauf',
                                 [adc_ph.id, calib_ph.id, ph.id])  #, out_ph.id])
            ph_history.plugin(self.bus)
            return

        if TEST_PH:
            adc_ph = AnalogInput('pH Sonde', 'ADC #1 in 3', 2.49, 'V',
                                 avg=1, interval=30)
            calib_ph = ScaleAux('pH Kalibrierung', adc_ph.id, 'pH',
                                points=[(2.99, 4.0), (2.51, 6.9)])
            ph = MaximumCtrl('pH', calib_ph.id, 7.0)
            out_ph = SwitchDevice('CO2 Ventil', ph.id, 'GPIO 20 out')
            out_ph.plugin(self.bus)
            ph.plugin(self.bus)
            calib_ph.plugin(self.bus)
            adc_ph.plugin(self.bus)
            ph_history = History('pH Verlauf',
                                 [adc_ph.id, calib_ph.id, ph.id, out_ph.id])
            ph_history.plugin(self.bus)

        if SIM_LIGHT:
            light_schedule = ScheduleInput('Zeitplan 1', '* 10/2 * * *')
            light_schedule.plugin(self.bus)
            # light_c = FadeCtrl('Beleuchtung', light_schedule.id,
            #                    fade_time=30 * 60)  # 30*60)
            light_c = SunCtrl('Beleuchtung', light_schedule.id, xscend=.2)
            light_c.plugin(self.bus)
            if not DAWN_LIGHT:
                light_pwm = AnalogDevice('Dimmer', light_c.id,
                                         #'PWM 0', percept=True, maximum=80)
                                         'TC420 #1 CH1', percept=True, maximum=80)
                light_pwm.plugin(self.bus)

                history = History('Licht',
                                  [light_schedule.id,
                                   light_c.id, light_pwm.id])
                history.plugin(self.bus)
            else:
                dawn_schedule = ScheduleInput('Zeitplan 2', '* 22 * * *')
                dawn_schedule.plugin(self.bus)
                dawn_c = FadeCtrl('Dämmerlicht', dawn_schedule.id,
                                  fade_time=30 * 60)
                dawn_c.plugin(self.bus)

                light_max = MaxAux('Max Licht', [light_c.id, dawn_c.id])
                light_max.plugin(self.bus)
                light_pwm = AnalogDevice('Dimmer', light_max.id,
                                         'PWM 0', percept=True, maximum=80)
                light_pwm.plugin(self.bus)

                history = History('Licht',
                                  [light_schedule.id, dawn_schedule.id,
                                   light_c.id, dawn_c.id, light_pwm.id])
                history.plugin(self.bus)

        if SIM_TEMP:
            if not COMPLEX_TEMP:
                # single temp sensor -> temp ctrl -> relay
                wasser_i = AnalogInput('Wasser', 'DS1820 xA2E9C', 25.0, '°C')
                wasser = MinimumCtrl('Temperatur', wasser_i.id, 25.0)
                wasser_o = SwitchDevice('Heizstab', wasser.id, 'GPIO 12 out')
                wasser.plugin(self.bus)
                wasser_o.plugin(self.bus)
                wasser_i.plugin(self.bus)

            else:
                # 2 temp sensors -> average -> temp ctrl -> relay
                w1_temp = AnalogInput('T-Sensor 1', 'DS1820 xA2E9C', 25.0, '°C')
                w1_temp.plugin(self.bus)

                w2_temp = AnalogInput('T-Sensor 2', 'DS1820 x7A71E', 25.0, '°C')
                w2_temp.plugin(self.bus)

                w_temp = AvgAux('T-Mittel', [w1_temp.id, w2_temp.id])
                w_temp.plugin(self.bus)

                w1_ctrl = MinimumCtrl('W-Heizung', w_temp.id, 25.0)
                w1_ctrl.plugin(self.bus)

                w2_ctrl = MaximumCtrl('W-Kühlung', w2_temp.id, 26.5)
                w2_ctrl.plugin(self.bus)

                w_heat = SwitchDevice('W-Heizer', w1_ctrl.id, 'GPIO 12 out')
                w_heat.plugin(self.bus)

                #FIXME: a node chain like this one has no *Ctrl and is thus
                #       invisible in UI, although totally valid
                w_coolspeed = ScaleAux('Lüftergeschwindigkeit', w_temp.id, '%',
                                       limit=True,
                                       points=[(25.1, 0), (26, 100)])
                w_cool = AnalogDevice('W-Lüfter', w_coolspeed.id,
                                      'PWM 1')  # ?? minimum=10, maximum=80)
                w_cool.plugin(self.bus)
                w_coolspeed.plugin(self.bus)

                t_history = History('Temperaturen',
                                    [w1_temp.id, w2_temp.id, w_temp.id,
                                     w_heat.id, w_cool.id])
                t_history.plugin(self.bus)

        if TEST_ALERT:
            led_alert = Alert('Alert LED',
                              [AlertAbove(calib_ph.id, 7.2), AlertBelow(calib_ph.id, 6.8)],
                              'GPIO 1 out')
            led_alert.plugin(self.bus)
            mail_alert = Alert('Alert Mail',
                              [AlertAbove(w_temp.id, 26.0), AlertBelow(w_temp.id, 23.0)],
                              'GPIO 0 out')  #TEMP, no drivers for email/Telegram yet
            mail_alert.plugin(self.bus)
