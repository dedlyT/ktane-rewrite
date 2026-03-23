from ktane import Module

module = Module("module2", status_led=(11,12,13), uart=(0,1))

@module.event
async def on_ready():
    print("READY!")

@module.task(freq=1000)
async def modules():
    print(module.g)
    print(module.get_addresses())

module.run()