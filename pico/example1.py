from ktane import Module
from components import IO
import random

module = Module("timer", status_led=(12,13,15), uart=(0,1))
led = IO(25)
btn = IO(16, "in", pull="down")
module.g["last_value"] = None
module.g["linked_id"] = None

@module.event
async def on_ready():
    print("DONE!")
    module.register(btn)

@btn.listener("high")
async def link_high():
    print("PRESS")
    led.value(1)
    module.send(0x00, 1, rx=module.g["linked_id"])

@btn.listener("low")
async def link_low():
    print("UNPRESS")
    led.value(0)
    module.send(0x00, 0, rx=module.g["linked_id"])
    module.g["linked_id"] = random.choice(list(module.g["modules"].keys()))

@module.command(0x00)
async def link(tx, v):
    led.value(v)

module.run()