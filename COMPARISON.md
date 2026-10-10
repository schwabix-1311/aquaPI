# aquaPi compared to commercial aquarium controllers

*As of October 2026. Prices are retailer listings found at that time and vary
a lot by shop, bundle and region; check current prices before buying.*

In short: aquaPi costs a fraction of the commercial controllers in hardware,
runs entirely on your local network, and is open source. In return you wire
the hardware yourself, and there is no warranty or commercial support. Most
commercial systems target saltwater reef tanks; freshwater keepers mostly get
single-purpose devices.

## Overview

| | Price (approx.) | Focus | Cloud | Openness |
|---|---|---|---|---|
| **aquaPi** | ~100–200 EUR in parts¹ | freshwater | none, local only | open source (GPL v3) |
| Neptune Apex A3 Pro | ~1,100–1,250 CAD system (base unit ~495 CAD) | reef | Apex Fusion cloud | closed |
| GHL ProfiLux 4.1 | ~620 EUR base unit, ~1,000 USD Mega-Set | reef and freshwater | optional | closed |
| Hydros Control X4 | ~450 USD starter pack, ~820 USD with power strip | reef | Hydros cloud app | closed |
| JBL ProFlora CO2 Control | ~275–300 EUR, pH probe extra | freshwater, CO2 only | none | closed |
| reef-pi (DIY) | parts only | reef | none | open source |

¹ Raspberry Pi Zero 2 W, DS18B20 temperature sensor, ADS1115-based pH board,
a few relays or Shelly plugs. A rough estimate, not a calculated parts list.

## Where aquaPi is stronger

- **Price for the scope.** The JBL controller alone costs more than an aquaPi
  setup with heating, lighting and pH/CO2 control, and it only covers CO2.
- **Local and private.** Apex and Hydros lean on their own cloud services.
  aquaPi runs completely offline; alerts by email or Telegram only go out if
  you set them up.
- **Flexible logic.** Control chains are assembled from small building blocks
  instead of a fixed program: PID heating, a fan curve, one sensor feeding
  several controllers, redundant sensors averaged.
- **Built for freshwater.** pH/CO2 control with 2-point probe calibration,
  sunrise/sunset/cloud simulation, multi-channel dimming, TC420 support.
  The big systems put most of their effort into reef features.
- **Open and extensible.** New drivers and node types can be added; Shelly
  WiFi devices are discovered automatically.

## Where the commercial systems are stronger

- **Plug & play.** Finished hardware with matching probes, power strips and
  expansion modules, no soldering, no mains wiring of your own. With aquaPi
  the hardware wiring is your responsibility, which matters especially for
  relays switching mains power.
- **Warranty and support.** Hydros, for example, gives a 1-year warranty with
  support from the US. aquaPi is a hobby project without any warranty.
- **Sensor range.** Apex and ProfiLux offer ports for salinity/conductivity,
  ORP, level and leak sensors; Hydros even measures alkalinity. aquaPi
  already handles simple ones (an ORP probe via the ADC, float switches via
  GPIO), but has nothing for conductivity yet.
- **Apps and remote access.** Polished mobile apps and access from outside
  the home out of the box. aquaPi has a responsive web interface, but only
  on the local network unless you set up a VPN.
- **Ecosystem.** Dosing pumps, wave pumps and lights from the same
  manufacturer that work together directly.

## Who aquaPi is for

Freshwater and planted-tank keepers who are comfortable with some
electronics: they get more functionality than a single-purpose CO2
controller for less money, and no cloud. If you want "unpack it, plug it in,
it works", a commercial system is the better choice.

## Sources

- [Neptune Apex A3 Pro at FragBox](https://fragbox.ca/?p=277399)
- [Neptune Apex at Reef Supplies](https://reefsupplies.ca/collections/neptune-apex?page=1)
- [Best aquarium controllers 2026, Cleveland Heart](https://www.clevelandheart.com/?p=55979)
- [GHL ProfiLux controllers](https://www.aquariumcomputer.com/usa/product-category/profilux-aquarium-controller/)
- [GHL ProfiLux 4 launch pricing, Reef Builders](https://reefbuilders.com/2016/11/02/ghl-formally-announces-profilux-4-controller-sets-and-pricing)
- [Hydros Control X4 starter pack, LiveAquaria](https://www.liveaquaria.com/products/hydros-control-x4-starter-pack)
- [Hydros Control X4 PRO pack, Top Shelf Aquatics](https://topshelfaquatics.com/products/hydros-control-x4-aquarium-controller-pro-pack-hydros)
- [JBL ProFlora CO2 Control](https://jbl.de/en/products/detail/9406/jbl-proflora-co2-control?country=es)
- [JBL ProFlora CO2 Control at Olibetta](https://www.olibetta.ch/en-CH/jbl/proflora-co2-control)
- [reef-pi on Hackaday](https://hackaday.io/project/28536-reef-pi)
