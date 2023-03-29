# aquaPi
A fish tank controller for Raspberry PI - in implementation phase

Using small functional blocks this software can build the controller functions for your fish tank in a highly modular way. The result is minmal hardware requirements and a UI showing exacly your desired functions, whether it is a simple light dimmer or a complex setup with redundant temperature sensors, many lights, pH controller and dosers. Based on a Raspberyy Pi (Model zero or better) you can get a powerful solution including diagrams, email or Telegram alarms, multi-channel dimmers, etc. for a competitive price.
Some experience with hardware setup is required. We're working in it to reduce this part, e.g. the common TC420 LED controller can be integrated and thus eliminates the need for recabling or to get new power drivers (MOSFET). 

On the technical side - for those who like to understand the inner workings, or to contribute:
The project is based on Python/Flask as backend, plus Vuetify as reactive frontend. The Raspberry runs "headless", meaning the user interface is your mobile, tablet, or PC.

To explain the building blocks, lets start with a simple temperature controller:
you select an analog input node (reading values through a configurable driver), connect it to a threshold node (switching on/off depending on the reading), which then is connected to a relay output node (writing to a configurable driver). That's all.
Later, for improved reliability you might want to have redundant sensors; you would simply add another input node reading a 2nd sensor, plus an averaging node to combine both readings. Finally you would reconnect your threshold node to use the average instead of the initial input.

AquaPi is designed to work completely offline, not cloud! Network is required to allow the user interaface on your mobile or PC shown in a browser, but the coomunication stays in your WiFi zone unless you decide to expose it through VPN or similar.

**What is working so far?**

The backend is complete to allow running my :-) aquarium with dimmed light, temperature and pH/CO2. The UI is basically working for monitoring. Drivers for relays, on-board PWM, TC420, temp. sensor DS1820 and ADC AD1115 (pH probe!) are working, more to follow.
The configuration of controller blocks has no user interface yet; you need to edit (simple!) python source to define the nodes described above.

**What is needed?**
- More drivers for I²C chips need to be implemented.
- The intial UI, based on Flask & Jinja is beeing converted to a modern SPA using Vuetify.
- Frontend and backend need translations.
- Reporting functions in various ways (email/Telegram alerts, logging page).
- Documentataion. Testing. Translation.
- Packaging and installation (ATM this project has no build step, and may ship in this form)

If you are interested in any aspect of contribution, you are welcome! Please leave a note in Discussion or Issues.
If you don't want to contribute, but have an idea of a "killer feature" that would make you throw out your current solution ;-)  let's talk about it in Discussions too.  BTW, German is my native language, feel free to use it here.

To get started, clone the repository to e.g.  ~/aquaPI  on your Linux system, then source ". aquaPI/init". This will initialize python and all dependencies. It will also explain how to run the development instance of aquaPi.

Windows is not actively supported as a development environment (currently it seems to work) - in lack of a Windows PC fixing Windows-only issues has no priority. The target system is limited to Raspberry OS anyways. My development environment is Manjaro Linux. All drivers support a simulation mode, so no Raspberry is needed for development.

Markus Kuhn, 2023-03-29
