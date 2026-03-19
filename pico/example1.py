from ktane import Module
from components import IO
import random

module = Module(status_led=(12,13,15), uart=(0,1))
btn = IO(16, "in", pull="down")

@module.event
async def on_ready():
    module.register(btn)

@btn.listener("high")
async def send_message():
    msg = random.choice(["Hello!", "Dia duit!", "Bonjour!", "Guten tag!", "Hallo!"])
    module.send(0x01, msg)

module.run()