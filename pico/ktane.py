from components import IO
import machine as m
import uasyncio
import random
import time

START_BYTE = 0xAA
RX_GLOBAL_BYTE = 0xEE
CMD = 2
RX = 3
TX = 4
LEN = 5
CHKSUM = lambda cmd,rx,tx,len,data: (cmd+rx+tx+len+sum(data)) & 0xFF

async def __empty(*a, **kw): pass

class Module:
    ALLOWED_EVENTS = (
        "on_ready",
        "on_second_passed",
        "on_minute_passed",
        "on_hour_passed",
        "on_command_received"
    )
    ALLOWED_COMPONENTS = (IO,)

    def __init__(self, **kwargs):
        self.g = {}

        self.__id = None
        while self.__id in (None, START_BYTE, RX_GLOBAL_BYTE):
            self.__id = random.randint(0,255)
        
        self.__event_hooks = dict.fromkeys(self.ALLOWED_EVENTS, __empty)
        self.__event_queue = []
        self.__command_hooks = {}
        self.__tasks = []
        self.__time_timer = 0

        status_led = kwargs.get("status_led")
        if status_led is None: 
            raise ValueError("Module missing status_led keyword argument")
        if not isinstance(status_led, (list,tuple)) or not all(isinstance(x, int) for x in status_led):
            raise ValueError("status_led must be a tuple of ints!")
        self.__status_led = tuple(IO(pin) for pin in status_led)
        
        uart = kwargs.get("uart")
        if uart is None: 
            raise ValueError("Module missing uart keyword argument")
        if not isinstance(uart, (list,tuple)) or not all(isinstance(x, int) for x in status_led):
            raise ValueError("uart must be a tuple of ints!")
        self.__uart = m.UART(0, baudrate=9000, tx=m.Pin(uart[0]), rx=m.Pin(uart[1]))
        self.__uart_data = {"DATA":[], "CMD":None, "LEN":None, "RX":None, "TX":None, "POS":0}

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
    
    #DECORATOR
    def command(self, *args, **kwargs):
        def wrap(f):
            byte = args[0]
            self.__command_hooks[byte] = f
        return wrap

    def register(self, obj):
        if type(obj) not in self.ALLOWED_COMPONENTS:
            raise ValueError(f"obj must be an allowed type, not {type(obj)}")
        self.__components.append({"obj":obj, "last":False})

    def set_status_led(self, values):
        for led,v in zip(self.__status_led, values):
            led.value(v)
    
    #[START][CMD][RX][TX][LEN][DATA][CHK]
    def send(self, cmd, data=None, **kwargs):
        packet = bytearray()
        packet.append(START_BYTE) #[START]

        if not isinstance(cmd, int):
            raise TypeError(f"cmd must be int, not {type(cmd)}")
        if cmd < 0x00 or cmd > 0xFF:
            raise ValueError("cmd must be single-byte hexadecimal!")
        if cmd == START_BYTE:
            raise ValueError(f"cmd must not be reserved hexadecimal byte {START_BYTE}")
        packet.append(cmd) #[CMD]
        
        rx = kwargs.get("rx")
        if rx is None:
            rx = RX_GLOBAL_BYTE
        if not isinstance(rx, int):
            raise TypeError(f"rx must be int, not {type(rx)}")
        if rx < 0x00 or rx > 0xFF:
            raise ValueError("rx must be single-byte hexadecimal!")
        if rx == START_BYTE:
            raise ValueError(f"rx must not be reserved hexadecimal byte {START_BYTE}")
        packet.append(rx) #[RX]
        
        packet.append(self.__id) #[TX]

        if data is None:
            data = []
        if not isinstance(data, (list, tuple, str)):
            data = [data]
        
        final_data = bytearray()
        for item in data:
            if isinstance(item, str):
                item = ord(item)
                if item < 0x00 or item > 0xFF:
                    raise ValueError(f"ascii character '{chr(item)}' hexadecimal ({item}) must be one byte")
                if item == START_BYTE:
                    raise ValueError(f"ascii character '{chr(item)}' hexadecimal cannot be reserved byte {START_BYTE}")
                final_data.append(item)
                continue
            if isinstance(item, int):
                if item < 0x00 or item > 0xFF:
                    raise ValueError("hexadecimal int must be one byte")
                final_data.append(item)
                continue
            raise ValueError(f"data can only be hexadecimal int or ascii character, not {type(item)}")

        packet.append(len(final_data)) #[LEN]
        if final_data != []:
            packet.extend(final_data) #[DATA]

        checksum = CHKSUM(cmd, rx, self.__id, len(final_data), final_data)
        packet.append(checksum) #[CHK]

        self.__uart.write(packet)

    async def __uart_listener(self):
        while True:
            await uasyncio.sleep_ms(1)
            if not self.__uart.any(): continue
            byte = self.__uart.read(1)[0]

            if not self.__uart_data["POS"]:
                if byte == START_BYTE:
                    self.__uart_data["POS"] += 1
                    continue
            self.__uart_data["POS"] += 1

            key = None
            if self.__uart_data["POS"] == CMD:
                key = "CMD"
            if self.__uart_data["POS"] == RX:
                key = "RX"
            if self.__uart_data["POS"] == TX:
                key = "TX"
            if self.__uart_data["POS"] == LEN:
                key = "LEN"
            if key is not None:
                self.__uart_data[key] = byte
            
            if key is None and self.__uart_data["LEN"] is not None:
                if self.__uart_data["POS"] > (LEN + self.__uart_data["LEN"]):
                    checksum = CHKSUM(self.__uart_data["CMD"], self.__uart_data["RX"], self.__uart_data["TX"], self.__uart_data["LEN"], self.__uart_data["DATA"])
                    if byte != checksum:
                        print(f"DISCARD! {byte=} {checksum=} {self.__uart_data=}")
                        self.__uart_data = {"DATA":[], "CMD":None, "LEN":None, "RX":None, "TX":None, "POS":0}
                        continue

                    cmd = self.__uart_data["CMD"]
                    tx = self.__uart_data["TX"]
                    data = self.__uart_data["DATA"].copy()
                    self.__event_queue.append(lambda cmd=cmd, tx=tx, data=data: self.__command_hooks.get(cmd, __empty)(tx, data))
                    self.__event_queue.append(lambda cmd=cmd, tx=tx, data=data: self.__event_hooks["on_command_received"](tx, cmd, data))

                    self.__uart_data = {"DATA":[], "CMD":None, "LEN":None, "RX":None, "TX":None, "POS":0}
                    continue
                self.__uart_data["DATA"].append(byte)

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

                self.__event_queue.append(lambda time=self.__time: self.__event_hooks["on_second_passed"](time))
                if m != old_time["m"]: self.__event_queue.append(lambda time=self.__time: self.__event_hooks["on_minute_passed"](time))
                if h != old_time["h"]: self.__event_queue.append(lambda time=self.__time: self.__event_hooks["on_hour_passed"](time))

    async def __start(self):
        uasyncio.create_task(self.__uart_listener())
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