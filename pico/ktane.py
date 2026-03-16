from components import IO
import uasyncio
import time

async def __empty(*a, **kw): pass

async def __empty(*a, **kw): pass

class Module:
    ALLOWED_EVENTS = (
        "on_ready",
        "on_second_passed",
        "on_minute_passed",
        "on_hour_passed"
    )
    ALLOWED_COMPONENTS = (IO,)

    def __init__(self, name, status_led):
        self.g = {}
        self.__name = name
        self.__event_hooks = dict.fromkeys(self.ALLOWED_EVENTS, __empty)
        self.__event_queue = []
        self.__tasks = []
        self.__time_timer = 0
        self.__status_led = tuple(IO(pin) for pin in status_led)
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

    def set_status_led(self, values):
        for led,v in zip(self.__status_led, values):
            led.value(v)

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