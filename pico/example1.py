from ktane import Module

module = Module("timer", status_led=(10,11,12), uart=(0,1))

@module.event
async def on_ready():
    print("READY!")

@module.task(freq=1000)
async def modules():
    print(module.g)
    print(module.get_addresses())

module.run()