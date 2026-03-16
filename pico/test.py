import machine as m
import uasyncio
import time

async def __empty(*a, **kw): pass

class IO:
    MAX_U16 = 65535
    LISTENERS = ("high", "while_high", "low", "while_low")
    
    def __init__(self, pin, *args, **kwargs):
        if len(args) == 0: args = ["out"]
        self._mode = args[0]
        print(self._mode)

        if self._mode == "pwm":
            freq = kwargs.get("freq", 50)
            if not isinstance(freq, int):
                raise TypeError(f"freq must be int, not {type(freq)}")
            
            duty_u16 = kwargs.get("duty_u16", None)
            if duty_u16 is not None and not isinstance(duty_u16, int):
                    raise TypeError(f"duty_u16 must be int, not {type(duty_u16)}")

            if duty_u16 is None:
                duty_cycle = kwargs.get("duty_cycle", 0.125)
                if not isinstance(duty_cycle, float):
                    raise TypeError(f"duty_cycle must be float, not {type(duty_cycle)}")
                if (duty_cycle > 1 or duty_cycle < 0):
                    raise ValueError("duty_cycle must be between 1 and 0")
                duty_u16 = int(round(duty_cycle * self.MAX_U16))
            
            self.__obj = m.PWM(pin, freq=freq, duty_u16=duty_u16)
            self.value(0, percentage=True)
            return
        
        self.__listeners = dict.fromkeys(self.LISTENERS, __empty)

        if self._mode in ("in", 0, m.Pin.IN):
            self._mode = m.Pin.IN

            pull = kwargs.get("pull", None)
            if pull is None: raise ValueError("pull must be defined!")
            if pull in ("up", 1, m.Pin.PULL_UP): self._pull = m.Pin.PULL_UP
            if pull in ("down", 0, m.Pin.PULL_DOWN): self._pull = m.Pin.PULL_DOWN
            if self._pull not in (m.Pin.PULL_UP, m.Pin.PULL_DOWN): raise ValueError(f"pull must be either 'up' or 'down', not {pull}")

            self.__obj = m.Pin(pin, mode=self._mode, pull=self._pull)
        
        if self._mode in ("out", 1, m.Pin.OUT):
            self._mode = m.Pin.OUT
            self.__obj = m.Pin(pin, mode=self._mode)

        if self._mode not in (m.Pin.IN, m.Pin.OUT): raise ValueError(f"mode must be either 'in', 'out' or 'pwm', not {self._mode}")
    
    #DECORATOR
    def listener(self, event):
        def wrap(f):
            if self._mode == "pwm":
                raise RuntimeError("Cannot register listener for IO configured as PWM")
            if event not in self.LISTENERS:
                raise ValueError(f"{event} is not a valid listener!")
            self.__listeners[event] = f
        return wrap
    
    def get_listener(self, event):
        if event not in self.LISTENERS:
            raise ValueError(f"{event} is not a valid listener!")
        return self.__listeners[event]
        
    def switch(self):
        if self._mode == "pwm":
            self.value(not self.value(), percentage=True)
            return
        if self._mode == m.Pin.IN:
            raise RuntimeError(f"Cannot switch IO configured as 'in'!")
        self.value(not self.value())

    def value(self, v=None, **kwargs):
        if self._mode == "pwm":
            percentage = kwargs.get("percentage", False)

            if v is None:
                if percentage:
                    return (self.__obj.duty_u16() / self.MAX_U16)
                return self.__obj.duty_u16()
            
            if percentage:
                if (v > 1 or v < 0):
                    raise ValueError("v percentage must be between 1 and 0")
                v = int(round(self.MAX_U16 * v))
            
            if not isinstance(v, int):
                raise TypeError(f"v must be int, not {type(v)}")
            if (v > self.MAX_U16 or v < 0):
                raise ValueError(f"v must be between {self.MAX_U16} and 0")
            self.__obj.duty_u16(v)
            return

        if v is None:
            return self.__obj.value()
        
        if v not in (0, 1, False, True): raise ValueError(f"v must be either True or False, not {v}")
        self.__obj.value(v)

class Module:
    ALLOWED_EVENTS = (
        "on_ready",
        "on_second_passed",
        "on_minute_passed",
        "on_hour_passed"
    )
    ALLOWED_COMPONENTS = (IO,)

    def __init__(self, name):
        self.g = {}
        self.__name = name
        self.__event_hooks = dict.fromkeys(self.ALLOWED_EVENTS, __empty)
        self.__event_queue = []
        self.__tasks = []
        self.__time_timer = 0
        self.__time = {u:0 for u in "smh"}
        self.__components = []
    
    #DECORATOR
    def event(self, f):
        if f.__name__ in self.ALLOWED_EVENTS:
            self.__event_hooks[f.__name__] = f
    
    #DECORATOR
    def task(self, *args, **kwargs):
        def wrap(f):
            freq = kwargs.get("freq", 10)
            next_time = (time.ticks_ms()+freq) if kwargs.get("on_start", False) else 0
            self.__tasks.append({"freq":freq, "callback":f, "next":next_time})
        return wrap
    
    def register(self, obj):
        if type(obj) not in self.ALLOWED_COMPONENTS:
            raise ValueError(f"obj must be an allowed type, not {type(obj)}")
        self.__components.append({"obj":obj, "last":False})

    async def __event_handler(self):
        while True:
            await uasyncio.sleep_ms(1)
            if not len(self.__event_queue): continue
            
            event = self.__event_queue.pop(0)
            await event()

    async def __task_handler(self):
        while True:
            await uasyncio.sleep_ms(1)
            if not len(self.__tasks): continue

            task = self.__tasks.pop(0)
            if time.ticks_diff(task["next"], time.ticks_ms()) <= 0:
                task["next"] = (time.ticks_ms()+task["freq"])
                await task["callback"]()
            self.__tasks.append(task)
    
    async def __listener_handler(self):
        while True:
            await uasyncio.sleep_ms(1)
            if not len(self.__components): continue

            component_data = self.__components.pop(0)
            component = component_data["obj"]
            value = component.value()
            listener = "high" if value else "low"

            last_value = component_data["last"]
            if last_value != value:
                component_data["last"] = value
                await component.get_listener(listener)()
            
            await component.get_listener(f"while_{listener}")()

            self.__components = [component_data] + self.__components

    async def __event_listener(self):
        self.__event_queue.append(self.__event_hooks["on_ready"])
        while True:
            await uasyncio.sleep_ms(1)
            current_ticks = time.ticks_ms()

            if time.ticks_diff(self.__time_timer, current_ticks) <= 0:
                self.__time_timer = (time.ticks_ms()+1000)

                m_carry, s = divmod(self.__time["s"]+1, 60)
                h_carry, m = divmod(self.__time["m"]+m_carry, 60)
                h = self.__time["h"] + h_carry

                old_time = self.__time.copy()
                self.__time = {"s":s, "m":m, "h":h}
                self.g["time"] = self.__time.copy()

                self.__event_queue.append(lambda: self.__event_hooks["on_second_passed"](self.__time))
                if m != old_time["m"]: self.__event_queue.append(lambda: self.__event_hooks["on_minute_passed"](self.__time))
                if h != old_time["h"]: self.__event_queue.append(lambda: self.__event_hooks["on_hour_passed"](self.__time))

    async def __start(self):
        uasyncio.create_task(self.__task_handler())
        uasyncio.create_task(self.__event_listener())
        uasyncio.create_task(self.__event_handler())
        uasyncio.create_task(self.__listener_handler())
        await uasyncio.Event().wait()

    def run(self):
        uasyncio.run(self.__start())

    @property
    def name(self):
        return self.__name

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