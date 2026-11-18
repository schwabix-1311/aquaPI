#!/usr/bin/env python3
""" Tests for DriverDS1820's 1-Wire pin detection
    (aquaPi/driver/DriverOneWire.py) - fake device tree files, no hardware.
"""

import aquaPi.driver.DriverOneWire as ow


def _gpios(tmp_path, name, *cells):
    node = tmp_path / name / 'of_node'
    node.mkdir(parents=True)
    (node / 'gpios').write_bytes(b''.join(c.to_bytes(4, 'big') for c in cells))


def _pattern(tmp_path):
    return str(tmp_path / '*' / 'of_node' / 'gpios')


def test_w1_pin_from_device_tree(tmp_path):
    # as read on a Pi Zero 2 W with plain dtoverlay=w1-gpio
    _gpios(tmp_path, 'onewire@0', 7, 4, 0)
    assert ow.w1_gpio_pins(_pattern(tmp_path)) == [4]


def test_w1_second_bus_and_pullup_pin(tmp_path):
    _gpios(tmp_path, 'onewire@0', 7, 4, 0)
    _gpios(tmp_path, 'onewire@16', 7, 22, 0, 7, 23, 0)   # data + pull-up pin
    assert ow.w1_gpio_pins(_pattern(tmp_path)) == [4, 22, 23]


def test_w1_falls_back_to_gpio4(tmp_path):
    assert ow.w1_gpio_pins(_pattern(tmp_path)) == [4]
