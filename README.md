# aquaPi
A fish tank controller for Raspberry PI

By using small functional blocks, this software can build the controller functions for your fish tank in a highly modular way. The results are minimal hardware requirements and a UI without unused elements, whether you want a simple light dimmer or a complex setup with redundant temperature sensors, many lights, a pH controller and dosers. Based on a Raspberry Pi (starting as small as the zero!), you can get a versatile solution, including diagrams, email or Telegram alarms, multi-channel dimmers, etc., for a competitive price.
Some experience with hardware setup is required. If you're not into electronics you can combine it with the common TC420 LED controller as light dimmer or the RoboTank or Leviathan boards, sold in the U.S (some subfunctions not supported yet).

On the technical side - for those who like to understand the inner workings or to contribute:
The project is based on Python/Flask as the backend, plus Vuetify as the reactive frontend. The Raspberry runs "headless", meaning a browser on your mobile, tablet, or PC will display the user interface.

To explain the building blocks, let's start with a simple temperature controller:

You select an analog input node (reading values from a temperature sensor like DS1820) and connect it to a threshold node (switching on/off depending on the reading), which then is connected to a relay output node. That's all. Add a history node to get temperature graphs with selectable time period.

Later, for improved reliability, you might want to have redundant sensors; you would simply add a 2nd input node reading another sensor, plus an averaging node to combine both readings. Finally, you would reconfigure your threshold node to listen to the average node instead of the sensor.

AquaPi is designed to work entirely offline, with no cloud! The WiFi network is required to allow the user interface on your mobile or PC, but the communication stays in your WiFi zone unless you decide to expose it through VPN or similar. Time is automatically synchronized to your network.

**What is working so far?**

The backend is complete to allow running an aquarium with temperature, pH/CO2 and light (smooth sunrise, sunset, clouds). The UI is eady to monitor everything, including graphical charts. Drivers for relays, onboard PWM, TC420, temperature sensor DS1820 and ADC AD1115 (pH probe!) are working; more to follow.
The configuration of controller blocks has no user interface yet; you need to edit the (simple!) Python source to define the nodes described above.

**What is needed?**
- More drivers for I²C chips and WiFi devices (e.g. Shelly) must be implemented.
- Reporting functions in various ways (email/Telegram alerts, logging page).
- Documentation. Testing. Translation. Deployment.

If you are interested in contributing in any form, you are welcome! Please leave a note in Discussion or Issues.
If you don't want to contribute but have an idea of a "killer feature" let's talk about it in Discussions too.  BTW, German is my native language; feel free to use it here.

To start with aquaPi, clone the repository to e.g.  ~/aquaPI  on a Raspberry Pi or your Linux system, then source ". aquaPI/init". This step will initialize Python and all dependencies. It will also explain how to run the development instance of aquaPi.

The target platform is Raspberry OS (64bit or 32bit), while development can be done on any Linux system with Python 3.10 or later. Windows might be usable as development environment, but honestly, I don't care. All drivers support a simulation mode, thus no Raspberry is needed for development.

Markus Kuhn, 2024-12-21
