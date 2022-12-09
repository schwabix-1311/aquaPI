# aquaPi
A fish tank controller for Raspberry PI - in implementation phase

The project is based on Python/Flask as backend, plus Vue as reactive frontend.
The controller machinery (the "machine room") uses a highly modular architecture of simple nodes that are chained to build the controller functions.

As an example, a basic temperature controller is built from an analog input node (reading values through a configurable driver), plus a minimum threshold node (switching on/off depending on the analog sensor reading), and a binary output node (writing to a configurable driver). Then, for improved reliability you might want to have redundant sensors; you would simply add another input node reading a 2nd sensor and add an averaging node to combine both readings, finally the threshold would be reconnected to listen to the average instead of the 1st input.
All these nodes communicate in the background on a bus. Any type of listener can easily be added to the bus to implement new functionality, e.g. a node to remember history for diagrams, or a node to send emails when alerting conditions are met.
The backend is designed to work completely offline (you lose time synchronizstion though). The user interface depends on a browser that can run on the same Raspberry system; typically it will be a smart phone or computer and therefore both sides need a network ocnnection, but no cloud services.

What is working so far?
The backend meanwhile can reliably control temperatures (plural!) using DS1820 sensors and relay outputs. Any binary hardware connected to GPIO pins (MOSFETS, relay PCBs) is usable as output. Light controllers work off cron schedules (this will change to a more user friendly calendar later), with smooth fading on both Raspberry PWM channels. The count of controllers of any type is only limited by CPU and memory. ATO (water refill) should be doable with float switch and relay output, but this is unusual for fresh water aquariums where my focus lies. CO2/pH (ADC input) is close to complete.
On the frontend a configurable Dashboard monitors state of backend in real time through any modern browser, including a first implementation of charts.
Operation parameters have a preliminary settings page.
The configuration of controller chains has no user interface yet; you need to edit (simple!) python source to define the nodes described above.

What is needed?
Several drivers for I²C chips need to be implemented. A driver for the pouplar TC420/421 PWM controller is required.
The basic configuration of nodes and controllers needs to be implemented as reactive Vue page(s).
The front end needs a reactive settings page, dynamically offering all adjustable settings of the configured nodes. 
Frontend and backend needs modifications to allow i18n.
Reporting functions in various ways (email alerts, logging page).
Documentataion. Testing. Translation.
Packaging and installation (ATM this project has no build step, and may ship in this form)

If you are interested in any aspect of contribution, you are welcome! Please leave a note in Discussion or Issues.
If you don't want to contribute, but have an idea of a "killer feature" that would make you throw out your current solution ;-)  let's talk about it in Discussions too.  BTW, German is my native language, feel free to use it here.

To get started, clone the repository to e.g.  ~/aquaPI  on your Linux system, then source ". aquaPI/init". This will initialize python and all dependencies. It will also explain how to run the development instance of aquaPi.

Windows is not actively supported as a development environment (currently it seems to work) - in lack of a Windows PC fixing Windows-only issues has no priority. The target system is limited to Raspberry OS anyways. My development environment is Manjaro Linux. All drivers support a simulation mode, so no Raspberry is needed for development.

Markus Kuhn, 2022-12-09
