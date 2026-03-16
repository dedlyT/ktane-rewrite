import machine as m
import uasyncio
import time

async def __empty(*a, **kw): pass

class Module:
    ALLOWED_EVENTS = [
        "on_ready",
        "on_second_passed",
        "on_minute_passed",
        "on_hour_passed"
    ]

    def __init__(self, name):
        self.__name = name
        self.__event_hooks = dict.fromkeys(self.ALLOWED_EVENTS, __empty)
        self.__event_queue = []
        self.__tasks = []
        self.__time_timer = 0
        self.__time = {u:0 for u in "smh"}
    
    #DECORATOR
    def event(self, f):
        if f.__name__ in self.ALLOWED_EVENTS:
            self.__event_hooks[f.__name__] = f
        
    def task(self, *args, **kwargs):
        def wrap(f):
            freq = kwargs.get("freq", 10)
            next_time = (time.ticks_ms()+freq) if kwargs.get("on_start", False) else 0
            self.__tasks.append({"freq":freq, "callback":f, "next":next_time})
        return wrap
    
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

                self.__event_queue.append(lambda: self.__event_hooks["on_second_passed"](self.__time))
                if m != old_time["m"]: self.__event_queue.append(lambda: self.__event_hooks["on_minute_passed"](self.__time))
                if h != old_time["h"]: self.__event_queue.append(lambda: self.__event_hooks["on_hour_passed"](self.__time))

    async def __start(self):
        uasyncio.create_task(self.__task_handler())
        uasyncio.create_task(self.__event_listener())
        uasyncio.create_task(self.__event_handler())
        await uasyncio.Event().wait()

    def run(self):
        uasyncio.run(self.__start())

    @property
    def name(self):
        return self.__name