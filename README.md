# aquaPi
A fish tank controller for Raspberry PI - in implementation phase

The project is based on Python/Flask as backend, plus Vue on the frontend. The controller machinery (the "machine room") uses a modular extensible architecture of simple controller functions, as well as dynamically loaded drivers.

If you are interested in any aspect of contribution, you are welcome! Please leave a note in Discussion or Issues.
If you don't want to contribute, but have an idea of a "killer feature" that would make you throw out your current solution ;-)  let's talk about it in Discussions too.  BTW, German is my native language, feel free to use it here.

To get started, clone the repository to e.g.  ~/aquaPI  on your Linux system, then source ". aquaPI/init". This will initialize python and all dependencies. It will also explain how to run the development instance of aquaPi.

Windows is not actively supported as a development environment (currently it seems to work) - in lack of a Windows PC fixing Windows-only issues has no priority. The target system is limited to Raspberry OS anyways. My development environment is Manjaro Linux. All drivers support a simulation mode, so no Raspberry is needed for development.

Markus Kuhn, 2022-10-20
