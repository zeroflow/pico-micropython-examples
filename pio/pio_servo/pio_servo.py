# Example of using PIO for Servo control
 
from machine import Pin
from rp2 import PIO, StateMachine, asm_pio
from time import sleep

@asm_pio()
def servo_trigger():
    irq(clear, 4)    # Clear next relative ISR, allows servo code to run again
    irq(4)
    mov(y, x)             # Counter is stored in x, copy to y for use
    label("base")
    jmp(y_dec, "base")    # wait for programmed time
    
@asm_pio(sideset_init=PIO.OUT_LOW)
def servo_prog():
    wrap_target()
    
    wait(0, "irq", 4) .side(0) # Wait here for IRQ to be released by trigger SM
    
    pull(noblock)        # pull new pulse length into fifo (pull fifo into OSR, if empty fifo copies X->OSR)
    mov(x, osr)          # Keep most recent pull data stashed in X, for recycling by noblock (later)
    mov(y, isr) .side(1) # ISR must be preloaded with base length
    
    label("base")
    jmp(y_dec, "base")    # wait in state 1 for steps in y register (base pulse length)
    
    mov(y, x)
    label("var")    
    jmp(y_dec, "var")     # wait in state 1 for steps in x register (variable pulse length)
    
    wrap()
        
class ServoTrigger:
    '''
    Run one statemachine in a loop, that clears IRQ every 20ms as the
    base for the servo statemachine.
    '''
    def __init__(self, sm_idx):
        # Trigger SM should output a pulse every 20ms for the servo SM to run
        trig_target = 20 # ms
        
        trig_frq = 10_000 #Hz
        sm_trig = StateMachine(sm_idx, servo_trigger, freq=trig_frq)
        trig_ctr = (trig_frq // 1000 * trig_target) - 4 # 3 instructions to have perfect 20ms on IRQ

        sm_trig.put(trig_ctr)
        sm_trig.exec("pull()")
        sm_trig.exec("mov(x, osr)")
        sm_trig.active(1)
    
class Servo:
    '''
    Accepts the servo setpoint via FIFO input.
    It raises and waits for IRQ after the positive part of the pulse has been output.
    The other statemachine should clear IRQ every 20ms so that a new pulse is output cyclically.
    
    Preload the ISR with the base duration (fixed pulse length for position 0°)
    Send position data via FIFO into the OSR (variable pulse length for 0°..max)
    '''
    def __init__(self, sm_idx, pin, min_pulse, max_pulse):
        self.baseFrq = 1_000_000 # 1MHz = 1us clock base
        
        self.base_pulse = min_pulse             # us, base width of pulse
        self.free_pulse = max_pulse - min_pulse # us, max. additional length set by percent
        
        self.sm = StateMachine(sm_idx, servo_prog, freq=self.baseFrq, sideset_base=Pin(pin))

        # Use exec() to load max count into ISR
        self.sm.put(self.base_pulse)
        self.sm.exec("pull()")
        self.sm.exec("mov(isr, osr)")
        self.sm.active(1)
        
    def pos(self, n):
        '''Set servo position. Range 0.0 to 1.0'''
        self.sm.put(int(self.free_pulse*n))

# Trigger needs to be the sm before the servo, so the IRQs set by rel(n) match
trig = ServoTrigger(0)
s = Servo(1, 16, 1000, 2000) # phys IO on pin 16, with 1ms..2ms pulse width
s2 = Servo(3, 17, 1000, 2000) # phys IO on pin 16, with 1ms..2ms pulse width

while True:
    for p in range(10+1):
        p = p/10 # Scale 0..10 to 0..1
        
        s.pos(p)
        s2.pos(1-p)
        
        sleep(0.5)
