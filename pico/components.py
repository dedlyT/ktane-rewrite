import machine as m

async def __empty(*a, **kw): pass

class IO:
    MAX_U16 = 65535
    LISTENERS = ("high", "while_high", "low", "while_low")
    
    def __init__(self, pin, *args, **kwargs):
        if len(args) == 0: args = ["out"]
        self._mode = args[0]

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
            
            self.__obj = m.PWM(m.Pin(pin))
            self.__obj.freq(freq)
            self.__obj.duty_u16(duty_u16)
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
    
    def freq(self, v):
        if self._mode != "pwm":
            raise RuntimeError(f"Cannot change frequency of IO configured as '{self._mode}'")
        self.__obj.freq(v)

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