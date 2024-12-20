# Katana MIDI Proxy
A [mididings](https://das.nasophon.de/mididings/) script and config files used on a [Le Potato](https://libre.computer/products/aml-s905x-cc/) single board computer Pi to control a Boss Katana MKII amp (running Firmware 2.0 or later) with a [Behringer FCB1010 MIDI controller](https://www.behringer.com/product.html?modelCode=0715-AAA) running a [Wino2 firmware chip](https://www.fcb1010.eu/). This gives a number of advanced abilities in addition to the basics of selecting presets and toggling individual effects on and off:

* Toggle many additional features on and off, including pedal effects, preamp solo, global eq.
* Cycle through the three color options for every effect (including global eq) on every preset.
* Tap the delay interval for both of the Katana's virtual delay pedals.
* Match the Katana's preset UI of 2 banks of 4 presets with a bank toggle (using 5 pedals) instead of a separate pedal for each preset.
* Synchronize the LEDs on the controller with the amp state, including the preset bank toggle, even if amp settings are changed via other means like the panel or other software.
* Simultaneous expression pedal control of volume and the currently selected pedal effect.

This setup currently only uses 3 of the FCB1010's 10 available banks, so it would be possible to add the ability to control many other features, such as toggling noise suppression, toggling the send/return loop, switching the amp or cabinet emulation, selecting alternate signal chain orders, using the expression pedals to control virtual knobs such as the amount of drive in a boost pedal, or anything else the Katana is capable of.

The code could also be fairly easily modified to support other MIDI controller(s). An earlier, less well organized version of this script was used with multiple [Actition controllers](https://www.actition.net/actition-universal-midi-controllers), which are a great, less expensive option than the FCB1010/Wino2 combo. Their maker Thomas was even kind enough to add remote MIDI control of the LEDs to those units so they could be kept in sync with the amp.

# System Configuration

Some additional files have been included beyond the core mididings script:

* A simple systemd service file for managing the proxy service.
* A udev rules file that automatically starts the proxy service when the Katana is connected to the computer and stop it when it is disconnected or turned off.
* A rules file for the [midminder](https://github.com/mzero/midiminder) utility that will auto-connect the Katana and FCB1010 to the proxy service as soon as they are available.
* The Wino2 configuration file that causes the FCB1010 to play well with the proxy.

Some adjustments may be needed to match your system's paths or devices. For instance, since the FCB1010 doesn't have a USB connector, an adapter is needed; the provided midiminder rules are looking for a [Roland UM-ONE](https://www.roland.com/de/products/um-one_mk2/) device instead of the FCB1010 itself. Collectively, they can be installed on to a headless single board computer (SBC) such as a Le Potato or a Raspberry Pi to provide a compact, reliable way to travel with the setup. Ideally the SBC should be set up with a read-only filesystem so it can be safely powered off without needing a clean shutdown.
