#using Pimoroni uf2
from ktane import Module, Status
from components import IO
import picographics as pg
import random
import time

module = Module("module2", status_led=(11,12,13), uart=(0,1))
btn = IO(22, "in", pull="up")
strip_leds = (IO(10, "pwm"), IO(9, "pwm"), IO(8, "pwm"))
display = pg.PicoGraphics(display=pg.DISPLAY_PICO_EXPLORER)
display.set_backlight(0)

PRESS_THRESHOLD = 500
BLUE = display.create_pen(52,164,235)
RED = display.create_pen(235,52,58)
YELLOW = display.create_pen(235,229,52)
WHITE = display.create_pen(255,255,255)
BLACK = display.create_pen(36,36,36) 
BTN_COLS = ((BLUE, WHITE), (RED, WHITE), (YELLOW, BLACK), (WHITE, BLACK), (BLACK, WHITE))
STRP_COLS = (Status.WHITE, Status.YELLOW, Status.BLUE, Status.MAGENTA, Status.RED, Status.GREEN)
TEXTS = ("ABORT", "DETONATE", "HOLD", "PRESS")

module.g["button_colours"] = (BLACK, BLACK)
module.g["button_text"] = ""
module.g["strip_colour"] = Status.OFF
module.g["start_timestamp"] = 0
module.g["on"] = False
module.g["defused"] = False

LABELS = ("SND", "CLR", "CAR", "IND", "FRQ", "SIG", "NSA", "MSA", "TRN", "BOB", "FRK")
module.g["labels"] = None
module.g["batteries"] = None
module.g["timer_time"] = None

@module.event
async def on_ready():
    print("READY!")
    module.register(btn)

@module.command(0x01)
async def turn_on(tx, data):
    module.g["on"] = True
    module.status_led = Status.OFF

    module.g["button_colours"] = random.choice(BTN_COLS)
    display.set_pen(module.g["button_colours"][0])
    display.clear()

    module.g["button_text"] = random.choice(TEXTS)
    display.set_pen(module.g["button_colours"][1])
    display.set_font("sans")
    display.set_thickness(3)
    scale = 2
    text_width = display.measure_text(module.g["button_text"], scale=scale)
    if text_width > 210:
        scale = 1.5
        text_width = display.measure_text(module.g["button_text"], scale=scale)
    w,h = display.get_bounds()
    display.text(module.g["button_text"], (w-text_width)//2, h//2, scale=scale)
    display.update()
    display.set_backlight(1)

@module.command(0x00)
async def turn_off(tx, data):
    module.g["on"] = False
    module.g["defused"] = False

    module.g["labels"] = None
    module.g["batteries"] = None
    module.g["timer_time"] = None

    display.set_backlight(0)
    for led in strip_leds:
        led.value(0)

@btn.listener("low")
async def btn_pressed():
    module.g["start_timestamp"] = time.ticks_ms()
    
    if not module.g["on"]: return
    
    module.g["strip_colour"] = random.choice(STRP_COLS)
    for l,v in zip(strip_leds, module.g["strip_colour"]):
        l.value(v, percentage=True)

@btn.listener("high")
async def btn_unpressed():
    if not module.g["on"] or module.g["defused"]: return
    if module.g["labels"] is None or module.g["batteries"] is None or module.g["timer_time"] is None: return

    for led in strip_leds:
        led.value(0)
    
    press_length = time.ticks_diff(time.ticks_ms(), module.g["start_timestamp"])
    colour = module.g["button_colours"][0]
    text = module.g["button_text"]
    batteries = module.g["batteries"]
    labels = module.g["labels"]
    strip = module.g["strip_colour"]
    timer = module.g["timer_time"]

    should_release = False
    if colour == RED and text == "HOLD":
        should_release = True
    if colour == YELLOW:
        should_release = False
    if batteries > 2 and "FRK" in labels:
        should_release = True
    if colour == WHITE and "CAR" in labels:
        should_release = False
    if batteries > 1 and text == "DETONATE":
        should_release = True
    if colour == BLUE and text == "ABORT":
        should_release = False
    
    if should_release:
        if press_length > PRESS_THRESHOLD:
            module.send(0x10, rx=0x00)
            return
        module.g["defused"] = True
        module.status_led = Status.GREEN
        module.send(0x09, rx=0x00)
        return
    
    number = "1"
    if strip == Status.BLUE:
        number = "4"
    if strip == Status.YELLOW:
        number = "5"
    
    if number in timer:
        module.g["defused"] = True
        module.status_led = Status.GREEN
        module.send(0x09, rx=0x00)
        return
    module.send(0x10, rx=0x00)

@module.command(0x11)
async def GET_labels(tx, data): module.g["labels"] = [LABELS[d] for d in data]

@module.command(0x13)
async def GET_batteries(tx, data): module.g["batteries"] = data[0]

@module.command(0x15)
async def GET_time(tx, data): module.g["timer_time"] = Module.bytes_to_string(data)

module.run()