"""Bounded native initialization replay with synthetic, immediate MMIO readback.

UART0 = RS485-1/RS485-2 (shared pack bus); UART1 = RS485 pair in the
CAN socket; UART2 = local display/Bluetooth port. CAN uses separate socket pins.

Addresses follow the current image's main-call graph and vector handlers. This
model has no oscillator dynamics, peripheral elapsed time, NVIC arbitration or
wires. Clock-derived rates are nominal configuration checks, not measurements.
The basic protocol Machine remains independent of this test-only MMIO model.
"""
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_XPSR, UC_CPU_ARM_CORTEX_M0)
from .analysis import unique
from .thumb import Code

STOP = 0x3f000
REQUIRED = (
    'hardware-clock-48mhz-readback',
    'hardware-uart0-initialization', 'hardware-uart1-initialization',
    'hardware-uart2-initialization',
    'hardware-irq-cmp', 'hardware-irq-timer0', 'hardware-irq-timer1',
    'hardware-irq-uart0', 'hardware-irq-uart1', 'hardware-irq-uart2',
    'hardware-timer0-initialization', 'hardware-timer1-initialization',
    'hardware-watchdog-main-reset-mode', 'hardware-watchdog-interrupt-mode',
    'hardware-watchdog-progress-guard',
    'hardware-can-selector-0', 'hardware-can-selector-1',
    'hardware-can-selector-6', 'hardware-can-selector-7',
    'hardware-can-selector-8',
)
IRQ_SOURCES = (0x67, 0x54, 0x55, 0x58, 0x59, 0x5a)
IRQ_PRIORITIES = (0, 1, 1, 2, 3, 3)


def _ram(value):
    return value is not None and 0x20000000 <= value < 0x20004000


def discover_hardware(image, facts):
    """Derive roles from executable call relationships; no version/address table."""
    code = Code(image.app)
    main = code.body(facts['functions']['main'])
    enabled = unique([i.at for i in main if i.op == 'cpsie'], 'hardware main interrupt enable')
    calls = [i for i in main if i.op == 'bl' and i.at < enabled]
    bodies = {i.target: code.body(i.target) for i in calls}
    literals = lambda body: {i.literal for i in body if i.literal is not None}
    uart = {n: unique([at for at, body in bodies.items() if 0x50010000 + n*0x1000 in literals(body)],
                     f'hardware UART{n} initializer') for n in range(3)}
    timers = [i for i in calls if 0x50007000 in literals(bodies[i.target])]
    if len(timers) != 2:
        raise ValueError('hardware: expected two main timer initializers')
    clock_ram = unique(list(set.intersection(*[
        {i.literal for i in bodies[t.target] if _ram(i.literal)} for t in timers])), 'hardware clock RAM')
    shared = set.intersection(*[{i.target for i in bodies[at] if i.op == 'bl'}
                               for at in [*uart.values(), *(t.target for t in timers)]])
    route = unique(list(shared), 'hardware shared IRQ route helper')
    cmp_init = unique([at for at, body in bodies.items() if at not in uart.values()
                      and at not in [t.target for t in timers]
                      and any(i.op == 'bl' and i.target == route for i in body)], 'hardware CMP initializer')
    clock_wrapper = calls[0].target
    clock_calls = [i.target for i in bodies[clock_wrapper] if i.op == 'bl']
    readback = unique([at for at in clock_calls if clock_ram in literals(code.body(at))], 'hardware clock readback')
    if len(clock_calls) != 3 or clock_calls[-1] != readback:
        raise ValueError('hardware: unknown clock wrapper ordering')
    select = clock_calls[-2]
    if 0x5000c000 not in literals(code.body(select)):
        raise ValueError('hardware: clock selection lacks HRC register')
    watchdog_calls = [i for i in calls if i.at > timers[-1].at]
    if len(watchdog_calls) != 2:
        raise ValueError('hardware: unknown main watchdog setup window')
    irq = {n: struct.unpack_from('<I', image.app, 0x40+4*n)[0] for n in range(6)}
    if any(not v & 1 or not 0xc0 <= (v & ~1) < len(image.app) for v in irq.values()):
        raise ValueError('hardware: invalid peripheral vector')
    irq = {n: v & ~1 for n, v in irq.items()}
    guard_body = code.body(irq[2])
    guard = unique([i.at for i in guard_body if i.op == 'ldr' and _ram(i.literal)], 'hardware watchdog progress load')
    guard_window = code.window(guard, 4)
    if [i.op for i in guard_window] != ['ldr', 'adds', 'ldrb', 'cmp'] or guard_window[1].args != 'r0, r0, #0x1':
        raise ValueError('hardware: unknown watchdog progress address shape')
    progress = guard_window[0].literal + 1
    # Older light-profile OEMs call CAN initialization from main; newer OEMs do
    # so in the timer startup branch. Both owners are source-derived anchors.
    can_calls = [*calls, *[i for i in code.body(irq[1]) if i.op == 'bl']]
    can = unique(list({i.target for i in can_calls if 0x50020000 in literals(code.body(i.target))}),
                 'hardware CAN initializer')
    selector_candidates = []
    for i in code.body(can):
        w = code.window(i.at, 3)
        if len(w) == 3 and _ram(i.literal) and [x.op for x in w] == ['ldr', 'ldrb', 'cmp'] and w[2].args.endswith('#0x7'):
            selector_candidates.append(i.literal)
    if len(selector_candidates) > 1:
        raise ValueError('hardware: ambiguous CAN selector')
    # Keil startup's first two literal loads delimit its 16-byte region table.
    startup = code.ins[0xc4].target
    init_literals = [i.literal for i in code.window(startup, 4) if i.literal is not None]
    if len(init_literals) != 2:
        raise ValueError('hardware: unknown startup region-table shape')
    start, end = init_literals
    if not 0xc0 <= start < end <= len(image.app) or (end-start) % 16 or end-start > 128:
        raise ValueError('hardware: invalid startup region table')
    regions = []
    for at in range(start, end, 16):
        src, dst, size, handler = struct.unpack_from('<IIII', image.app, at)
        if not _ram(dst) or dst+size > image.sp or size > 0x4000:
            raise ValueError('hardware: invalid startup RAM extent')
        callback = code.body(handler & ~1)
        ops = [i.op for i in callback]
        if ops == ['movs', 'b', 'stm', 'subs', 'cmp', 'bne', 'bx'] and callback[0].args == 'r0, #0x0':
            src = 0
        elif ops != ['b', 'ldm', 'subs', 'stm', 'cmp', 'bne', 'bx']:
            raise ValueError('hardware: unknown startup RAM callback')
        if src and src+size > len(image.app):
            raise ValueError('hardware: invalid startup copy extent')
        regions.append((src, dst, size))
    return dict(uart_init=uart, irq=irq, irq_init={0: cmp_init, 1: timers[0].target,
                2: timers[1].target, 3: uart[0], 4: uart[1], 5: uart[2]},
                irq_priorities=dict(enumerate(IRQ_PRIORITIES)), irq_route=route,
                timer_init={n: t.target for n, t in enumerate(timers)},
                clock_select=select, clock_readback=readback, clock_ram=clock_ram,
                watchdog_setup=watchdog_calls[0].target, watchdog_start=watchdog_calls[1].target,
                watchdog_window=(timers[-1].at+4, enabled), watchdog_guard=guard,
                watchdog_progress=progress, can_init=can,
                can_selector=selector_candidates[0] if selector_candidates else None,
                # Fixed-CAN main startup (.03-.05) and selected-CAN timer
                # startup (.11-.13) independently qualify the timeout family.
                # This is a reviewed OEM-family correlation, not a hardware
                # rule for arbitrary applications. Never learn the expected
                # timeout from the UART under test.
                uart_timeout={0: 10, 1: 100 if selector_candidates else 10, 2: 10},
                regions=regions)


class HardwareModel:
    """Separate zero-initialized MMIO model; native calls are never stubbed."""
    def __init__(self, image, roles):
        self.image, self.roles = image, roles
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
        for address, size in ((0, 0x40000), (0x20000000, 0x4000),
                (0x40000000, 0x10000), (0x41000000, 0x1000),
                (0x43000000, 0x1000), (0x45000000, 0x1000),
                (0x50000000, 0x50000), (0xe000e000, 0x2000)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(0, image.app)
        for src, dst, size in roles['regions']:
            self.uc.mem_write(dst, image.app[src:src+size] if src else bytes(size))
        self.writes, self.executed = [], set()
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._write)
        self.uc.hook_add(UC_HOOK_CODE, self._code)

    def _write(self, uc, access, address, size, value, user):
        if address >= 0x40000000:
            self.writes.append((address, size, value & ((1 << (size*8))-1)))

    def _code(self, uc, address, size, user):
        self.executed.add(address)

    def num(self, address, size=4):
        return int.from_bytes(self.uc.mem_read(address, size), 'little')

    def put(self, address, value, size=4):
        self.uc.mem_write(address, int(value).to_bytes(size, 'little'))

    def run(self, address, args=(), stop=STOP):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM_REG_SP, self.image.sp)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.uc.reg_write(UC_ARM_REG_XPSR, 0x01000000)
        self.uc.emu_start(address | 1, stop, count=100000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == stop, 'hardware bounded replay instruction limit'
        if stop == STOP:
            assert self.uc.reg_read(UC_ARM_REG_SP) == self.image.sp, 'hardware replay stack imbalance'


def _clock(m, r):
    clock = r['clock_ram']
    assert m.num(clock) == 24000000, 'hardware initial SystemCoreClock'
    m.put(0x40000000, 2)
    m.run(r['clock_select'])
    assert m.num(0x5000c000) == 3 and m.num(0x40000000) == 4, 'hardware clock select registers'
    m.run(r['clock_readback'])
    assert m.num(clock) == 48000000 and m.num(clock+4) == 48, 'hardware 48MHz readback'


def _irq(m, n):
    assert m.num(0x45000000+4*n) == IRQ_SOURCES[n], f'hardware IRQ{n} route register'
    assert m.num(0xe000e400+n, 1) == IRQ_PRIORITIES[n] << 6, f'hardware IRQ{n} priority register'
    assert (0xe000e100, 4, 1 << n) in m.writes, f'hardware IRQ{n} enable write'


def _uart(m, r, n):
    m.run(r['uart_init'][n])
    base, baud, timeout = 0x50010000+0x1000*n, (19200 if n == 0 else 9600), r['uart_timeout'][n]
    assert m.num(base+8) & 0x3fff == 48000000//16//baud-1, f'hardware UART{n} divider register'
    ctrl = m.num(base+4)
    assert ctrl >> 24 == timeout, f'hardware UART{n} timeout register'
    assert ctrl & (1 << 9), f'hardware UART{n} enabled'
    assert ctrl & (1 << 13), f'hardware UART{n} flexible baud enabled'
    assert not ctrl & ((1 << 18) | (1 << 19) | (3 << 22)), f'hardware UART{n} framing 8N1'
    assert not ctrl & (1 << 10), f'hardware UART{n} loopback disabled'
    assert m.num(0x40000008) & (1 << (11+n)), f'hardware UART{n} clock enabled'
    # RX FIFO threshold is six characters; timing replay pins the same setting.
    assert (m.num(base+12) >> 16) & 7 == 6, f'hardware UART{n} FIFO threshold register'


def _timer(m, r, n):
    m.run(r['timer_init'][n])
    base = 0x50007000+12*n
    assert m.num(base) == (240000 if n == 0 else 48000000), f'hardware timer{n} LOAD register'
    assert m.num(base+8) == 1, f'hardware timer{n} control register'
    assert m.num(0x50007070) & (1 << n), f'hardware timer{n} interrupt enable'
    assert (0x50007074, 4, 1 << n) in m.writes, f'hardware timer{n} interrupt flag clear'
    assert m.num(0x40000008) & (1 << 6), f'hardware timer{n} clock enabled'


def _watchdog(m, r, interrupt=False):
    m.put(0x50009008, 3)
    if interrupt:
        m.run(r['watchdog_setup'], (0x50009000, 384000000, 1))
        m.run(r['watchdog_start'], (0x50009000,))
    else:
        m.run(r['watchdog_window'][0], stop=r['watchdog_window'][1])
    assert m.num(0x50009000) == (384000000 if interrupt else 192000000), 'hardware watchdog LOAD register'
    assert m.num(0x50009008) == (1 if interrupt else 3), 'hardware watchdog reset/enable register'
    assert m.num(0x40000008) & 0x80, 'hardware watchdog clock enabled'


def _guard(m, r):
    # Execute the actual native tail after timer acknowledgement/housekeeping.
    # Every missing checkpoint must withhold the feed and preserve its mask.
    progress = r['watchdog_progress']
    for value in (0, *(255 ^ (1 << n) for n in range(8)), 255):
        m.put(progress, value, 1)
        m.put(0x50009010, 0)
        # The tail returns via the handler's POP {r4,pc}; provide that real frame.
        m.uc.reg_write(UC_ARM_REG_SP, m.image.sp-8)
        m.uc.mem_write(m.image.sp-8, struct.pack('<II', 0, STOP | 1))
        m.uc.reg_write(UC_ARM_REG_XPSR, 0x01000000)
        m.uc.emu_start(r['watchdog_guard'] | 1, STOP, count=100)
        assert m.uc.reg_read(UC_ARM_REG_PC) == STOP, 'hardware watchdog guard bounded replay'
        assert m.uc.reg_read(UC_ARM_REG_SP) == m.image.sp, 'hardware watchdog guard stack'
        assert m.num(0x50009010) == (0x55 if value == 255 else 0), 'hardware watchdog feed guard register'
        assert m.num(progress, 1) == (0 if value == 255 else value), 'hardware watchdog progress preservation'


def _can(m, r, selector):
    if r['can_selector'] is not None:
        m.put(r['can_selector'], selector, 1)
    m.run(r['can_init'])
    slow = r['can_selector'] is not None and selector == 7
    assert m.num(0x50020018) == (0x9d if slow else 0x85), 'hardware CAN BT0 register'
    assert m.num(0x5002001c) == 0x23, 'hardware CAN BT1 register'
    assert m.num(0x50020010) == 0, 'hardware CAN interrupt enable register'
    assert m.num(0x40000008) & (1 << 25), 'hardware CAN clock enabled'
    bt0, bt1 = m.num(0x50020018), m.num(0x5002001c)
    rate = 48000000 / (2*((bt0 & 63)+1)*(1+(bt1 & 15)+1+((bt1 >> 4) & 7)+1))
    assert rate == (100000 if slow else 500000), 'hardware CAN nominal bitrate'


def validate_hardware(original, patched, facts, build):
    """Run mandatory current-image contracts; failed assertions abort publication."""
    roles = discover_hardware(original, facts)
    checks = []
    def check(name, fn):
        model = HardwareModel(patched, roles)
        model.put(roles['clock_ram'], 48000000)
        fn(model)
        checks.append(dict(name=name, passed=True))
    # Clock check reads the actual initialized value before executing selection.
    model = HardwareModel(patched, roles)
    _clock(model, roles)
    checks.append(dict(name=REQUIRED[0], passed=True))
    for n in range(3):
        check(REQUIRED[1+n], lambda m, n=n: _uart(m, roles, n))
    for n in range(6):
        def route(m, n=n):
            m.run(roles['irq_init'][n])
            _irq(m, n)
        check(REQUIRED[4+n], route)
    for n in range(2):
        check(REQUIRED[10+n], lambda m, n=n: _timer(m, roles, n))
    check(REQUIRED[12], lambda m: _watchdog(m, roles))
    check(REQUIRED[13], lambda m: _watchdog(m, roles, True))
    check(REQUIRED[14], lambda m: _guard(m, roles))
    for index, selector in enumerate((0, 1, 6, 7, 8)):
        check(REQUIRED[15+index], lambda m, selector=selector: _can(m, roles, selector))
    assert tuple(c['name'] for c in checks) == REQUIRED
    return checks
