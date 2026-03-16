import ktane
import components 
module = ktane.Module("module")

internal_led = components.IO(25)
btn = components.IO(15, "in", "down")
led = components.IO(17, is_pwm=True)

@module.event
async def on_ready():
    module.register(btn)

@module.task(freq=1000)
async def blink_led():
    internal_led.value(not internal_led.value())

    if btn.value():
        led.switch()

module.run()