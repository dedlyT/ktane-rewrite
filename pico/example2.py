from ktane import Module, Status

module = Module("module2", status_led=(11,12,13), uart=(0,1))
TIMER = 0x00

@module.event
async def on_ready():
    print("READY!")

@module.task()
async def control_status():
    if not module.is_registered: return
    if module.g["modules"].get(TIMER) is None: return
    if module.g["modules"][TIMER]["int_data"].get(0x00) is None:
        module.query_variables(TIMER)
        return
    
    counter = module.g["modules"][TIMER]["int_data"].get(0x00)
    if counter is None: return   

    status = (Status.YELLOW, Status.ORANGE, Status.RED)[counter]
    module.status_led = status

module.run()