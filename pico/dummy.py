from ktane import Module, Status

module = Module("dummy", status_led=(12,13,15), uart=(0,1))

@module.event
async def on_ready():
    print("DUMMY READY!")

@module.command(0x01)
async def dummy_on(tx, data):
    module.send(0x09, rx=0x00)
    module.status_led = Status.GREEN

module.run()