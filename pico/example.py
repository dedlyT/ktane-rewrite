import ktane

module = ktane.Module("test")

@module.event
async def on_ready():
    print("Module ready!")

@module.event
async def on_second_passed():
    print("TICK")

module.run()