#using pico_i2c_lcd from github
from ktane import Module, Status
from components import IO
from pico_i2c_lcd import I2cLcd
import machine as m
import random
import time

module = Module("timer", status_led=(12,11,10), uart=(0,1))
lcd = I2cLcd(m.I2C(1, sda=m.Pin(26), scl=m.Pin(27), freq=400000), 0x27, 2, 16)
switch = IO(22, "in", pull="up")
strike_leds = (IO(21, "pwm"), IO(18, "pwm"), IO(17, "pwm"))
bzr = IO(16, "pwm", freq=500, duty_u16=1000)
btn = IO(15, "in", pull="up")

LABELS = ("SND", "CLR", "CAR", "IND", "FRQ", "SIG", "NSA", "MSA", "TRN", "BOB", "FRK")
MAX_STRIKES = len(strike_leds)
C7, B6, G6, C6, G5, E5, D5, C5, B5, A5, A4, G4, E4, D4, B4, AS3, A3, GS3, G3, E3, C3, P = 2093, 1976, 1568, 1047, 784, 659, 587, 523, 988, 880, 440, 392, 330, 294, 494, 233, 220, 208, 196, 165, 131, -1
FAIL_TUNE = [C7,C7,C7,C7,C7,B6,B6,B6,G6,G6,G6,C6,C6,G5,G5,E5,D5,C5,A4,G4,E4,D4,A3,A3,G3,G3,E3,E3,E3,C3,C3,C3]
AS4, GS4, F4, DS4, C4, F3, B3, F2 = 466, 415, 349, 311, 262, 175, 247, 87
WIN_TUNE = [AS4,GS4,F4,B4,C5,AS4,GS4,F4,E4,DS4,C4,AS3,GS3,F3,GS3,AS3,B3,C4,DS4,E4,E4,F4,F4,F4,F2,F2,F2,F2]
STR, BM, BZ1, BZ2, BZ3, DF = 0,1,2,3,4,5
STRIKE_MODIFIERS = ((BZ1, 1000), (BZ2, 750), (BZ3, 500), (0, 2000))

module.g["buzzer_queue"] = []
module.g["next_backlight_state"] = 0
module.g["next_buzz"] = time.ticks_ms()
module.g["next_second"] = time.ticks_ms()

module.g["last_on"] = switch.value()
module.g["on"] = not switch.value()
module.g["timer"] = {"m":1,"s":0}
module.g["strikes"] = 0
module.g["defused_modules"] = set()
module.g["has_boomed"] = False
module.g["characteristics"] = {"batteries":0, "lit_labels":[], "unlit_labels":[]}

@module.event
async def on_ready():
    print("READY!")
    module.register(switch)
    module.register(btn)
    module_on() if not switch.value() else module_off()

def module_off():
    module.send(0x00)
    module.g["on"] = False
    lcd.backlight_off()
    lcd.clear()
    for led in strike_leds:
        led.value(0)

def module_on():
    module.send(0x01)
    module.g["on"] = True
    module.g["has_boomed"] = False
    module.status_led = Status.OFF
    module.g["defused_modules"] = set()

    module.g["strikes"] = 0
    module.g["timer"] = {"m":1,"s":0}
    module.g["characteristics"]["batteries"] = random.randint(0,4)
    labels = list(LABELS)
    selected_labels = [labels.pop(random.randint(0, len(labels)-1)) for _ in range(random.randint(3,5))]
    module.g["characteristics"]["lit_labels"] = [selected_labels.pop() for _ in range(random.randint(0,len(selected_labels)))]
    module.g["characteristics"]["unlit_labels"] = selected_labels
    lcd.backlight_on()

    module.send(0x11, get_label_ids("lit"))
    module.send(0x13, module.g["characteristics"]["batteries"])
    broadcast_time()

@module.task()
async def main():
    if not module.is_registered: return
    if not module.g["on"]: return
    if not Module.time_has_elapsed(module.g["next_second"]): return
    module.g["next_second"] = (time.ticks_ms() + STRIKE_MODIFIERS[module.g["strikes"]][1])

    lcd.clear()

    if module.g["has_boomed"]:
        lcd.putstr("BOOM!")
        if Module.time_has_elapsed(module.g["next_backlight_state"]):
            module.g["on"] = False
        return
    
    if STR not in module.g["buzzer_queue"]:
        module.g["buzzer_queue"] = [(BZ1,BZ2,BZ3)[module.g["strikes"]-1]]*2

    s = module.g["timer"]["s"]-1
    m = module.g["timer"]["m"]
    if s < 0:
        s = 59
        m = module.g["timer"]["m"]-1
        if m < 0:
            m = 0
    module.g["timer"]["s"] = s
    module.g["timer"]["m"] = m

    broadcast_time()

    if m == 0 and s == 0:
        module.g["buzzer_queue"] = FAIL_TUNE
        module.g["has_boomed"] = True
        module.status_led = Status.RED
        module.send(0x00)
        module.g["next_backlight_state"] = (time.ticks_ms() + 2000)
    
    m = f"0{m}" if len(str(m)) != 2 else m
    s = f"0{s}" if len(str(s)) != 2 else s
    lcd.putstr(f"{m}:{s}|{module.g['characteristics']['batteries']}§|{' '.join(module.g['characteristics']['lit_labels'])}")

def get_label_ids(is_lit:str) -> bytearray:
    res = bytearray()
    for label in module.g["characteristics"][f"{is_lit}_labels"]:
        res.append(module.g["characteristics"][f"{is_lit}_labels"].index(label))
    return res

@switch.listener("high")
async def switch_off():
    module_off()

@switch.listener("low")
async def switch_on():
    module_on()

@module.command(0x10)
async def SET_strike(tx, data):
    if not module.g["on"]: return
    if module.g["has_boomed"]: return

    module.g["strikes"] = min(module.g["strikes"]+1, MAX_STRIKES)
    module.send(0x14, module.g["strikes"])
    
    strike_leds_values = [0.1]*module.g["strikes"] + [0]*(MAX_STRIKES - module.g["strikes"])
    for led,v in zip(strike_leds,strike_leds_values):
        led.value(v, percentage=True)
    
    module.g["buzzer_queue"] = [STR, STR, STR, STR, P, P, P, P, P]
    if module.g["strikes"] == MAX_STRIKES:
        module.g["has_boomed"] = True
        module.status_led = Status.RED
        module.send(0x00)
        module.g["next_backlight_state"] = (time.ticks_ms() + 1000)
        module.g["buzzer_queue"] += FAIL_TUNE
        return
    module.g["next_second"] = time.ticks_ms() + STRIKE_MODIFIERS[module.g["strikes"]][1]

@module.command(0x09)
async def SET_defused(tx, data):
    if not module.g["on"]: return
    if module.g["has_boomed"]: return

    module.g["defused_modules"].add(tx)
    buzzer_tune = [DF,DF,P,DF,DF,P,DF,DF,DF,DF]
    if len(module.g["defused_modules"]) >= len(module.g["modules"]):
        print("DEFUSED!")
        buzzer_tune = WIN_TUNE
        module.status_led = Status.GREEN
        module_off()
    module.g["buzzer_queue"] = buzzer_tune

@module.command(0x11)
async def GET_lit_labels(tx, data):
    module.send(0x11, get_label_ids("lit"), rx=tx)

@module.command(0x12)
async def GET_unlit_labels(tx, data):
    module.send(0x12, get_label_ids("unlit"), rx=tx)

@module.command(0x13)
async def GET_batteries(tx, data):
    module.send(0x13, module.g["characteristics"]["batteries"], rx=tx)

@module.task()
async def buzzer_queue():
    if not len(module.g["buzzer_queue"]):
        bzr.value(0)
        return
    if not Module.time_has_elapsed(module.g["next_buzz"]): return
    module.g["next_buzz"] = (time.ticks_ms() + 125)

    buzz = module.g["buzzer_queue"].pop(0)

    if buzz == P:
        bzr.value(0)
        return
    if buzz in (DF, BZ1, BZ2, BZ3, STR, BM):
        bzr.value(0.5, percentage=True)
        if buzz == BZ1:
            freq = 1100
        if buzz == BZ2:
            freq = 1500
        if buzz == BZ3:
            freq = 1000
        if buzz == STR:
            freq = 3000
        if buzz == BM:
            freq = 5000
        if buzz == DF:
            freq = 4000
        bzr.freq(freq)
        return

    bzr.value(1000)
    bzr.freq(buzz)

def broadcast_time():
    m,s = module.g["timer"]["m"], module.g["timer"]["s"]
    data = bytearray()
    data.append(0x00)
    data.append(ord(str(m)))
    data.append(ord("."))
    seconds = str(s)
    data.append(ord(seconds[0]))
    if len(seconds) == 2:
        data.append(ord(seconds[1]))
    module.send(0x15, data)

module.run()