from ktane import Module, Status
from components import IO
import random
import time

module = Module("simonsays", status_led=(12,13,15), uart=(0,1))

leds = {
    "red": IO(10),
    "yellow": IO(11),
    "green": IO(9),
    "blue": IO(8)
}
btns = {
    "red": IO(2, "in", pull="up"),
    "yellow": IO(4, "in", pull="up"),
    "green": IO(3, "in", pull="up"),
    "blue": IO(5, "in", pull="up")
}

VFX_DELAY = 2000
VFX_ON_TIME = 750
VFX_OFF_TIME = 500
VFX_END_TIME = 3000

#TRANSLATION_TABLE[SERIAL # HAS VOWELS][STRIKES][VFX COLOUR] = ANSWER
TRANSLATION_TABLE = (
    ({"red":"blue", "blue":"red", "green":"yellow", "yellow":"green"},
     {"red":"yellow", "blue":"green", "green":"blue", "yellow":"red"},
     {"red":"green", "blue":"red", "green":"yellow", "yellow":"blue"}),
    ({"red":"blue", "blue":"red", "green":"yellow", "yellow":"green"},
     {"red":"yellow", "blue":"green", "green":"blue", "yellow":"red"},
     {"red":"green", "blue":"red", "green":"yellow", "yellow":"blue"})
)

module.g["on"] = False
module.g["defused"] = False

module.g["vfx_answer"] = []
module.g["answer"] = None
module.g["input"] = None
module.g["vfx_leds"] = []
module.g["last_pressed_timestamp"] = 0
module.g["next_vfx_timestamp"] = 0
module.g["vfx_pos"] = 0
module.g["vfx_on"] = False

module.g["strikes"] = 0
module.g["serial"] = None

@module.event
async def on_ready():
    print("READY!")
    for btn in btns.values():
        module.register(btn)
        btn.value(0)

@module.command(0x01)
async def turn_on(tx, data):
    module.g["on"] = True
    module.g["defused"] = False
    module.status_led = Status.OFF

    module.g["next_vfx_timestamp"] = (time.ticks_ms() + 500)
    module.g["last_pressed_timestamp"] = 0

    module.g["vfx_answer"] = [random.choice(list(btns.keys())) for _ in range(random.randint(4,6))]
    module.g["answer"] = None

@module.command(0x00)
async def turn_off(tx, data):
    module.g["on"] = False
    module.g["strikes"] = 0
    module.g["vfx_leds"] = []
    for led in leds.values():
        led.value(0)

@module.task()
async def main():
    if not module.g["on"] or module.g["defused"]: return
    if module.g["strikes"] is None or module.g["serial"] is None: return
    if module.g["answer"] is None:
        recalculate_answers()

    for colour in leds.keys():
        btn_value = not btns[colour].value()
        leds[colour].value(btn_value or colour in module.g["vfx_leds"])

        if btn_value:
            module.g["last_pressed_timestamp"] = time.ticks_ms()

def press_dispatch(colour):
    if not module.g["on"] or module.g["defused"]: return
    if module.g["strikes"] is None or module.g["serial"] is None: return

    module.g["input"] = module.g["input"] or []
    module.g["input"].append(colour)

    if module.g["answer"][len(module.g["input"])-1] != colour:
        module.send(0x10, rx=0x00)
        module.g["strikes"] += 1
        recalculate_answers()
        
    if module.g["input"] == module.g["answer"]:
        module.send(0x09, rx=0x00)
        print("DEFUSED!")
        module.g["defused"] = True
        module.status_led = Status.GREEN

rbtn,ybtn,gbtn,bbtn = btns["red"],btns["yellow"],btns["green"],btns["blue"]
@rbtn.listener("low")
async def press_red():
    press_dispatch("red")

@ybtn.listener("low")
async def press_yellow():
    press_dispatch("yellow")

@gbtn.listener("low")
async def press_green():
    press_dispatch("green")

@bbtn.listener("low")
async def press_blue():
    press_dispatch("blue")

@module.task()
async def play_vfx():
    if not module.g["on"] or module.g["defused"]: return
    if module.g["strikes"] is None or module.g["serial"] is None: return
    
    if time.ticks_diff(time.ticks_ms(), module.g["last_pressed_timestamp"]) < VFX_DELAY: 
        module.g["vfx_pos"] = 0
        module.g["vfx_on"] = False
        return
    
    if module.g["input"] is not None:
        module.g["input"] = None
    
    if not Module.time_has_elapsed(module.g["next_vfx_timestamp"]): return

    module.g["vfx_on"] = not module.g["vfx_on"]
    next_gap = (VFX_OFF_TIME, VFX_ON_TIME)[module.g["vfx_on"]]
    if not module.g["vfx_on"]:
        module.g["vfx_pos"] += 1
        if module.g["vfx_pos"] >= len(module.g["vfx_answer"]):
            next_gap = VFX_END_TIME
            module.g["vfx_pos"] = 0
            
    colour = module.g["vfx_answer"][module.g["vfx_pos"]]
    module.g["vfx_leds"] = [colour] if module.g["vfx_on"] else []

    module.g["next_vfx_timestamp"] = (time.ticks_ms() + next_gap)

@module.command(0x14)
async def GET_strikes(tx, data):
    module.g["strikes"] = data[0]
    recalculate_answers()

@module.command(0x16)
async def GET_serial(tx, data):
    module.g["serial"] = Module.bytes_to_string(data)

def recalculate_answers():
    has_vowel = any(char in module.g["serial"] for char in "AEIOU")
    module.g["answer"] = [TRANSLATION_TABLE[has_vowel][module.g["strikes"]][colour] for colour in module.g["vfx_answer"]]

module.run()