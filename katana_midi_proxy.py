"""
Mididings script translating from a couple of ActitioN MIDI controller
footpedals to control of a Katana MkII Head amplifier.

MIDI out from the controllers should be routed into `katana_proxy` input, and
`katana_proxy` outputs routed to the Katana and the ActitioN programmable
controller.
"""
import inspect
import logging
import time

from _thread import start_new_thread

from mididings import *
from mididings import engine
from mididings import event

# logging.basicConfig(level=logging.INFO)
# logging.basicConfig(level=logging.DEBUG)

config(
	backend='alsa',
	client_name='katana_proxy',
	data_offset=1,
	out_ports=[
		'out_to_katana',
		'out_to_controller',
		],
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
	"60 00 00 10": "boost_on",
	"60 00 01 00": "mod_on",
	"60 00 03 00": "fx_on",
	"60 00 05 00": "delay_on",
	"60 00 05 40": "reverb_on",
	"60 00 05 20": "delay2_on",
	"60 00 05 50": "pedal_fx_on",
	"60 00 06 14": "solo_on",
	}

PREFIX = "f0 41 00 00 00 00 33"

sysex_cmds = {
	"boost_color": {
		0: "12 60 00 06 39 00",
		1: "12 60 00 06 39 01",
		2: "12 60 00 06 39 02",
		},
	"mod_color": {
		0: "12 60 00 06 3a 00",
		1: "12 60 00 06 3a 01",
		2: "12 60 00 06 3a 02",
		},
	"fx_color": {
		0: "12 60 00 06 3b 00",
		1: "12 60 00 06 3b 01",
		2: "12 60 00 06 3b 02",
		},
	"delay1_color": {
		0: "12 60 00 06 3c 00",
		1: "12 60 00 06 3c 01",
		2: "12 60 00 06 3c 02",
		},
	"reverb_color": {
		0: "12 60 00 06 3d 00",
		1: "12 60 00 06 3d 01",
		2: "12 60 00 06 3d 02",
		},
	"global_eq_color": {
		0: "12 00 00 00 2e 00",
		1: "12 00 00 00 2e 01",
		2: "12 00 00 00 2e 02",
		},

	# 127 -> on, 0 -> off
	"reverb_on": {
		1:		  "12 60 00 05 40 01",
		0:		  "12 60 00 05 40 00",
		},
	"delay2_on": {
		1:		  "12 60 00 05 20 01",
		0:		  "12 60 00 05 20 00",
		},
	"pedal_fx_on": {
		1:		  "12 60 00 05 50 01",
		0:		  "12 60 00 05 50 00",
		},
	"preamp_solo_on": {
		1:		  "12 60 00 06 14 01",
		0:		  "12 60 00 06 14 00",
		},
	"select_amp": "12 00 01 00 00 00 {}",
	"delay1_tap": "12 60 00 05 02 {} {}",
	"delay2_tap": "12 60 00 05 22 {} {}",
	}

query_cmds = [
	"12 7f 00 00 01 01",           # put into verbose mode
	"11 00 01 00 00 00 00 00 02",  # get patch number
	"11 60 00 00 10 00 00 00 48",  # get boost data
	"11 60 00 01 00 00 00 01 00",  # get mod data
	"11 60 00 03 00 00 00 01 00",  # get fx data
	"11 60 00 05 00 00 00 00 1a",  # get delay data
	"11 60 00 05 20 00 00 00 1a",  # get delay2 data
	"11 60 00 05 40 00 00 00 32",  # reverb / pedalfx data
	"11 60 00 06 39 00 00 00 05",  # get effect colors
	"11 00 00 00 2e 00 00 00 01",  # get global eq color
	]

amp_state = {
	# effect colors: 0 == green, 1 == red, 2 == yellow
	"boost_color":		0,
	"mod_color":		0,
	"fx_color":			0,
	"delay_color":		0,
	"reverb_color":		0,
	"global_eq_color":	0,

	# setting toggles: 0 == off, 1 == on
	"reverb_on":		0,
	"delay2_on":		0,
	"pedal_fx_on":		0,
	"preamp_solo_on":	0,

	"bank":				0,		 # toggles btn 0 and 127
	"patch_selected":	1,		 # from 1-8

	"delay1_tap":		0,		 # becomes a timestamp (ms since epoch)
	"delay2_tap":		0,
	}

LED_map = {
	# map from effect names to CC commands that will set the corresponding LED
	"boost_on":		   110,
	"mod_on":		   111,
	"fx_on":		   112,
	"delay_on":		   113,
	"reverb_on":	   114,
	"delay2_on":	   115,
	"pedal_fx_on":	   116,
	"patch_selected":  118,
	"bank":			   117,
	}

def get_checksum(values):
	accum = 0
	for val in values:
		accum = (accum + val) & 127
	return (128-accum) & 127

def cmd_sent_debug(port, sysex_cmd):
    caller_name = inspect.stack()[1][3]
    logging.debug("fn name: {}; ev.port: {}; {}".format(caller_name, port, sysex_cmd))

def format_sysex_cmd(cmd_hex):
	hex_parts = cmd_hex.split()
	send_or_rcv, cmd = hex_parts[0], hex_parts[1:]
	cmd_ints = [int(v, 16) for v in cmd]
	checksum = '{:02x}'.format(get_checksum(cmd_ints))
	formatted = " ".join((PREFIX, send_or_rcv, " ".join(cmd), checksum, 'f7'))
	logging.debug("formatted sysex_cmd: {}".format(formatted))
	return formatted

def output_event(event, sleep=.002):
	engine.output_event(event)
	if sleep > 0:
		time.sleep(sleep)

def next_color(ev, attr_name):
	"""
	Switches the specified effect to the next color in the cycle.
	"""
	# determine the next color and set for next time
	logging.info("ENTER next_color")
	logging.info("ev: {}; attr_name: {}".format(ev, attr_name))
	color = amp_state[attr_name]
	if color >= 2:
		color = 0
	else:
		color = color + 1
	amp_state[attr_name] = color

	# send the command
	sysex_cmd = sysex_cmds[attr_name][color]
	cmd_sent_debug(ev.port, sysex_cmd)
	return event.SysExEvent(ev.port, sysex_cmd)

def toggle_effect(ev, effect):
	"""
	Toggles the specified trait on (value 127) or off (value 0).
	"""
	logging.info("ENTER toggle_effect")
	logging.info("ev: {}; effect: {}".format(ev, effect))
	key = ev.value
	# 0-63 == off, 64-127 == on
	if key <= 63:
		key = 0
	else:
		key = 1
	sysex_cmd = sysex_cmds[effect][key]
	cmd_sent_debug(ev.port, sysex_cmd)
	return event.SysExEvent(ev.port, sysex_cmd)

def select_amp_sysex(patch):
	"""
	Returns the sysex cmd for selecting the specified patch.
	"""
	return format_sysex_cmd(
		sysex_cmds["select_amp"].format('{:02x}'.format(patch)))

def select_amp(ev):
	"""
	We accept program change (PC) values 2-5. (The controller sends 1-4, which
	the Katana recognizes, but since `data_offset` is 1 so we can access the
	controller's listener channel 16 mididings sees them as 2-5.) If the `bank`
	value is 0 we use the first bank, if >0 we use the second one.
	"""
	logging.info("ENTER select_amp")
	logging.info("ev: {}".format(ev))
	patch = ev.program - 1
	if not 1 <= patch <= 4:
		return
	if amp_state["bank"] > 0:
		# upper bank is 5-8
		patch = patch + 4
	amp_state["patch_selected"] = patch
	sysex_cmd = select_amp_sysex(patch)
	cmd_sent_debug(ev.port, sysex_cmd)
	return event.SysExEvent(ev.port, sysex_cmd)

def toggle_amp_bank(ev):
	"""
	Toggles btn the two banks of four amps.
	"""
	logging.info("ENTER toggle_amp_bank")
	logging.info("ev: {}; amp_state['bank']: {}".format(ev, amp_state["bank"]))
	if ev.value == amp_state["bank"]:
		# we're already in the selected bank, do nothing
		return

	# get current patch and adjust it to match the new bank
	patch = amp_state["patch_selected"]
	if ev.value == 0:
		patch = patch - 4
	else:
		patch = patch + 4

	# update our state trackng w the new values
	amp_state["bank"] = ev.value
	amp_state["patch_selected"] = patch

	# emit sysex event to switch to the corresponding amp in the other bank
	sysex_cmd = select_amp_sysex(patch)
	cmd_sent_debug(ev.port, sysex_cmd)
	return event.SysExEvent(ev.port, sysex_cmd)

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
		code = 2	 # delay1's opcode is 0x02
	else:
		code = 34	 # delay2's opcode is 0x22

	checksum = get_checksum((96, 0, 5, code, first_hex, second_hex))

	# turn them into 2 digit strings
	first_hex = '0' + hex(first_hex)[2:] # always a single digit
	second_hex = hex(second_hex)[2:].zfill(2) # might be one or two digits

	sysex_cmd = format_sysex_cmd(
		sysex_cmds[tap_str].format(first_hex, second_hex)
		)
	return event.SysExEvent(ev.port, sysex_cmd)

def process_query_result(ev):
	"""
	Parse SysEx data coming from the Katana to get amp state and send
	MIDI commands out to the controller to update the LEDs if needed.
	"""
	hex_bytes = ' '.join('{:02x}'.format(x) for x in ev.sysex)
	logging.debug("SysEx event rec'd: {}".format(hex_bytes))

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
			logging.debug("setting name: {}".format(setting_name))
			# no match, ignore it
			continue

		ctrl_port = engine.out_ports()[1]
		# update our amp state data and set LEDs on the controller
		if setting_name.endswith("color"):
			logging.info("Match: " + setting_name)
			amp_state[setting_name] = int(data_byte)
		elif setting_name.endswith("on"):
			logging.info("Match: " + setting_name)
			amp_state[setting_name] = int(data_byte)
			if (LED_CC := LED_map.get(setting_name)) is not None:
				out_val = 0 if int(data_byte) == 0 else 127
				logging.info("Sending {} to controller CC {} - {}".format(
					out_val, LED_CC, setting_name,
					))
				output_event(
					event.CtrlEvent(
						ctrl_port, 16, LED_CC, out_val
						)
					)
		elif setting_name == "patch_selected":
			logging.info("Match: patch_selected")
			b4_patch = amp_state["patch_selected"]
			patch = int(data_bytes[-1], 16)
			logging.info("patch: {}".format(patch))
			LED_start = LED_map["patch_selected"]
			amp_state["patch_selected"] = patch
			if b4_patch > 4:
				b4_patch = b4_patch - 4
			LED_CC = LED_start + b4_patch - 1
			logging.info("Sending {} to controller CC {} - {} previous: {}".format(
				0, LED_CC, setting_name, b4_patch,
				))
			output_event(event.CtrlEvent(ctrl_port, 16, LED_CC, 0))
			if patch <= 4:
				amp_state["bank"] = 0
				LED_CC = LED_start + patch - 1
			else:
				amp_state["bank"] = 127
				LED_CC = LED_start + patch - 5
			logging.info("Sending {} to controller CC {} - {}: {}".format(
				127, LED_CC, setting_name, patch,
				))
			output_event(event.CtrlEvent(ctrl_port, 16, LED_CC, 127))
			logging.info("Sending {} to controller CC {} - {}: bank {}".format(
				127, LED_map["bank"], setting_name, amp_state["bank"]
				))
			output_event(
				event.CtrlEvent(
					ctrl_port, 16, LED_map["bank"], amp_state["bank"]
					)
				)

def init():
	"""
	Send SysEx command queries to initialize our state.
	"""
	for sysex_cmd, cmd_set in sysex_cmds.items():
		if type(cmd_set) == dict:
			for key, cmd_hex in cmd_set.items():
				sysex_cmds[sysex_cmd][key] = format_sysex_cmd(cmd_hex)

	time.sleep(1) # wait for the engine to initialize
	ports = engine.out_ports()
	port = ports[0]
	for query_cmd in query_cmds:
		cmd = format_sysex_cmd(query_cmd)
		output_event(event.SysExEvent(port, cmd), sleep=0)

start_new_thread(init, ())

run(
	# CC messages for various toggles, option cycling, and delay taps
	[
		Filter(CTRL) >> CtrlSplit({
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
		ProgramFilter([2, 3, 4, 5]) >> Process(select_amp),
		# SysEx messages are query results back from the amp
		SysExFilter(manufacturer=0x41) >> Call(process_query_result),
		SysExFilter("\xf0\x7e") >> Call(process_query_result),
	]
	)
