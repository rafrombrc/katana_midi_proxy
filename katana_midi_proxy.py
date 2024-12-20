"""
Mididings script that sits between a Behringer FCB1010 MIDI controller running
Wino2 firmware and a Katana MkII Head amplifier. This allows much more complete
control over the Katana than most other foot pedal solutions.

The proxy exposes `out_to_katana` and `out_to_controller` outputs to connect to
the device's MIDI inputs. MIDI out from both the controller and the amp should
 be routed to the proxy's single input port.
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

effect_names = ["boost", "mod", "fx", "delay", "reverb", "delay2", "global_eq"]
effect_wo_color_names = ["pedal_fx", "solo"]

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
	"delay_color": {
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

	# 1 -> on, 0 -> off
	"boost_on": {
		1:        "12 60 00 00 10 01",
		0:        "12 60 00 00 10 00",
		},
	"mod_on": {
		1:        "12 60 00 01 00 01",
		0:        "12 60 00 01 00 00",
		},
	"fx_on": {
		1:        "12 60 00 03 00 01",
		0:        "12 60 00 03 00 00",
		},
	"delay_on": {
		1:        "12 60 00 05 00 01",
		0:        "12 60 00 05 00 00",
		},
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
	"solo_on": {
		1:		  "12 60 00 06 14 01",
		0:		  "12 60 00 06 14 00",
		},
	}

sysex_cmds_subs = {
	"select_amp": "12 00 01 00 00 00 {:02x}",
	"delay_tap":  "12 60 00 05 {:02x} {:02x} {:02x}",
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

# map of notes the controller sends to what it tells us about its state
ctrl_state_keys = {
	1: "boost_on",
	2: "mod_on",
	3: "fx_on",
	4: "delay_on",
	5: "reverb_on",
	6: "delay2_on",
	20: "preset",
	21: "preset_toggle",
}

# Each bank's map from effect names to the PC cmds that will push the
# corresponding button
ctrl_LED_maps = {
	1: {
		"boost":		   1,
		"mod":		       2,
		"fx":    		   3,
		"delay":		   4,
		"reverb":   	   5,
		"presets":         6, # presets start here
		"amp_bank":        10,
	},
	2: {
		"boost":		   1,
		"mod":	    	   2,
		"fx":		       3,
		"delay":		   4,
		"reverb":	       5,
		"delay2":          6,
		"pedal_fx":        7,
	},
	3: {},
}


def get_checksum(values):
	accum = 0
	for val in values:
		accum = (accum + val) & 127
	return (128-accum) & 127


def format_sysex_cmd(cmd_hex):
	hex_parts = cmd_hex.split()
	send_or_rcv, cmd = hex_parts[0], hex_parts[1:]
	cmd_ints = [int(v, 16) for v in cmd]
	checksum = '{:02x}'.format(get_checksum(cmd_ints))
	formatted = " ".join((PREFIX, send_or_rcv, " ".join(cmd), checksum, 'f7'))
	logging.debug("formatted sysex_cmd: %s", formatted)
	return formatted


def output_event(event, sleep=.002):
	engine.output_event(event)
	if sleep > 0:
		time.sleep(sleep)


def send_query_cmds(port):
	for query_cmd in query_cmds:
		cmd = format_sysex_cmd(query_cmd)
		output_event(event.SysExEvent(port, cmd), sleep=0)


def log_fn_call(outer_fn):
	def fn(*args, **kwargs):
		logging.info("ENTER %s", outer_fn.__name__)
		logging.info("args: %s", args)
		if kwargs:
			logging.info("kwargs: %s", kwargs)
		return outer_fn(*args, **kwargs)
	return fn


class Effect(object):
	def __init__(self, name, on=False, has_color=True, color=0):
		self.name = name
		self.on = on
		self.has_color = has_color
		if self.has_color:
			# effect colors: 0 == green, 1 == red, 2 == yellow
			self.color = color
		self.is_delay = False
		if self.name.startswith("delay"):
			self.is_delay = True
			self.last_tap = 0 # timestamp (ms since epoch)
			self.tap_opcode = 34 if name.endswith("2") else 2


class Amp(object):
	"""
	Katana Amp.
	"""
	def __init__(self):
		self.effects = dict()
		for name in effect_names:
			self.effects[name] = Effect(name)
		for name in effect_wo_color_names:
			self.effects[name] = Effect(name, has_color=False)

		self.bank = 0  # toggles btn 0 and 127
		self.patch = 0 # from 1 to 8
		self.port = engine.out_ports()[0]

	def run_cmd(self, cmd_name, key):
		"""
		Returns the SysExEvent that runs the specified command.
		"""
		sysex_cmd = sysex_cmds[cmd_name][key]
		caller_name = inspect.stack()[1][3]
		logging.debug("fn name: %s; port: %s; %s", caller_name, self.port,
					  sysex_cmd)
		return event.SysExEvent(self.port, sysex_cmd)

	def run_cmd_subs(self, cmd_name, *args):
		"""
		Returns the SysExEvent that runs the specified command, substituting
		numeric values into the event as needed. This requires the values to
		be encoded into hex, and for the SysEx checksum to be calculated.
		"""
		fmt_args = ['{:02x}'.format(arg) for arg in args]
		sysex_cmd = sysex_cmds_subs[cmd_name].format(*args)
		sysex_cmd = format_sysex_cmd(sysex_cmd)
		caller_name = inspect.stack()[1][3]
		logging.debug("fn name: %s; port: %s; %s", caller_name, self.port,
					  sysex_cmd)
		return event.SysExEvent(self.port, sysex_cmd)

	def get_effect(self, name):
		effect = self.effects.get(name)
		if effect is None:
			logging.error("Unknown effect: %s", name)
		return effect

	@log_fn_call
	def toggle_effect(self, ev, name):
		"""
		Turns an effect on or off.
		"""
		effect = self.get_effect(name)
		if effect is None:
			return
		# 0-63 == off, 64-127 == on
		on = ev.value >= 64
		if on == effect.on:
			# already matches, do nothing
			return
		effect.on = on
		return self.run_cmd(name+"_on", on)

	@log_fn_call
	def toggle_amp_bank(self, ev):
		"""
		Toggles btn the two banks of four amp presets.
		"""
		bank = ev.value
		if bank == self.bank:
			# already matches, do nothing
			return
		self.bank = bank
		# adjust patch to match the new bank
		self.patch = self.patch + 4 if bank else self.patch - 4
		return self.run_cmd_subs("select_amp", self.patch)

	@log_fn_call
	def next_effect_color(self, ev, name):
		"""
		Switches the specified effect to the next color in the cycle.
		"""
		effect = self.get_effect(name)
		if effect is None:
			return
		if not effect.has_color:
			logging.error("Effect has no color: %s", name)
			return
		# increment color value, looping to 0 after 2
		effect.color = 0 if effect.color >= 2 else effect.color + 1
		return self.run_cmd(name+"_color", effect.color)

	@log_fn_call
	def delay_tap(self, ev, name):
		"""
		Set the delay time for the specified delay effect to the time elapsed
		between two taps, up to an interval of 2 seconds.
		"""
		effect = self.get_effect(name)
		if effect is None:
			return
		if not effect.is_delay:
			logging.error("Effect is not a delay: %s", name)
			return
		# use whole milliseconds
		now = int(time.time() * 1000)
		# always store the new tap time
		last_tap = effect.last_tap
		effect.last_tap = now
		interval = now - last_tap
		# if first tap or > 2s since last tap, do nothing else
		if interval > 2000:
			return

		# clear last tap so a third tap starts new instead of interfering
		effect.last_tap = 0
		# get 11 digit binary representation
		interval_bin = "{:011b}".format(interval)
		# first four digits make the first value, the rest the second
		i_sub1 = int(interval_bin[:4], 2)
		i_sub2 = int('0'+interval_bin[4:], 2)
		return self.run_cmd_subs("delay_tap", effect.tap_opcode, i_sub1, i_sub2)

	@log_fn_call
	def select_preset(self, ev):
		"""
		We accept program change (PC) values 2-5. (The controller sends 1-4,
		which the Katana recognizes, but since `data_offset` is 1 so we can
		access the controller's listener channel 16 mididings sees them as 2-5.)
		"""
		patch = ev.program - 1
		if not 1 <= patch <= 4:
			logging.error("Invalid patch value: %d", patch)
			return
		if self.bank > 0:
			# upper bank is 5-8
			patch = patch + 4
		self.patch = patch
		return self.run_cmd_subs("select_amp", patch)

amp = Amp()


class Controller(object):
	"""
	FCB1010 MIDI controller w Wino2 firmware chipset.
	"""
	def __init__(self, bank=1, amp_bank=0, channel=16):
		self.bank = bank
		self.amp_bank = amp_bank
		self.port = engine.out_ports()[1]
		self.channel = channel

	def update_amp_bank(self, ev):
		self.amp_bank = ev.value

	def toggle_amp_bank(self, amp_bank):
		if self.amp_bank == amp_bank:
			return
		self.amp_bank = amp_bank
		LED_map = ctrl_LED_maps[self.bank]
		amp_bank_pedal = LED_map.get("amp_bank")
		if amp_bank_pedal is None:
			return
		logging.info("Sending PC %d to controller - amp_bank", amp_bank_pedal)
		output_event(event.ProgramEvent(self.port, self.channel, amp_bank_pedal))

	def update_bank(self, ev):
		self.bank = ev.value
		# get amp state so we can update controller LEDs as needed
		send_query_cmds(amp.port)

	def toggle_effect(self, effect):
		LED_map = ctrl_LED_maps[self.bank]
		effect_pedal = LED_map.get(effect.name)
		if effect_pedal is None:
			return
		logging.info("Sending PC %d to controller - %s", effect_pedal,
					 effect.name)
		output_event(event.ProgramEvent(self.port, self.channel, effect_pedal))

	def set_preset(self, preset):
		LED_map = ctrl_LED_maps[self.bank]
		preset_pedal = LED_map.get("presets")
		if preset_pedal is None:
			return
		preset_pedal = preset_pedal + preset - 1
		logging.info("Sending PC %d to controller - preset %d", preset_pedal,
					 preset)
		output_event(event.ProgramEvent(self.port, self.channel, preset_pedal))

ctrl = Controller()


class QueryProcessor(object):
	def increment_address(self, address):
		"""
		Increment the address after we process each data byte to get the
		address of the next data byte.
		"""
		last_addr_byte = address[-2:]
		if last_addr_byte != "7f":
			# add 1 to the last byte
			last_addr_byte = int(last_addr_byte,16)+1
			address = "{}{:02x}".format(address[:-2], last_addr_byte)
		else:
			# rolls over, need to increment the upper address byte
			last_addr_byte = "00"
			upper_addr_byte = address[-5:-3]
			upper_addr_byte = int(address[-5:-3],16)+1
			address = "{}{:02x} {}".format(
				address[:-5], upper_addr_byte, last_addr_byte)
		return address

	def process_query_result(self, ev):
		"""
		Parses and processes the SysEx events that the amp sends to get its
		state.
		"""
		hex_bytes = ' '.join('{:02x}'.format(x) for x in ev.sysex)
		logging.debug("SysEx event rec'd: %s", hex_bytes)

		# extract the starting address and an unknown number of data bytes
		start_address = hex_bytes[24:35]
		data_bytes = hex_bytes[36:-6].split()

		address = None
		last_addr_byte = None

		# iterate through the bytes and check each address
		for data_byte in data_bytes:
			if not address:
				# initialize
				address = start_address
				last_addr_byte = address[-2:]
			else:
				address = self.increment_address(address)

			# see if this byte's address maps to a known setting
			setting_name = addresses.get(address)
			if not setting_name:
				# no match, ignore it
				continue
			logging.info("Match: %s", setting_name)

			if setting_name == "patch_selected":
				patch = int(data_bytes[-1], 16)
				if amp.patch == patch:
					continue
				logging.info("patch: %d", patch)
				# update amp state
				amp.patch = patch
				# update controller `amp_bank` state
				amp_bank_of_patch = int(patch > 4)
				# `toggle_amp_bank` checks to see if they match so we don't
				# need to
				ctrl.toggle_amp_bank(amp_bank_of_patch)
				ctrl_preset = patch - 4	if amp_bank_of_patch else patch
				ctrl.set_preset(ctrl_preset)
				continue

			data_byte = int(data_byte, 16)
			effect_name, action = setting_name.rsplit("_", 1)
			effect = amp.get_effect(effect_name)
			if action == "color":
				# controller doesn't support colors so we just update
				# amp/effect state
				effect.color = data_byte
				continue

			if action == "on":
				# python equates 0 & 1 with True & False
				if effect.on == data_byte:
					continue
				# update amp/effect state
				effect.on = bool(data_byte)
				# update controller state
				ctrl.toggle_effect(effect)

qproc = QueryProcessor()


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
	send_query_cmds(ports[0])

start_new_thread(init, ())

run(
	# CC messages for various toggles, option cycling, and delay taps
	[
		Filter(CTRL) >> CtrlSplit({
			16: Process(amp.toggle_effect, "boost"),
			17: Process(amp.toggle_effect, "mod"),
			18: Process(amp.toggle_effect, "fx"),
			19: Process(amp.toggle_effect, "delay"),
			20: Process(amp.toggle_effect, "reverb"),
			21: Process(amp.toggle_effect, "delay2"),
			22: Process(amp.toggle_effect, "pedal_fx"),
			23: Process(amp.toggle_amp_bank),

			96: CtrlValueFilter(127) >> Process(amp.next_effect_color, "boost"),
			97: CtrlValueFilter(127) >> Process(amp.next_effect_color, "mod"),
			98: CtrlValueFilter(127) >> Process(amp.next_effect_color, "fx"),
			99: CtrlValueFilter(127) >> Process(amp.next_effect_color,
												 "reverb"),
			100: CtrlValueFilter(127) >> Process(amp.delay_tap, "delay"),
			101: CtrlValueFilter(127) >> Process(amp.delay_tap, "delay2"),

			102: Process(amp.toggle_effect, "solo"),

			103: CtrlValueFilter(127) >> Process(amp.next_effect_color,
												 "global_eq"),

			125: Process(ctrl.update_amp_bank),
			126: Call(ctrl.update_bank),
			None: Pass(),
			}),
		ProgramFilter([2, 3, 4, 5]) >> Process(amp.select_preset),
		# SysEx messages are query results back from the amp
		SysExFilter(manufacturer=0x41) >> Call(qproc.process_query_result),
		SysExFilter("\xf0\x7e") >> Call(qproc.process_query_result),
	]
	)
