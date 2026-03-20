from ktane import Module
from components import IO

module = Module("module3", status_led=(11,12,13), uart=(0,1))
led = IO(25)

@module.command(0x00)
async def link(tx, v):
    led.value(v[0])

module.run()