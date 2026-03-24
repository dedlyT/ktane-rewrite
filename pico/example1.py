from ktane import Module, Status, Bytes
from components import IO

module = Module("timer", status_led=(10,11,12), uart=(0,1))
led = IO(25)
btn = IO(16, "in", pull="down")
module.g["counter"] = 0

@module.event
async def on_ready():
    module.register(btn)
    print("READY!")

@module.task()
async def control_status():
    if not module.is_registered: return

    led.value(btn.value())
    status = (Status.YELLOW, Status.ORANGE, Status.RED)[module.g["counter"]]
    module.status_led = status

@module.command(Bytes.REG_QUERY)
async def extra_info(tx, data):
    module.send(Bytes.REG_INT, (0x00, module.g["counter"]))

@btn.listener("high")
async def press():
    module.g["counter"] = (module.g["counter"] + 1) % 3
    module.send(Bytes.REG_INT, (0x00, module.g["counter"]))

module.run()