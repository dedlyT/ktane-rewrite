from ktane import Module
from components import IO
from pico_i2c_lcd import I2cLcd
import machine as m

module = Module("timer", status_led=(12,11,10), uart=(0,1))
i2c = m.I2C(1, sda=m.Pin(26), scl=m.Pin(27), freq=400000)
lcd = I2cLcd(i2c, 0x27, 2, 16)
switch = IO(22, "in", pull="up")

@module.event
async def on_ready():
    print("READY!")
    module.register(switch)
    module.g["timer"] = {"m":0,"s":10}

@module.event
async def on_second_passed(t):
    if not module.is_registered: return
    lcd.clear()

    if module.g["timer"] == {"m":0,"s":0}:
        lcd.putstr("BOOM!")
        return

    s = module.g["timer"]["s"]-1
    m = module.g["timer"]["m"]
    if s < 0:
        s = 59
        m = module.g["timer"]["m"]-1
        if m < 0:
            m = 0
    module.g["timer"]["s"] = s
    module.g["timer"]["m"] = m
    
    m = f"0{m}" if len(str(m)) != 2 else m
    s = f"0{s}" if len(str(s)) != 2 else s
    lcd.putstr(f"{m}:{s}")

@switch.listener("high")
async def switch_low():
    print("HIGH")

@switch.listener("low")
async def switch_low():
    print("LOW")

module.run()