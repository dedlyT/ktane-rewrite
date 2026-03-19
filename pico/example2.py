from ktane import Module

module = Module(status_led=(11,12,13), uart=(0,1))

@module.event
async def on_command_received(tx, cmd, data):
    print(f"{tx=} {cmd=} {data=}")

@module.command(0x01)
async def print_message(tx, data):
    msg = "".join(list(map(chr, data)))
    print(f"{msg} --- FROM {tx}")

module.run()