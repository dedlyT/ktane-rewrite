from components import IO
import machine as m
import uasyncio
import random
import time

CMD, RX, TX, LEN = 2,3,4,5
CHKSUM = lambda cmd,rx,tx,len,data: (cmd+rx+tx+len+sum(data)) & 0xFF
REG_TIMEOUT = 1000
HEARTBEAT_TIME = 2000
HEARTBEAT_TIMEOUT = 3000

#custom implementation of collections.defaultdict
class defaultdict(dict):
    def __init__(self, default_factory, *a, **kw):
        super(defaultdict, self).__init__(*a, **kw)
        self.default_factory = default_factory
    
    def __getitem__(self, k):
        if k not in self:
            self[k] = self.default_factory()
        return super(defaultdict, self).__getitem__(k)

#enum Status for status_led colours
class Status:
    RED = (1,0,0)
    ORANGE = (1,0.25,0)
    YELLOW = (1,1,0)
    GREEN = (0,1,0)
    CYAN = (0,1,1)
    BLUE = (0,0,1)
    MAGENTA = (1,0,1)
    PURPLE = (0.5,0,1)
    LILAC = (1,0,0.5)
    WHITE = (1,1,1)
    OFF = (0,0,0)

    @classmethod
    def validate(cls, v):
        if v not in Status.__dict__.values():
            raise ValueError(f"{v} not a valid enum")
        return v
    
class Bytes:
    START = 0xAA
    RX_GLOBAL = 0xEE
    REG_ATTEMPT = 0xBA
    REG_FAIL = 0xBF
    REG_QUERY = 0xBC
    REG_VARS_QUERY = 0xBE
    REG_TYPE = 0xCA
    REG_STR = 0xCB
    REG_INT = 0xCC
    HEARTBEAT = 0xBD

async def __empty(*a, **kw): pass

def generate_temp_id() -> int:
    temp_id = None
    while temp_id in (None, Bytes.START, Bytes.RX_GLOBAL):
        temp_id = random.randint(1,255)
    return temp_id

def default_uart_data() -> dict:
    return {"DATA":bytearray(), "CMD":None, "LEN":None, "RX":None, "TX":None, "POS":0}

class Module:
    ALLOWED_EVENTS = (
        "on_ready",
        "on_second_passed",
        "on_minute_passed",
        "on_hour_passed",
        "on_command_received"
    )
    ALLOWED_COMPONENTS = (IO,)

    def __init__(self, name:str, **kwargs):
        self.__name = name
        self.__components = []

        self.__g = {}
        self.g["modules"] = defaultdict(dict)
        self.__alive_modules = set()

        self.__next = defaultdict(time.ticks_ms)
        self.__next["cleanup"] += HEARTBEAT_TIMEOUT
        self.__next["time"] += 1000

        self.__event_hooks = dict.fromkeys(self.ALLOWED_EVENTS, __empty)
        self.__event_queue = []
        self.__command_hooks = {}
        self.__tasks = []

        status_led = kwargs.get("status_led")
        if status_led is None: 
            raise ValueError("Module missing status_led keyword argument")
        if not isinstance(status_led, (list,tuple)) or not all(isinstance(x, int) for x in status_led):
            raise ValueError("status_led must be a tuple of ints!")
        self.__status_led_objs = tuple(IO(pin, "pwm") for pin in status_led)
        self.__status_led = Status.OFF
        
        uart = kwargs.get("uart")
        if uart is None: 
            raise ValueError("Module missing uart keyword argument")
        if not isinstance(uart, (list,tuple)) or not all(isinstance(x, int) for x in status_led):
            raise ValueError("uart must be a tuple of ints!")
        self.__uart_obj = m.UART(0, baudrate=9000, tx=m.Pin(uart[0]), rx=m.Pin(uart[1]))
        self.__uart_data = default_uart_data()

        self.__time = {u:0 for u in "smh"}
        
    #DECORATOR register event hook
    def event(self, f:function) -> None:
        if f.__name__ in self.ALLOWED_EVENTS:
            self.__event_hooks[f.__name__] = f
    
    #DECORATOR register task
    def task(self, **kwargs) -> function:
        def wrap(f:function) -> None:
            freq = kwargs.get("freq", 10)
            next_time = (time.ticks_ms()+freq) if kwargs.get("on_start", False) else 0
            self.__tasks.append({"freq":freq, "callback":f, "next":next_time})
        return wrap
    
    #DECORATOR register command hook
    def command(self, byte:int) -> function:
        def wrap(f:function) -> None:
            if not isinstance(byte, int) or (byte > 255 or byte < 0):
                raise ValueError("Command hook byte must be hexadecimal integer!")
            self.__command_hooks[byte] = f
        return wrap
    
    #register component for listeners!
    def register(self, obj:IO) -> None:
        if type(obj) not in self.ALLOWED_COMPONENTS:
            raise ValueError(f"obj must be an allowed type, not {type(obj)}")
        self.__components.append({"obj":obj, "last":False})

    #set status led to custom values
    def set_status_led(self, values:tuple[int]) -> None:
        for led,v in zip(self.__status_led_objs, values):
            led.value(v, percentage=True)
    
    def query_variables(self, address:int) -> None:
        if not isinstance(address, int) or (address > 0xFF or address < 0x00):
            raise TypeError("address must be hexadecimal int!")
        module_exists = self.g["modules"].get(address)
        if not module_exists:
            return
        next_query = self.g["modules"][address].get("next_query", 0)
        if Module.time_has_elapsed(next_query):
            self.g["modules"][address]["next_query"] = time.ticks_ms() + 1000
            self.send(Bytes.REG_VARS_QUERY, rx=address)

    #send message over UART channels
    def send(self, cmd:int, data=None, **kwargs) -> None:
        packet = bytearray()
        packet.append(Bytes.START) #[START]

        if not isinstance(cmd, int):
            raise TypeError(f"cmd must be int, not {type(cmd)}")
        if cmd < 0x00 or cmd > 0xFF:
            raise ValueError("cmd must be single-byte hexadecimal!")
        if cmd == Bytes.START:
            raise ValueError(f"cmd must not be reserved hexadecimal byte {Bytes.START}")
        packet.append(cmd) #[CMD]
        
        rx = kwargs.get("rx")
        if rx is None:
            rx = Bytes.RX_GLOBAL
        if not isinstance(rx, int):
            raise TypeError(f"rx must be int, not {type(rx)}")
        if rx < 0x00 or rx > 0xFF:
            raise ValueError("rx must be single-byte hexadecimal!")
        if rx == Bytes.START:
            raise ValueError(f"rx must not be reserved hexadecimal byte {Bytes.START}")
        packet.append(rx) #[RX]
        
        tx = kwargs.get("tx", self.__id)
        packet.append(tx) #[TX]

        data = data if data is not None else []
        if not isinstance(data, (list, tuple, str, bytearray)):
            data = [data]
        
        databytes = bytearray()
        for item in data:
            if not isinstance(item, (str,int)):
                raise ValueError(f"data can only be hexadecimal int or ascii character, not {type(item)}")

            if isinstance(item, str): item=ord(item)

            if item < 0x00 or item > 0xFF:
                raise ValueError(f"ascii character '{item}' hexadecimal must be one byte")
            if item == Bytes.START:
                raise ValueError(f"ascii character '{item}' hexadecimal cannot be reserved byte {Bytes.START}")

            databytes.append(item)

        packet.append(len(databytes)) #[LEN]
        packet.extend(databytes) #[DATA]

        checksum = CHKSUM(cmd, rx, tx, len(databytes), databytes)
        packet.append(checksum) #[CHK]

        #[START][CMD][RX][TX][LEN][DATA][CHK]
        self.__uart_obj.write(packet)

    def __process_command(self, cmd:int, rx:int, tx:int, data:bytearray):
        current_id = self.__id if self.__temp_id is None else self.__temp_id

        #did i send the command?
        if tx == current_id:
            #did my reg attempt succeed? (and im unregistered)
            if cmd == Bytes.REG_ATTEMPT and self.__id is None:
                self.__id, self.__temp_id = self.__temp_id, None
                self.send(Bytes.REG_QUERY)
                self.__event_queue.append(self.__event_hooks["on_ready"])
            return
        
        #is the command intended for me? (global or my id)
        if rx not in (Bytes.RX_GLOBAL, current_id):
            self.send(cmd, data, tx=tx, rx=rx)
            return
        
        #built-in commands:
        should_pass_message_on = None
        if cmd == Bytes.REG_FAIL:
            self.__temp_id = generate_temp_id()
            self.send(Bytes.REG_ATTEMPT, tx=self.__temp_id)
            should_pass_message_on = False
        if cmd == Bytes.REG_ATTEMPT:
            should_pass_message_on = True
            if tx == current_id:
                self.send(Bytes.REG_FAIL, rx=tx, tx=current_id)
                should_pass_message_on = False
        if cmd == Bytes.REG_QUERY:
            if self.__id is not None:
                self.send(Bytes.REG_TYPE, self.name, rx=tx)
            should_pass_message_on = True
        if cmd == Bytes.REG_TYPE:
            data = Module.bytes_to_string(data)
            self.g["modules"][tx] = {"name":data, "str_data":{}, "int_data":{}}
            should_pass_message_on = True
        if cmd == Bytes.REG_STR and tx in self.g["modules"]:
            str_id = data[0]
            str_data = Module.bytes_to_string(data[1:])
            self.g["modules"][tx]["str_data"][str_id] = str_data
            should_pass_message_on = True
        if cmd == Bytes.REG_INT and tx in self.g["modules"]:
            int_id = data[0]
            int_data = data[1]
            self.g["modules"][tx]["int_data"][int_id] = int_data
            should_pass_message_on = True
        if cmd == Bytes.HEARTBEAT:
            self.__alive_modules.add(tx)
            should_pass_message_on = True
        
        #if the message is global AND either the message should be passed on or it isn't a built-in command.
        if (rx == Bytes.RX_GLOBAL) and (should_pass_message_on or should_pass_message_on is None):
            self.send(cmd, data, tx=tx)

        #call custom command hooks
        self.__event_queue.append(lambda cmd=cmd, tx=tx, data=data: self.__command_hooks.get(cmd, __empty)(tx, data))
        self.__event_queue.append(lambda cmd=cmd, tx=tx, data=data: self.__event_hooks["on_command_received"](tx, cmd, data))

    async def __module_registrator(self):
        self.__id = None
        self.__temp_id = generate_temp_id() if "timer" != self.__name else 0x00

        #while unregistered:
        while self.__id is None:
            await uasyncio.sleep_ms(1)
            #send registration message cyclically
            if Module.time_has_elapsed(self.__next["registration_message"]):
                self.__next["registration_message"] += REG_TIMEOUT
                self.send(Bytes.REG_ATTEMPT, tx=self.__temp_id)
            
            #blink purple led to indicate that it's unregistered
            if self.status_led in (Status.LILAC, Status.OFF):
                if Module.time_has_elapsed(self.__next["status_led"]):
                    self.__next["status_led"] += 500
                    self.status_led = (Status.LILAC, Status.OFF)[self.status_led == Status.LILAC]
        
        #turn led green to show that it's made a connection!
        self.status_led = Status.GREEN
        self.__next["status_led_hold"] += 1000

        #while registered:
        while True:
            await uasyncio.sleep_ms(1)
            #turn off led after being green
            if self.__next.get("status_led_hold") and Module.time_has_elapsed(self.__next["status_led_hold"]):
                self.status_led = Status.OFF
                del self.__next["status_led_hold"]
            
            #heartbeat
            if Module.time_has_elapsed(self.__next["heartbeat"]):
                self.__next["heartbeat"] += HEARTBEAT_TIME
                self.send(Bytes.HEARTBEAT)

            if Module.time_has_elapsed(self.__next["prune"]):
                self.__next["prune"] += HEARTBEAT_TIMEOUT

                #remove dead modules
                for addresses in self.get_addresses().values():
                    for address in addresses:
                        if address not in self.__alive_modules:
                            self.g["modules"].pop(address, None)
                            continue
                        self.__alive_modules.remove(address)
                
                #instantiate new modules
                for address in self.__alive_modules.copy():
                        self.__alive_modules.discard(address)
                        self.send(Bytes.REG_QUERY, rx=address)
    
    async def __uart_listener(self):
        #clear buffer
        while self.__uart_obj.any(): self.__uart_obj.read()

        while True:
            await uasyncio.sleep_ms(1)
            if not self.__uart_obj.any(): continue
            byte = self.__uart_obj.read(1)[0]

            #when reading first byte:
            if not self.__uart_data["POS"]:
                if byte == Bytes.START:
                    self.__uart_data["POS"] += 1
                    continue
            self.__uart_data["POS"] += 1

            #put bytes into their categories
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
            
            #if the position doesn't correspond to a category and [LEN] has been established, then it must either be [DATA] or [CHK].
            if key is None and self.__uart_data["LEN"] is not None:
                #if the current position in the message > [LEN] (length of the data), then it is [CHK]
                if self.__uart_data["POS"] > (LEN + self.__uart_data["LEN"]):
                    checksum = CHKSUM(self.__uart_data["CMD"], self.__uart_data["RX"], self.__uart_data["TX"], self.__uart_data["LEN"], self.__uart_data["DATA"])
                    #discard message if [CHK] doesn't match the evaluated checksum
                    if byte != checksum:
                        self.__uart_data = default_uart_data()
                        continue
                    
                    #process the message and execute any built-in commands
                    uart_data = self.__uart_data.copy()
                    self.__process_command(uart_data["CMD"], uart_data["RX"], uart_data["TX"], uart_data["DATA"])
                    self.__uart_data = default_uart_data()
                    continue
                #collect data stream
                self.__uart_data["DATA"].append(byte)
    
    async def __event_handler(self):
        while True:
            await uasyncio.sleep_ms(1)
            #do not run any events if unregistered
            if self.__id is None: continue

            if not len(self.__event_queue): continue
            
            #run events FIFO
            event = self.__event_queue.pop(0)
            await event()

    async def __task_handler(self):
        while True:
            await uasyncio.sleep_ms(1)
            if not len(self.__tasks): continue

            #pop task at the top of the queue and run it,
            #ONLY if the task["next"] timestamp has elapsed
            task = self.__tasks.pop(0)
            if Module.time_has_elapsed(task["next"]):
                task["next"] = (time.ticks_ms() + task["freq"])
                await task["callback"]()
            #add task back to task queue (like a casette roll)
            self.__tasks.append(task)
    
    async def __listener_handler(self):
        while True:
            await uasyncio.sleep_ms(1)
            if not len(self.__components): continue

            #pop component at the top of the components queue
            component_data = self.__components.pop(0)
            component = component_data["obj"]
            value = component.value()
            listener = "high" if value else "low"

            #only call "high" or "low" listeners if component_data["last"]
            #does not match the current value of the component
            last_value = component_data["last"]
            if last_value != value:
                #change component_data["last"] to be the current value
                component_data["last"] = value
                await component.get_listener(listener)()
            
            #call "while_high" or "while_low" listener depending on the value
            await component.get_listener(f"while_{listener}")()

            #add component back to components queue (like a casette roll)
            self.__components.append(component_data)

    async def __event_listener(self):
        while True:
            await uasyncio.sleep_ms(1)
            #time counter:
            if Module.time_has_elapsed(self.__next["time"]):
                self.__next["time"]  += 1000

                m_carry, s = divmod(self.__time["s"]+1, 60)
                h_carry, m = divmod(self.__time["m"]+m_carry, 60)
                h = self.__time["h"] + h_carry

                old_time = self.__time.copy()
                self.__time = {"s":s, "m":m, "h":h}
                self.__g["time"] = self.__time.copy()

                #call event hooks based off of what values changed between
                #the previous values of self.__time and the current ones
                self.__event_queue.append(lambda time=self.__time: self.__event_hooks["on_second_passed"](time))
                if m != old_time["m"]: self.__event_queue.append(lambda time=self.__time: self.__event_hooks["on_minute_passed"](time))
                if h != old_time["h"]: self.__event_queue.append(lambda time=self.__time: self.__event_hooks["on_hour_passed"](time))

    async def __start(self):
        #create all necessary asyncio tasks
        uasyncio.create_task(self.__module_registrator())
        uasyncio.create_task(self.__uart_listener())
        uasyncio.create_task(self.__task_handler())
        uasyncio.create_task(self.__event_listener())
        uasyncio.create_task(self.__event_handler())
        uasyncio.create_task(self.__listener_handler())
        await uasyncio.Event().wait()

    def run(self):
        uasyncio.run(self.__start())

    @property
    def name(self) -> str:
        return self.__name
    
    @property
    def is_registered(self) -> bool:
        return (self.__id is not None)
    
    @property
    def status_led(self) -> tuple[int]:
        return self.__status_led
    
    @status_led.setter
    def status_led(self, v:tuple[int]):
        status_led = Status.validate(v)
        self.__status_led = status_led
        self.set_status_led(self.__status_led)

    @property
    def g(self) -> dict:
        return self.__g

    def get_addresses(self) -> dict[str, set[int]]:
        addresses = defaultdict(list)
        for address,data in self.g["modules"].items():
            addresses[data["name"]].append(address)
        return addresses
    
    @classmethod
    def bytes_to_string(cls, v:bytearray) -> str:
        return "".join(list(map(chr, v)))
    
    @classmethod
    def time_has_elapsed(cls, timestamp:float) -> bool:
        return (time.ticks_diff(timestamp, time.ticks_ms()) <= 0)