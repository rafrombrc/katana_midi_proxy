"""
Mididings script translating from a couple of Actition MIDI controller
footpedals to control of a Katana MkII Head amplifier.

MIDI out from the controllers should be routed into mididings input, and
mididings output routed to the Katana.
"""
import time

from _thread import start_new_thread

from mididings import *
from mididings import engine
from mididings import event

config(
    backend='alsa',
    client_name='katana_proxy',
    data_offset=0,
    )

addresses = {
    # effect colors
    "60 00 06 39": "boost_color",
    "60 00 06 3a": "mod_color",
    "60 00 06 3b": "fx_color",
    "60 00 06 3c": "delay_color",
    "60 00 06 3d": "reverb_color",
    "00 00 00 2e": "global_eq_color",

    # patch
    "00 01 00 00": "patch_selected",

    # effect / property toggles
    "60 00 05 40": "reverb_on",
    "60 00 05 20": "delay2_on",
    "60 00 05 50": "pedal_fx_on",
    "60 00 06 14": "solo_on",
    }

PREFIX = "f0 41 00 00 00 00 33"

sysex_cmds = {
    "boost_color": {
        0: PREFIX + " 12 60 00 06 39 00 61 f7",
        1: PREFIX + " 12 60 00 06 39 01 60 f7",
        2: PREFIX + " 12 60 00 06 39 02 5f f7",
        },
    "mod_color": {
        0: PREFIX + " 12 60 00 06 3a 00 60 f7",
        1: PREFIX + " 12 60 00 06 3a 01 5f f7",
        2: PREFIX + " 12 60 00 06 3a 02 5e f7",
        },
    "fx_color": {
        0: PREFIX + " 12 60 00 06 3b 00 5f f7",
        1: PREFIX + " 12 60 00 06 3b 01 5e f7",
        2: PREFIX + " 12 60 00 06 3b 02 5d f7",
        },
    "delay1_color": {
        0: PREFIX + " 12 60 00 06 3c 00 5e f7",
        1: PREFIX + " 12 60 00 06 3c 01 5d f7",
        2: PREFIX + " 12 60 00 06 3c 02 5c f7",
        },
    "reverb_color": {
        0: PREFIX + " 12 60 00 06 3d 00 5d f7",
        1: PREFIX + " 12 60 00 06 3d 01 5c f7",
        2: PREFIX + " 12 60 00 06 3d 02 5b f7",
        },
    "global_eq_color": {
        0: PREFIX + " 12 00 00 00 2e 00 52 f7",
        1: PREFIX + " 12 00 00 00 2e 01 51 f7",
        2: PREFIX + " 12 00 00 00 2e 02 50 f7",
        },

    # 127 -> on, 0 -> off
    "reverb_on": {
        1:        PREFIX + " 12 60 00 05 40 01 5a f7",
        0:        PREFIX + " 12 60 00 05 40 00 5b f7",
        },
    "delay2_on": {
        1:        PREFIX + " 12 60 00 05 20 01 7a f7",
        0:        PREFIX + " 12 60 00 05 20 00 7b f7",
        },
    "pedal_fx_on": {
        1:        PREFIX + " 12 60 00 05 50 01 4a f7",
        0:        PREFIX + " 12 60 00 05 50 00 4b f7",
        },
    "preamp_solo_on": {
        1:        PREFIX + " 12 60 00 06 14 01 05 f7",
        0:        PREFIX + " 12 60 00 06 14 00 06 f7",
        },
    "select_amp": PREFIX + " 12 00 01 00 00 00 {} {} f7",
    "delay1_tap": PREFIX + " 12 60 00 05 02 {} {} {} f7",
    "delay2_tap": PREFIX + " 12 60 00 05 22 {} {} {} f7",
    }

amp_state = {
    # effect colors: 0 == green, 1 == red, 2 == yellow
    "boost_color":      0,
    "mod_color":        0,
    "fx_color":         0,
    "delay_color":      0,
    "reverb_color":     0,
    "global_eq_color":  0,

    # setting toggles: 0 == off, 1 == on
    "reverb_on":        0,
    "delay2_on":        0,
    "pedal_fx_on":      0,
    "preamp_solo_on":   0,

    "bank":             0,       # toggles btn 0 and 127
    "patch_selected":   1,       # from 1-8

    "delay1_tap":       0,       # becomes a timestamp (ms since epoch)
    "delay2_tap":       0,
    }

def next_color(ev, attr_name):
    """
    Switches the specified effect to the next color in the cycle.
    """
    # determine the next color and set for next time
    color = amp_state[attr_name]
    if color >= 2:
        color = 0
    else:
        color = color + 1
    amp_state[attr_name] = color

    # send the command
    sysex_cmd = sysex_cmds[attr_name][color]
    return event.SysExEvent(ev.port, sysex_cmd)

def toggle_effect(ev, effect):
    """
    Toggles the specified trait on (value 127) or off (value 0).
    """
    key = ev.value
    # 0-63 == off, 64-127 == on
    if key <= 63:
        key = 0
    else:
        key = 1
    sysex_cmd = sysex_cmds[effect][key]
    return event.SysExEvent(ev.port, sysex_cmd)

def select_amp_sysex(patch):
    """
    Returns the sysex cmd for selecting the specified patch.
    """
    checksum = get_checksum(
        (0, 1, 0, 0, 0, patch))
    return sysex_cmds["select_amp"].format(
         '{:02x}'.format(patch), '{:02x}'.format(checksum)
        )

def select_amp(ev):
    """
    We accept program change (PC) values 1-4. If the `bank` value is 0 we use
    the first bank, if >0 we use the second one.
    """
    patch = ev.program
    if not 1 <= patch <= 4:
        # expect PC 1-4
        return
    if amp_state["bank"] > 0:
        # upper bank is 5-8
        patch = patch + 4
    amp_state["patch"] = patch
    sysex_cmd = select_amp_sysex(patch)
    return event.SysExEvent(ev.port, sysex_cmd)
    return ev

def toggle_amp_bank(ev):
    """
    Toggles btn the two banks of four amps.
    """
    if ev.value == amp_state["bank"]:
        # we're already in the selected bank, do nothing
        return

    # get current patch and adjust it to match the new bank
    patch = amp_state["patch"]
    if ev.value == 0:
        patch = patch - 4
    else:
        patch = patch + 4

    # update our state trackng w the new values
    amp_state["bank"] = ev.value
    amp_state["patch"] = patch

    # emit sysex event to switch to the corresponding amp in the other bank
    return event.SysExEvent(ev.port, select_amp_sysex(patch))

def delay_tap(ev, tap_str):
    """
    Set delay interval by tapping. `tap_str` should be the sysex key,
    `delay1_tap` or `delay2_tap`.
    """
    # now in whole milliseconds
    now = int(time.time() * 1000)

    # always store the new tap time
    last_tap = amp_state[tap_str]
    amp_state[tap_str] = now
    interval = now - last_tap

    # if first tap or > 2s since last tap, do nothing else
    if interval > 2000:
        return

    # get 11 digit binary representation
    interval_bin = bin(interval)[2:].zfill(11)

    # first four digits are the first hex number
    first_hex = int(interval_bin[:4], 2)
    # last 7 digits w a prepended zero is the second hex number
    second_hex = int('0'+interval_bin[4:], 2)

    if tap_str == "delay1_tap":
        code = 2     # delay1's opcode is 0x02
    else:
        code = 34    # delay2's opcode is 0x22

    checksum = get_checksum((96, 0, 5, code, first_hex, second_hex))

    # turn them into 2 digit strings
    first_hex = '0' + hex(first_hex)[2:] # always a single digit
    second_hex = hex(second_hex)[2:].zfill(2) # might be one or two digits
    checksum = hex(checksum)[2:].zfill(2)

    sysex_cmd = sysex_cmds[tap_str].format(
        first_hex, second_hex, checksum)
    return event.SysExEvent(ev.port, sysex_cmd)

def get_checksum(values):
    accum = 0
    for val in values:
        accum = (accum + val) & 127
    return (128-accum) & 127


def process_query_result(ev):
    """
    Process SysEx data coming from the Katana.
    """
    hex_bytes = ' '.join('{:02x}'.format(x) for x in ev.sysex)
    # print("SysEx event rec'd: {}".format(hex_bytes))

    # extract the starting address and an unknown number of data bytes
    start_address = hex_bytes[24:35]
    data_bytes = hex_bytes[36:-6].split()

    address = None
    address_int = None
    last_addr_byte = None

    # iterate through the bytes and check each address
    for data_byte in data_bytes:
        if not address:
            # initialize
            address = start_address
            last_addr_byte = address[-2:]
        else:
            # increment hex str representation.
            if last_addr_byte != "7f":
                # increment the last byte by 1
                last_addr_byte = format(int(last_addr_byte,16)+1, '02x')
                address = "{}{}".format(address[:-2], last_addr_byte)
            else:
                # rolls over, need to increment the upper address byte
                last_addr_byte = "00"
                upper_addr_byte = address[-5:-3]
                upper_addr_byte = format(int(upper_addr_byte,16)+1, '02x')
                address = "{}{} {}".format(
                    address[:-5], upper_addr_byte, last_addr_byte)

        # see if this byte matches a known setting address
        setting_name = addresses.get(address)
        if not setting_name:
            # no match, ignore it
            continue

        # update amp state
        if setting_name.endswith("color") or setting_name.endswith("on"):
            # print("Match: " + setting_name)
            amp_state[setting_name] = int(data_byte)
        elif setting_name == "patch_selected":
            # print("Match: patch_selected")
            patch = int(data_bytes[-1], 16)
            amp_state["patch_selected"] = patch
            if patch <= 4:
                amp_state["bank"] = 0
            else:
                amp_state["bank"] = 127

def init():
    time.sleep(2) # wait for the engine to initialize
    ports = engine.out_ports()
    port = ports[0]
    cmds = [
        # Put into verbose mode
        PREFIX + " 12 7f 00 00 01 01 7f f7",

        # Fetch patch number
        PREFIX + " 11 00 01 00 00 00 00 00 02 7d f7",

        # Fetch effect colors
        PREFIX + " 11 60 00 06 39 00 00 00 04 5d f7",
        #PREFIX + " 11 10 03 00 00 00 00 00 10 5D f7",
        # PREFIX + " 11 10 04 00 00 00 00 00 10 5C f7",
        # PREFIX + " 11 10 05 00 00 00 00 00 10 5B f7",
        # PREFIX + " 11 10 06 00 00 00 00 00 10 5A f7",
        # PREFIX + " 11 10 07 00 00 00 00 00 10 59 f7",
        # PREFIX + " 11 10 08 00 00 00 00 00 10 58 f7",
        # PREFIX + " 11 60 00 00 00 00 00 0f 48 49 f7",
        # PREFIX + " 11 00 00 00 00 00 02 00 1D 61 f7",
        # PREFIX + " 11 00 01 00 00 00 00 00 02 FE f7",
        ]
    for cmd in cmds:
        engine.output_event(
            event.SysExEvent(
                port, cmd)
            )

start_new_thread(init, ())

run(
    # CC messages for various toggles, option cycling, and delay taps
    [Filter(CTRL) >> CtrlSplit({
        20: Process(toggle_effect, "reverb_on"),
        21: Process(toggle_effect, "delay2_on"),
        22: Process(toggle_effect, "pedal_fx_on"),
        23: Process(toggle_amp_bank),

        96: CtrlValueFilter(127) >> Process(next_color, "boost_color"),
        97: CtrlValueFilter(127) >> Process(next_color, "mod_color"),
        98: CtrlValueFilter(127) >> Process(next_color, "fx_color"),
        99: CtrlValueFilter(127) >> Process(delay_tap, "delay1_tap"),
        100: CtrlValueFilter(127) >> Process(next_color, "reverb_color"),
        101: CtrlValueFilter(127) >> Process(delay_tap, "delay2_tap"),

        102: Process(toggle_effect, "preamp_solo_on"),

        103: CtrlValueFilter(127) >> Process(next_color, "global_eq_color"),

        None: Pass(),
        }),
    ProgramFilter([1, 2, 3, 4]) >> Process(select_amp),
    # SysEx messages are query results back from the amp
    SysExFilter(manufacturer=0x41) >> Call(process_query_result),
    SysExFilter("\xf0\x7e") >> Call(process_query_result),
     ]
    )
