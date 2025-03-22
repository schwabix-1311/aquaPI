#!/usr/bin/env python3

import logging
from os import (environ, path)
import json
import pickle
import atexit

from .msg_bus import MsgBus
from .ctrl_nodes import MinimumCtrl, MaximumCtrl, PidCtrl, SunCtrl, FadeCtrl
from .in_nodes import AnalogInput, ScheduleInput
from .out_nodes import SwitchDevice, SlowPwmDevice, AnalogDevice
from .aux_nodes import ScaleAux, MinAux, MaxAux, AvgAux
from .hist_nodes import History
from .alert_nodes import Alert, AlertAbove, AlertBelow
from ..driver import (driver_config, create_io_registry, DriverError)


log = logging.getLogger('machineroom')
log.brief = log.warning  # alias, warning used as brief info, info is verbose


class MachineRoom:
    """ The Machine Room
        The core is a message bus, on which different sensors,
        controllers, devices and auxiliary nodes communicate.
        The Bus also provides the interface to Flask backend.
        Some bus nodes start worker threads (e.g. sensors), the rest
        works in msg handlers and callbacks.
    """

    def __init__(self, global_cfg: dict[str, str]) -> None:
        """ Create everything needed to get the machinery going:
            the Bus, global config and the IoRegistry for drivers
        """
        self.globals = global_cfg
        instance_path = global_cfg['INSTANCE_PATH']

        # merge customized config from this file
        cfg_file = 'config.json'
        if 'AQUAPI_CFG' in environ:
            cfg_file = environ['AQUAPI_CFG']
        cfg_file = path.join(instance_path, cfg_file)

        if path.exists(cfg_file):
            with open(cfg_file, 'r', encoding='utf8') as f_in:
                custom_cfg = json.load(f_in)
            self.globals.update(custom_cfg)

        topo_file = 'topo.pickle'
        if 'AQUAPI_TOPO' in environ:
            topo_file = environ['AQUAPI_TOPO']
        topo_file = path.join(instance_path, topo_file)

        self.globals['CUSTOM_CFG'] = cfg_file
        self.globals['BUS_TOPO'] = topo_file

        if 'Email' in self.globals:
            driver_config['Email'] = self.globals['Email']
        if 'Telegram' in self.globals:
            driver_config['Telegram'] = self.globals['Telegram']
        create_io_registry()

        try:
            if not path.exists(self.globals['BUS_TOPO']):
                self.bus: MsgBus = MsgBus(threaded=False)

                log.brief("=== There are no controllers defined, creating default")

# this constructs all nodes contained in this file, including all side effects of
# construction such as port driver creation, just it isn't plugged in yet
#                with open('phsteuerung.chain', 'r', encoding='utf8') as p:
#                    ch = jsonpickle.loads(p.read())
#                breakpoint()
#                print(ch)

                self.create_default_nodes()
                self.save_nodes(self.bus)

# thoughts on chains:
# - could have a couple of jsonpickeled chain files
# - before decoding them (instantiate by loads), the file contents could run through a
#   parser, interactively filling in variables
# - with appropriate variable syntax the parser could offer choices from appropriate types or data from the live system
# - should go through all possible variables to learn requirements
# - same parser could later be used to pre-select choices of a nicer API

                # instead iterate with bus.get_nodes().intersect(chain) until empty?
#                for c in self.bus.get_nodes(BusRole.CTRL):
#                    chain = {c}
#                    chain |= {rcv for rcv in c.get_receives(True)}
#                    chain |= {lst for lst in c.get_listeners(True)}
#                    with open(c.id + '.chain', 'w', encoding='utf8') as p:
#                        p.write(jsonpickle.dumps(chain, indent=2))

                log.brief("=== Successfully created Bus and default Nodes")
                log.brief("  ... and saved to %s", self.globals['BUS_TOPO'])

            else:
                log.brief("=== Loading Bus & Nodes from %s", self.globals['BUS_TOPO'])
                self.bus = self.restore_nodes()

        except DriverError as ex:
            log.fatal("Creation of a controller failed: %s", ex.msg)
            raise

        # Our __del__ would not be called after Ctrl-C.
        atexit.register(self.shutdown)

        log.brief("%s", str(self.bus))
        if self.bus:
            log.info(self.bus.get_nodes())

    def shutdown(self) -> None:
        """ Prepare for shutdown, save bus state etc.
        """
        log.brief('Preparing shutdown ...')

        # write changed data (onyl our!) back to self.globals['CUSTOM_CFG']
        # thus, load from file, update our dynamic keys, then write back
        custom_cfg: dict[str, str] = {}
        cfg_file = self.globals['CUSTOM_CFG']
        if path.exists(cfg_file):
            with open(cfg_file, 'r', encoding='utf8') as f_in:
                custom_cfg = json.load(f_in)
        # if 'Email' in custom_cfg:
        #     for idx in range(len(custom_cfg['Email'])):
        #         custom_cfg['Email'][idx].update(self.globals['Email'][idx])
        if 'Telegram' in custom_cfg:
            for idx in range(len(custom_cfg['Telegram'])):
                custom_cfg['Telegram'][idx].update(self.globals['Telegram'][idx])
        if custom_cfg:
            with open(cfg_file, 'w', encoding='utf8') as p:
                p.write(json.dumps(custom_cfg, indent=2))

        if self.bus:
            self.save_nodes(self.bus)
            self.bus.teardown()
            # self.bus = None
            log.brief('... shutdown completed')

    def save_nodes(self, container, fname: str = '') -> None:
        """ save the Bus, Nodes and Drivers to storage
            Parameters allow usage for controller templates,
            contained in "something", not a bus
        """
        if container:
            if not fname:
                fname = self.globals['BUS_TOPO']
            with open(fname, 'wb') as p:
                pickle.dump(container, p, protocol=pickle.HIGHEST_PROTOCOL)

    def restore_nodes(self, fname: str = ''):
        """ recreate the Bus, Nodes and Drivers from storage,
            or a controller template in a container from some file
        """
        if not fname:
            fname = self.globals['BUS_TOPO']
        with open(fname, 'rb') as p:
            container = pickle.load(p)
        return container

    def create_default_nodes(self) -> None:
        """ "let there be light" and heating of course, what
            else do my fish(es) need?
            Distraction: interesting fact about English:
              "fish" is plural, "fishes" are several species of fish
        """
        REAL_CONFIG = True  # this disables the other test configs
        # REAL_CONFIG = False

        TEST_ALERT = True
        TEST_PH = TEST_ALERT or False  # True
        SIM_LIGHT = False  # True
        DAWN_LIGHT = SIM_LIGHT and False  # True
        SIM_TEMP = False  # True
        COMPLEX_TEMP = SIM_TEMP and False

        if REAL_CONFIG:
            # __Lighting__ #
            # single PWM dimmed LED bar, perceptive correction
            light_schedule = ScheduleInput('Zeitplan Licht', '* 14-21 * * *')

            # ... with linear dawn & dusk for 15mins
            # light_c = FadeCtrl('Beleuchtung', light_schedule.id,
            #                    fade_time=15 * 60)

            # ... with "realistic" dawn & dusk for 1h each
            light_c = SunCtrl('Licht', light_schedule.id, xscend=1.0)

            light_pwm = AnalogDevice('Dimmer', light_c.id,
                                     'PWM 0', percept=True, maximum=75)
            light_schedule.plugin(self.bus)
            light_c.plugin(self.bus)
            light_pwm.plugin(self.bus)

            # ... and history for a diagram
            history = History('Beleuchtung',
                              [light_schedule.id, light_c.id])  # , light_pwm.id])
            history.plugin(self.bus)

            # __Temperatures__ #
            # single water temp sensor
            # 2-point switched relay or triac ...
            # wasser_i1 = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C',
            #                         avg=1, interval=60)
            # wasser = MinimumCtrl('Temperatur', wasser_i1.id, 25.0)
            # wasser_o = SwitchDevice('Heizstab', wasser.id,
            #                         'GPIO 12 out', inverted=False)

            # ... or PID driven triac (relay has increased wear, not recomm.)
            # PID for my 60cm/100W: sensor cycle 300s, PID 1.0/0.05/5, PWM 10s
            wasser_i1 = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C',
                                    avg=1, interval=300)
            wasser = PidCtrl('Heizleistung', wasser_i1.id, 25.0,
                             p_fact=1.1, i_fact=0.07, d_fact=0.0)
            wasser_o = SlowPwmDevice('Heizstab', wasser.id,
                                     'GPIO 12 out', inverted=False, cycle=10)
            wasser_i1.plugin(self.bus)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)

            # air temperature, just for the diagram
            wasser_i2 = AnalogInput('Raumluft', 'DS1820 #2', 25.0, '°C',
                                    avg=2, interval=60)
            wasser_i2.plugin(self.bus)

            # fancy: if water temp >26 a cooling fan spins dynamically up
            coolspeed = ScaleAux('Lüftersteuerung', wasser_i1.id, '%',
                                 points=[(26.0, 0), (28.0, 100)])
            cool = AnalogDevice('Kühlungslüfter', coolspeed.id,
                                'PWM 1', minimum=10, maximum=80)
            cool.plugin(self.bus)
            coolspeed.plugin(self.bus)

            # ... and history for a diagram
            t_history = History('Temperaturen',
                                [wasser_i1.id, wasser_i2.id,
                                 wasser.id,  # wasser_o.id,
                                 coolspeed.id])  # , cool.id])
            t_history.plugin(self.bus)

            # __CO2__ #
            adc_ph = AnalogInput('pH Sonde', 'ADC #1 in 3', 2.49, 'V',
                                 avg=3, interval=120)
            calib_ph = ScaleAux('pH Wert', adc_ph.id, 'pH',
                                limit=(4.0, 10.0),
                                points=[(2.99, 4.0), (2.51, 6.9)])
            ph = MaximumCtrl('pH Steuerung', calib_ph.id, 6.7)

            ph_broken = False   # True
            if ph_broken:
                # WAR broken CO2 vent:
                # pulse it, as CO2 only flows when partially opened
                ph_ticker = ScheduleInput('pH Blinker', '* * * * * */15')
                ph_ticker_or = MinAux('pH Toggle', {ph.id, ph_ticker.id})
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
                                 [adc_ph.id, calib_ph.id, ph.id])  # , out_ph.id])
            ph_history.plugin(self.bus)

            # Alert system
            email_alert = Alert('Email-Warnungen',
                                {AlertAbove(calib_ph.id, 7.5),
                                 AlertBelow(calib_ph.id, 6.5),
                                 AlertAbove(wasser_i1.id, 26.0),
                                 AlertBelow(wasser_i1.id, 24.5)},
                                'Email #1', repeat=30 * 60)
            email_alert.plugin(self.bus)
            telegram_alert = Alert('Telegram-Warnungen',
                                   {AlertAbove(calib_ph.id, 7.3),
                                    AlertBelow(calib_ph.id, 6.8),
                                    AlertAbove(wasser_i1.id, 25.2),
                                    AlertBelow(wasser_i1.id, 24.7)},
                                   'Telegram #1', repeat=30 * 60)
            telegram_alert.plugin(self.bus)

            return

        if TEST_PH:
            adc_ph = AnalogInput('pH Sonde', 'ADC #1 in 3', 2.49, 'V',
                                 avg=1, interval=30)
            calib_ph = ScaleAux('pH Kalibrierung', adc_ph.id, 'pH',
                                limit=(4.0, 10.0),
                                points=[(2.99, 4.0), (2.51, 6.9)])
            ph = MaximumCtrl('pH', calib_ph.id, 7.0)
            # ph = PidCtrl('pH', calib_ph.id, 7.0)
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
                                         # 'PWM 0', percept=True, maximum=80)
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

                light_max = MaxAux('Max Licht', {light_c.id, dawn_c.id})
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
                # __Temperatures__ #
                # single water temp sensor
                # 2-point switched relay or triac ...
                # wasser_i1 = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C',
                #                         avg=1, interval=60)
                # wasser = MinimumCtrl('Temperatur', wasser_i1.id, 25.0)
                # wasser_o = SwitchDevice('Heizstab', wasser.id,
                #                         'GPIO 12 out', inverted=False)

                # ... or PID driven triac (relay has increased wear, not recomm.)
                # PID for my 60cm/100W: sensor cycle 300s, PID 1.0/0.05/5, PWM 10s
                wasser_i1 = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C',
                                        avg=1, interval=30)
                wasser = PidCtrl('Heizleistung (PID)', wasser_i1.id, 25.0,
                                 p_fact=1.0, i_fact=0.05, d_fact=0.0)
                wasser_o = SlowPwmDevice('Heizstab', wasser.id,
                                         'GPIO 12 out', inverted=False, cycle=10)
                wasser_i1.plugin(self.bus)
                wasser.plugin(self.bus)
                wasser_o.plugin(self.bus)

                # ... and history for a diagram
                t_history = History('Temperaturen',
                                    [wasser_i1.id, wasser.id])  # , wasser_o.id])
                t_history.plugin(self.bus)

            else:
                # 2 temp sensors -> average -> temp ctrl -> relay
                wasser_i1 = AnalogInput('T-Sensor 1', 'DS1820 #1', 25.0, '°C')
                wasser_i1.plugin(self.bus)

                wasser_i2 = AnalogInput('T-Sensor 2', 'DS1820 #2', 25.0, '°C')
                wasser_i2.plugin(self.bus)

                w_temp = AvgAux('T-Mittel', {wasser_i1.id, wasser_i2.id})
                w_temp.plugin(self.bus)

                w1_ctrl = MinimumCtrl('W-Heizung', w_temp.id, 25.0)
                w1_ctrl.plugin(self.bus)

                w2_ctrl = MaximumCtrl('W-Kühlung', wasser_i2.id, 26.5)
                w2_ctrl.plugin(self.bus)

                w_heat = SwitchDevice('W-Heizer', w1_ctrl.id, 'GPIO 12 out')
                w_heat.plugin(self.bus)

                #FIXME: a node chain like this one has no *Ctrl and is thus \
                #       invisible in UI, although totally valid
                w_coolspeed = ScaleAux('Lüftergeschwindigkeit', w_temp.id, '%',
                                       points=[(25.1, 0), (26, 100)])
                w_cool = AnalogDevice('W-Lüfter', w_coolspeed.id,
                                      'PWM 1')  # ?? minimum=10, maximum=80)
                w_cool.plugin(self.bus)
                w_coolspeed.plugin(self.bus)

                t_history = History('Temperaturen',
                                    [wasser_i1.id, wasser_i2.id, w_temp.id,
                                     w_heat.id, w_cool.id])
                t_history.plugin(self.bus)

        if TEST_ALERT:
            led_alert = Alert('Alert LED',
                              {AlertAbove(calib_ph.id, limit=7.5, duration=1),
                               AlertBelow(calib_ph.id, 6.5),
                               AlertAbove(ph.id, duration=15)
                               #AlertAbove(wasser_i1.id, 26.0), AlertBelow(wasser_i1.id, 24.5)
                               },
                              'Telegram #1', repeat=10)  # 30 * 60)
            led_alert.plugin(self.bus)
#            mail_alert = Alert('Alert Mail',
#                               {AlertAbove(wasser_i1.id, 25.2), AlertBelow(wasser_i1.id, 24.9)},
#                               'Email #1')  #TEMP, no drivers for Telegram yet
#            mail_alert.plugin(self.bus)
