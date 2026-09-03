#!/usr/bin/env python3

import logging
from os import (environ, path)
import json
import atexit
from threading import Timer

from .. import db
from .msg_bus import MsgBus
from .ctrl_nodes import (MaximumCtrl, MinimumCtrl, PidCtrl, SunCtrl, FadeCtrl)  # noqa
from .in_nodes import (AnalogInput, SwitchInput, ScheduleInput, UiSwitchInput)  # noqa
from .out_nodes import (AnalogDevice, SlowPwmDevice, SwitchDevice)  # noqa
from .aux_nodes import (AvgAux, MaxAux, MinAux, ScaleAux)  # noqa
from .hist_nodes import History
from .alert_nodes import (Alert, AlertAbove, AlertBelow)  # noqa
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

        # merge customized global config from this file - unlike the
        # Email/Telegram sub-migration below (which moves out of config.json
        # once and for all, into the users DB, since that already has a
        # /settings editor), there's no editor yet for the rest of this
        # file's keys (DEFAULT_CONFIG, backup settings, ...), so it stays a
        # live merge, re-read on every start, not a one-time migration.
        cfg_file = 'config.json'
        if 'AQUAPI_CFG' in environ:
            cfg_file = environ['AQUAPI_CFG']
        cfg_file = path.join(instance_path, cfg_file)

        if path.exists(cfg_file):
            with open(cfg_file, 'r', encoding='utf8') as f_in:
                custom_cfg = json.load(f_in)
            self.globals.update(custom_cfg)

        # AQUAPI_WIRING used to name the pickle file directly (e.g.
        # 'wiring.pickle' or, via `run -w nodes`, 'nodes.pickle'). It now
        # names the *base* wiring, stored in an equally named '.sqlite'
        # database.
        #
        # This name doubles as the default-config selector: 'wiring' (the
        # default, no config.json entry needed) bootstraps the real/
        # production node set the first time instance/wiring.sqlite doesn't
        # exist yet; any other name (e.g. 'dev', set via config.json's
        # "DEFAULT_CONFIG" or a one-off '-w NAME') bootstraps the dev/test
        # node set instead, in its own separate instance/<name>.sqlite -
        # see create_default_nodes(). This replaces the old TEST_BUS/
        # REAL_CONFIG constants that used to live (and had to be kept out
        # of commits) in create_default_nodes() itself.
        wiring_base = self.globals.get('DEFAULT_CONFIG', 'wiring')
        if 'AQUAPI_WIRING' in environ:
            wiring_base = environ['AQUAPI_WIRING']
        wiring_base, _ = path.splitext(wiring_base)
        self.globals['DEFAULT_CONFIG'] = wiring_base

        wiring_file = path.join(instance_path, wiring_base + '.sqlite')

        self.globals['CUSTOM_CFG'] = cfg_file
        self.globals['BUS_WIRING'] = wiring_file

        # Email/Telegram credentials now live in the users SQLite DB
        # (table 'notification_config'), not in config.json anymore.
        # A config.json still present is migrated once, then ignored.
        users_db_path = db.get_users_db_path(instance_path)
        self.globals['USERS_DB'] = users_db_path

        if db.migrate_notification_config_from_json(self.globals, users_db_path):
            log.brief("=== Migrated notification config (Email/Telegram) from "
                      "%s to %s", cfg_file, users_db_path)

        for channel in db.NOTIFICATION_CHANNELS:
            cfg_list = db.get_notification_config(users_db_path, channel)
            if cfg_list:
                driver_config[channel] = cfg_list

        # let alert_nodes.py look up per-user notification prefs without
        # needing Flask's app context (mirrors driver_config's pattern)
        db.set_current_users_db_path(users_db_path)

        # let a deployment skip specific drivers' find_ports() entirely,
        # e.g. hardware that isn't present or a discovery that's slow/
        # unreliable on that network - a list of driver class names in
        # config.json's "DRIVER_BLACKLIST", live-merged above into
        # self.globals like the rest of this file's keys (no editor
        # for it yet, same as DEFAULT_CONFIG/backup settings)
        driver_config['DRIVER_BLACKLIST'] = self.globals.get('DRIVER_BLACKLIST', [])

        # database backups (Step 24): daily rotating backup of both
        # SQLite databases into instance/backups/, in addition to the
        # on-demand GET /api/backup download (aquaPi/api.py)
        self.globals['BACKUP_DIR'] = environ.get(
            'AQUAPI_BACKUP_DIR', path.join(instance_path, 'backups'))
        self._backup_interval = int(environ.get('AQUAPI_BACKUP_INTERVAL', 24 * 60 * 60))
        self._backup_keep = int(environ.get('AQUAPI_BACKUP_KEEP', db.DEFAULT_BACKUP_KEEP))
        self._backup_timer: Timer | None = None

        create_io_registry()

        try:
            if not db.wiring_exists(self.globals['BUS_WIRING']):
                self.bus: MsgBus = MsgBus(threaded=False)

                log.brief("=== There are no controllers defined, creating default")

                self.create_default_nodes()
                self.save_nodes(self.bus)

                log.brief("=== Successfully created Bus and default Nodes")
                log.brief("  ... and saved to %s", self.globals['BUS_WIRING'])

            else:
                log.brief("=== Loading Bus & Nodes from %s", self.globals['BUS_WIRING'])
                self.bus = self.restore_nodes()

        except DriverError as ex:
            log.fatal("Creation of a controller failed: %s", ex.msg)
            raise

        # Our __del__ would not be called after Ctrl-C.
        atexit.register(self.shutdown)

        self._schedule_backup()

        log.brief("%s", str(self.bus))
        if self.bus:
            log.info(self.bus.get_nodes())

    def _run_backup(self) -> None:
        """ create one scheduled, rotating backup generation, then
            reschedule the next run - runs in the Timer's own thread
        """
        try:
            archive = db.create_scheduled_backup(
                self.globals['BUS_WIRING'], self.globals['USERS_DB'],
                self.globals['BACKUP_DIR'], keep=self._backup_keep)
            log.brief('=== Scheduled backup created: %s', archive)
        except Exception:
            log.exception('Scheduled backup failed')
        finally:
            self._schedule_backup()

    def _schedule_backup(self) -> None:
        """ (re-)arm the daily backup timer; a daemon thread so it
            never blocks process shutdown on its own
        """
        self._backup_timer = Timer(self._backup_interval, self._run_backup)
        self._backup_timer.daemon = True
        self._backup_timer.start()

    def shutdown(self) -> None:
        """ Prepare for shutdown, save bus state etc.
        """
        log.brief('Preparing shutdown ...')

        if self._backup_timer:
            self._backup_timer.cancel()
            self._backup_timer = None

        # write changed data (onyl our!) back to self.globals['CUSTOM_CFG']
        # thus, load from file, update our dynamic keys, then write back
        custom_cfg: dict[str, str] = {}
        cfg_file = self.globals['CUSTOM_CFG']
        if path.exists(cfg_file):
            with open(cfg_file, 'r', encoding='utf8') as f_in:
                custom_cfg = json.load(f_in)
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

    def save_nodes(self, container: MsgBus, fname: str = '') -> None:
        """ save the Bus, Nodes and Drivers to SQLite storage
            Parameters allow usage for controller templates,
            contained in "something", not a bus
        """
        if container:
            if not fname:
                fname = self.globals['BUS_WIRING']
            db.save_wiring(container, fname)

    def restore_nodes(self, fname: str = '') -> MsgBus:
        """ recreate the Bus, Nodes and Drivers from SQLite storage,
            or a controller template in a container from some file
        """
        if not fname:
            fname = self.globals['BUS_WIRING']
        return db.load_wiring(fname)

    def create_default_nodes(self) -> None:
        """ "let there be light" and heating of course, what
            else do my fish(es) need?
            Distraction: interesting fact about English:
              "fish" is plural, "fishes" are several species of fish
        """
        # which default node set to bootstrap is now driven by the
        # wiring name itself (see MachineRoom.__init__'s DEFAULT_CONFIG
        # resolution) instead of source-level toggles: 'wiring' (the
        # default) -> the real/production config below; 'test_bus' -> the
        # minimal test bus; anything else (e.g. 'dev') -> the dev/test
        # scenarios further down.
        default_config = self.globals.get('DEFAULT_CONFIG', 'wiring')

        TEST_PH = True  # True
        SIM_LIGHT = True  # True
        SIM_TEMP = True  # True
        COMPLEX_TEMP = SIM_TEMP and False

        # NOTE:
        # plugin() nodes with Role.IN_ENDP last to have less
        # traffic during startup

        if default_config == 'test_bus':
            wasser_i1 = AnalogInput('Input', 'DS1820 #1', 24.6, '°C',
                                    avg=1, interval=10)
            wasser = MinimumCtrl('Ctrl', wasser_i1.id, 25.0)
            wasser_o = SwitchDevice('Output', wasser.id,
                                    'GPIO 12 out', inverted=False)
            wasser_i1.plugin(self.bus)
            wasser.plugin(self.bus)
            wasser_o.plugin(self.bus)

            telegram_alert = Alert('Telegram-Warnungen',
                                   {  # AlertAbove(calib_ph.id, 7.3),
                                      # AlertBelow(calib_ph.id, 6.8),
                                      # AlertAbove(wasser_i1.id, 25.2),
                                     AlertBelow(wasser_i1.id, 24.7)},
                                   'Telegram #1', repeat=30 * 60)
            telegram_alert.plugin(self.bus)
            return

        if default_config == 'wiring':
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
                              [light_schedule.id, light_c.id])
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
                                    interval=300)
            wasser = PidCtrl('Heizleistung', wasser_i1.id, 25.0,
                             p_fact=110, i_fact=0.07, d_fact=0.0)
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
                                 avg=3, interval=60)
            calib_ph = ScaleAux('pH Wert', adc_ph.id, 'pH',
                                limit=(4.0, 10.0),
                                points=[(2.99, 4.0), (2.51, 6.9)])
            adc_ph.plugin(self.bus)
            calib_ph.plugin(self.bus)

            PH_BROKEN = False   # True
            PH_PID = False
            if not PH_PID:
                ph = MaximumCtrl('pH Steuerung', calib_ph.id, 6.7)
                if PH_BROKEN:
                    # WAR broken CO2 vent:
                    # pulse it, as CO2 only flows when partially opened
                    ph_ticker = ScheduleInput('pH Blinker', '* * * * * */15')
                    ph_ticker_or = MinAux('pH Toggle', {ph.id, ph_ticker.id})
                    ph_ticker.plugin(self.bus)
                    ph_ticker_or.plugin(self.bus)
                    out_ph = SwitchDevice('CO2 Ventil', ph_ticker_or.id, 'GPIO 20 out')
                else:
                    out_ph = SwitchDevice('CO2 Ventil', ph.id, 'GPIO 20 out')
            else:
                ph = PidCtrl('pH Regler', calib_ph.id, 6.7,
                             p_fact=-1.0, i_fact=-0.07, d_fact=0.0)
                out_ph = SlowPwmDevice('CO2 Ventil', ph.id,
                                       'GPIO 20 out', inverted=False, cycle=15)

            ph.plugin(self.bus)
            out_ph.plugin(self.bus)

            # ... and history for a diagram
            ph_history = History('pH Verlauf',
                                 [adc_ph.id, calib_ph.id, ph.id])  # , out_ph.id])
            ph_history.plugin(self.bus)

            # a simple UI switch for the filter pump, should run continuously
            filter_switch = UiSwitchInput('Filterpumpe', True)
            filter_out = SwitchDevice('Filter', filter_switch.id, 'GPIO 13 out')
            filter_switch.plugin(self.bus)
            filter_out.plugin(self.bus)

            # Alert system
            email_alert = Alert('Email-Warnungen',
                                {  # AlertAbove(calib_ph.id, 7.5),
                                   # AlertBelow(calib_ph.id, 6.5),
                                  AlertAbove(wasser_i1.id, 26.0),
                                  AlertBelow(wasser_i1.id, 24.0)},
                                'Email #1', repeat=60 * 60)
            email_alert.plugin(self.bus)
            telegram_alert = Alert('Telegram-Warnungen',
                                   {  # AlertAbove(calib_ph.id, 7.3),
                                      # AlertBelow(calib_ph.id, 6.8),
                                     AlertAbove(wasser_i1.id, 25.5),
                                     AlertBelow(wasser_i1.id, 24.5)},
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

            adc_ph.plugin(self.bus)
            calib_ph.plugin(self.bus)
            ph.plugin(self.bus)
            out_ph.plugin(self.bus)

            ph_history = History('pH Verlauf',
                                 [adc_ph.id, calib_ph.id, ph.id, out_ph.id])
            ph_history.plugin(self.bus)

        if SIM_LIGHT:
            light_schedule = ScheduleInput('Zeitplan 1', '* 10/2 * * *')
            # light_c = FadeCtrl('Beleuchtung', light_schedule.id,
            #                    fade_time=30 * 60)  # 30*60)
            light_c = SunCtrl('Beleuchtung', light_schedule.id, xscend=.2)
            light_pwm = AnalogDevice('Dimmer', light_c.id,
                                     # 'PWM 0', percept=True, maximum=80)
                                     'TC420 #1 CH1', percept=True, maximum=80)
            light_schedule.plugin(self.bus)
            light_c.plugin(self.bus)
            light_pwm.plugin(self.bus)

            history = History('Licht',
                              [light_schedule.id,
                               light_c.id, light_pwm.id])
            history.plugin(self.bus)

        if SIM_TEMP:
            if not COMPLEX_TEMP:
                # __Temperatures__ #
                # single water temp sensor
                TEMP_PID = False
                if not TEMP_PID:
                    # 2-point switched relay or triac ...
                    wasser_i1 = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C',
                                            avg=1, interval=60)
                    wasser = MinimumCtrl('Heizen', wasser_i1.id, 25.0)
                    wasser_o = SwitchDevice('Heizstab', wasser.id,
                                            'GPIO 12 out', inverted=False)
                else:
                    # ... or PID driven triac (relay has increased wear, not recomm.)
                    # PID for my 60cm/100W: sensor cycle 300s, PID 1.0/0.05/5, PWM 10s
                    wasser_i1 = AnalogInput('Wasser', 'DS1820 #1', 25.0, '°C',
                                            avg=1, interval=60)
                    wasser = PidCtrl('Heizleistung (PID)', wasser_i1.id, 25.0,
                                     p_fact=100, i_fact=0.05, d_fact=0.0)
                    wasser_o = SlowPwmDevice('Heizstab', wasser.id,
                                             'GPIO 12 out', inverted=False, cycle=10)
                wasser_o.plugin(self.bus)
                wasser.plugin(self.bus)
                wasser_i1.plugin(self.bus)

                # ... and history for a diagram
                t_history = History('Temperaturen',
                                    [wasser_i1.id, wasser.id])  # , wasser_o.id])
                t_history.plugin(self.bus)

            else:
                # 2 temp sensors -> average -> temp ctrl -> relay
                wasser_i1 = AnalogInput('T-Sensor 1', 'DS1820 #1', 25.0, '°C')
                wasser_i2 = AnalogInput('T-Sensor 2', 'DS1820 #2', 25.0, '°C')
                w_temp = AvgAux('T-Mittel', {wasser_i1.id, wasser_i2.id})

                w1_ctrl = MinimumCtrl('W-Heizung', w_temp.id, 25.0)
                w2_ctrl = MaximumCtrl('W-Kühlung', wasser_i2.id, 26.5)

                w_heat = SwitchDevice('W-Heizer', w1_ctrl.id, 'GPIO 12 out')

                # FIXME: a node chain like this one has no *Ctrl and is thus \
                #       invisible in UI, although totally valid
                w_coolspeed = ScaleAux('Lüftergeschwindigkeit', w_temp.id, '%',
                                       points=[(25.1, 0), (26, 100)])
                w_cool = AnalogDevice('W-Lüfter', w_coolspeed.id,
                                      'PWM 1')  # ?? minimum=10, maximum=80)

                w_heat.plugin(self.bus)
                w2_ctrl.plugin(self.bus)
                w1_ctrl.plugin(self.bus)
                w_temp.plugin(self.bus)

                w_coolspeed.plugin(self.bus)
                w_cool.plugin(self.bus)

                wasser_i2.plugin(self.bus)
                wasser_i1.plugin(self.bus)

                t_history = History('Temperaturen',
                                    [wasser_i1.id, wasser_i2.id, w_temp.id,
                                     w_heat.id, w_cool.id])
                t_history.plugin(self.bus)
