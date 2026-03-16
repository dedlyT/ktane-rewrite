from ktane import Module
from components import IO

module = Module("module")

internal_led = IO(25)
btn = IO(15, "in", pull="down")
led = IO(17, "pwm")

@module.event
async def on_ready():
    module.register(btn)

@module.task(freq=1000)
async def blink_led():
    internal_led.value(not internal_led.value())

    if "led_value" in module.g:
        print("HOLD!")

@btn.listener("high")
async def blinking_start():
    print("PRESS!")
    module.g["led_value"] = 1

@btn.listener("while_high")
async def blink():
    module.g["led_value"] -= 0.01
    if module.g["led_value"] < 0:
        module.g["led_value"] = 1
    led.value(module.g["led_value"], percentage=True)

@btn.listener("low")
async def blinking_cleanup():
    print("UNPRESS!")
    del module.g["led_value"]
    led.value(0)

module.run()