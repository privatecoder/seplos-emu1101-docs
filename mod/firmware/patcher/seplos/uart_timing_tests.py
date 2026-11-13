"""Mandatory UART1 timing with synthetic clock ticks and actual Thumb paths.

> Port notation: UART0 = RS485-1/RS485-2 (shared pack bus); UART1 = RS485
> pair in the CAN socket; UART2 = local display/Bluetooth port. UART1 carries
> RS485 traffic; the actual CAN interface uses separate pins in the same socket.

The SWM181 V2.07 manual specifies an eight-byte RX FIFO and timeout only with
nonempty FIFO and no new reception. Detailed pp.104/107 say RX count > threshold;
p.101 instead says >=. Both comparator interpretations are tested. Neither is
claimed as a resolved physical property. Events are completed-byte arrivals;
CPU execution consumes no modeled time. At an exact deadline callers explicitly
choose timeout-first (advance then arrive) or arrival-first (advance without
service then arrive). This is not wire, CPU-cycle or electrical simulation.
"""
from fractions import Fraction
from .machine import Machine, UART, ascii_frame

CLOCK_HZ = 48_000_000
EXPECTED_BAUD = 9600
EXPECTED_DIVIDER = 311
EXPECTED_TIMEOUT = 100
EXPECTED_THRESHOLD = 6
FIFO_DEPTH = 8
REQUIRED = tuple('uart-timing-' + name for name in (
    'native-config', 'divider-derived-time', 'threshold-boundaries-both-interpretations',
    'threshold-IRQ-keeps-last-byte', 'below-exact-above-timeout',
    'arrival-resets-silence', 'timeout-requires-nonempty-FIFO',
    'FIFO-depth-overflow-explicit', 'same-time-event-orders',
    'adjacent-ASCII-short-gap-merges', 'processed-timeout-separates-ASCII'))


class TimingMachine(Machine):
    """Opt-in RX timing; Machine.feed and the legacy register model stay intact.

    BAUD bit 16 is RXTOIF, the OR of enabled RX threshold and timeout flags
    (manual pp.107–108). FIFO nonempty is CTRL bit 3 (RXNE). Reading DATA
    removes one byte; native RX retains the final byte until timeout bit 21.
    Overflow raises explicitly instead of inventing undocumented drop behavior.
    """
    def __init__(self, image, facts, *, divider=EXPECTED_DIVIDER,
                 timeout_count=EXPECTED_TIMEOUT, threshold=EXPECTED_THRESHOLD,
                 threshold_mode='gt', control=None, fifo=None):
        super().__init__(image, facts)
        assert threshold_mode in ('gt', 'ge'), threshold_mode
        assert 0 <= threshold <= 7, 'SWM181 RX threshold field'
        self.divider = divider
        self.timeout_count = timeout_count
        self.threshold = threshold
        self.threshold_mode = threshold_mode
        self.baud = Fraction(CLOCK_HZ, 16 * (divider + 1))
        self.character_ticks = 10 * 16 * (divider + 1)
        self.timeout_ticks = timeout_count * self.character_ticks
        self.timeout_seconds = Fraction(self.timeout_ticks, CLOCK_HZ)
        self.now = Fraction(0)
        self.last_arrival = None
        self.rx_irqs = []
        # Primary validation supplies the native initializer's exact registers.
        # Explicit model-only callers use the pinned enabled UART1 settings.
        if control is None:
            control = (timeout_count << 24) | (1 << 14) | (1 << 13) | (1 << 9) | (1 << 4)
        self.fifo_configuration = (threshold << 16) if fifo is None else fifo & 0xffff0000
        self.put(UART+4, control.to_bytes(4, 'little'))
        self.put(UART+12, self.fifo_configuration.to_bytes(4, 'little'))

    def _rx_flags(self):
        control = self.num(UART+4, 4)
        threshold = bool(self.queue and self.threshold_pending)
        rxif = threshold and bool(control & (1 << 4))
        toif = bool(self.queue and self.timeout and control & (1 << 14))
        return threshold, rxif, toif

    def _read(self, uc, access, address, size, value, user):
        if address == UART+8:
            threshold, rxif, toif = self._rx_flags()
            status = self.divider & 0x3fff
            status |= int(threshold) << 19
            status |= int(rxif) << 22
            status |= int(toif) << 21
            status |= int(rxif or toif) << 16
            # TX is immediate, as in the basic model; preserve the sender's
            # TXDONEIRQ when its interrupt is enabled by the native driver.
            status |= int(bool(self.num(UART+4, 4) & (1 << 6))) << 27
            self.put(address, status.to_bytes(4, 'little'))
        elif address == UART+12:
            self.put(address, (self.fifo_configuration | len(self.queue)).to_bytes(4, 'little'))
        elif address == UART+4:
            control = self.num(address, 4) & ~(1 << 3)
            self.put(address, (control | (int(bool(self.queue)) << 3)).to_bytes(4, 'little'))
        else:
            super()._read(uc, access, address, size, value, user)

    @property
    def deadline(self):
        return self.last_arrival + self.timeout_ticks if self.queue else None

    @property
    def threshold_pending(self):
        return len(self.queue) > self.threshold if self.threshold_mode == 'gt' else len(self.queue) >= self.threshold

    def service_rx(self):
        _, rxif, toif = self._rx_flags()
        cause = 'timeout' if toif else 'threshold' if rxif else None
        if cause is None:
            return False
        before = bytes(self.queue)
        self.run(self.f['irq'])
        self.rx_irqs.append(dict(cause=cause, ticks=self.now, before=before, after=bytes(self.queue)))
        assert len(self.queue) < len(before), 'native RX IRQ made no progress'
        return True

    def arrive(self, byte, *, service=True):
        assert 0 <= byte <= 255, byte
        assert len(self.queue) < FIFO_DEPTH, 'UART1 FIFO overflow: ninth byte without service'
        self.queue.append(byte)
        self.last_arrival = self.now
        self.timeout = False
        if service:
            self.service_rx()

    def advance(self, ticks, *, service=True):
        ticks = Fraction(ticks)
        assert ticks >= 0, 'synthetic time cannot move backwards'
        target = self.now + ticks
        deadline = self.deadline
        if deadline is not None and deadline <= target:
            self.now = max(self.now, deadline)
            self.timeout = True
            if service:
                self.service_rx()
        self.now = target

    def deliver(self, data):
        for byte in data:
            self.advance(self.character_ticks)
            self.arrive(byte)

    def work(self, patched):
        self.output.clear()
        if self.num(self.r['state']) == 4:
            self.dispatch(patched)
        return self.drain()


def _uart_config(image, facts, hardware):
    from .hardware_tests import HardwareModel
    from .thumb import Code
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1
    m = HardwareModel(image, hardware)
    calls = {i.target for i in Code(image.app).body(hardware['uart_init'][1]) if i.op == 'bl'}
    configs = []
    def capture(uc, address, size, user):
        if address in calls and uc.reg_read(UC_ARM_REG_R0) == UART:
            pointer = uc.reg_read(UC_ARM_REG_R1)
            if 0x20000000 <= pointer < image.sp - 12:
                configs.append(bytes(uc.mem_read(pointer, 13)))
    m.uc.hook_add(UC_HOOK_CODE, capture)
    m.put(hardware['clock_ram'], CLOCK_HZ)
    m.run(hardware['uart_init'][1])
    assert len(configs) == 1, 'unique native UART1 initialization struct'
    config = configs[0]
    return dict(requested_baud=int.from_bytes(config[:4], 'little'),
                divider=m.num(UART+8) & 0x3fff,
                timeout=m.num(UART+4) >> 24,
                threshold=(m.num(UART+12) >> 16) & 7,
                timeout_enabled=bool(m.num(UART+4) & (1 << 14)),
                native_config=config.hex(), control=m.num(UART+4), fifo=m.num(UART+12))


def configuration_mutant(image, facts, field):
    """Change real Thumb input, preserving discoverability of the initializer.

    This is a focused regression helper, not an image emitted by the patcher.
    The timeout MOVS immediate and requested-baud construction are found in the
    source-derived initializer body, without a version-address table.
    """
    from .hardware_tests import discover_hardware
    from .thumb import Code
    hardware = discover_hardware(image, facts)
    entry = hardware['uart_init'][1]
    code = Code(image.app)
    body = code.body(entry)
    app = bytearray(image.app)
    if field == 'timeout':
        candidates = [i for i in body if i.op == 'movs' and i.args.endswith('#0x64')]
        assert len(candidates) == 1, 'unique UART1 timeout immediate'
        app[candidates[0].at] = EXPECTED_TIMEOUT - 1
    elif field == 'divider':
        candidates = []
        for i in body:
            w = code.window(i.at, 3)
            if (i.op == 'movs' and i.args == 'r0, #0x4b' and
                    [x.op for x in w] == ['movs', 'lsls', 'str'] and
                    w[1].args == 'r0, r0, #0x7' and '[sp,' in w[2].args):
                candidates.append(i)
        assert len(candidates) == 1, 'unique UART1 requested baud construction'
        app[candidates[0].at] = 0x4c
    else:
        raise ValueError(field)
    return image.with_app(app)


def validate_uart_timing(original, patched, facts, build):
    """Run independently pinned initialization and native UART1 RX contracts."""
    rows = []
    observed = []
    expected_timeout = []
    from .hardware_tests import discover_hardware
    def equal(actual, expected, label=''):
        assert actual == expected, (label, actual, expected)
    def check(name, fn):
        try:
            fn()
        except Exception as exc:
            raise AssertionError('uart-timing-' + name + ': ' + str(exc)) from exc
        rows.append(dict(name='uart-timing-' + name, passed=True))
    def config():
        hardware = discover_hardware(original, facts)
        # Accepted older light OEMs have a fixed CAN initializer and ten-char
        # UART1 timeout. The later selector family uses 100. This independent
        # native control-flow qualification cannot be changed by a timeout mutant.
        expected_timeout.append(10 if hardware['can_selector'] is None else EXPECTED_TIMEOUT)
        for image in (original, patched):
            cfg = _uart_config(image, facts, hardware)
            equal(cfg['divider'], EXPECTED_DIVIDER, 'divider')
            equal(cfg['requested_baud'], EXPECTED_BAUD, 'requested baud')
            equal(cfg['timeout'], expected_timeout[0], 'timeout')
            equal(cfg['threshold'], EXPECTED_THRESHOLD, 'threshold')
            assert cfg['control'] & (1 << 13), 'flexible baud disabled'
            assert not cfg['control'] & ((1 << 18) | (1 << 19) | (3 << 22)), 'framing must be 8N1'
            assert not cfg['control'] & (1 << 10), 'loopback enabled'
            assert cfg['timeout_enabled'], 'timeout interrupt disabled'
            assert cfg['control'] & (1 << 4), 'RX threshold interrupt disabled'
            observed.append(cfg)
    check('native-config', config)
    def boards():
        for image, ispatched in ((original, False), (patched, True)):
            for mode in ('gt', 'ge'):
                cfg = observed[int(ispatched)]
                m = TimingMachine(image, facts, divider=cfg['divider'], timeout_count=cfg['timeout'], threshold=cfg['threshold'], threshold_mode=mode, control=cfg['control'], fifo=cfg['fifo'])
                m.defaults(1)
                yield m, ispatched
    def timing():
        for m, _ in boards():
            equal(m.baud, Fraction(125000, 13), 'divider baud')
            equal(m.timeout_ticks, expected_timeout[0] * 49_920, 'timeout ticks')
            equal(m.timeout_seconds, Fraction(expected_timeout[0] * 13, 12500), 'divider timeout at modeled 48MHz')
    check('divider-derived-time', timing)
    def thresholds():
        for m, _ in boards():
            count = 7 if m.threshold_mode == 'gt' else 6
            for byte in range(count - 1):
                m.arrive(0x7e if not byte else 0x32)
            equal(m.rx_irqs, [])
            equal(len(m.queue), count - 1)
            m._read(m.uc, 0, UART+8, 4, 0, None)
            equal(m.num(UART+8, 4) & (1 << 16), 0, 'RXTOIF below threshold')
            m.arrive(0x33, service=False)
            m._read(m.uc, 0, UART+8, 4, 0, None)
            equal(m.num(UART+8, 4) & ((1 << 16) | (1 << 22)), (1 << 16) | (1 << 22), 'RXTOIF at threshold IRQ')
            assert m.service_rx()
            equal(len(m.rx_irqs), 1)
            equal(len(m.rx_irqs[0]['before']), count)
            equal(m.rx_irqs[0]['cause'], 'threshold')
    check('threshold-boundaries-both-interpretations', thresholds)
    def tail():
        for m, _ in boards():
            packet = ascii_frame(1, 0x51)
            m.deliver(packet)
            assert m.rx_irqs and all(e['after'][-1:] == e['before'][-1:] for e in m.rx_irqs)
            assert 1 <= len(m.queue) <= m.threshold
            equal(m.num(m.r['state']), 1)
            equal(m.read(m.r['rx'], len(packet)-len(m.queue)), packet[:-len(m.queue)])
    check('threshold-IRQ-keeps-last-byte', tail)
    def boundaries():
        for offset in (-1, 0, 1):
            for m, _ in boards():
                packet = ascii_frame(1, 0x51)
                m.deliver(packet)
                m.advance(m.timeout_ticks + offset)
                equal(m.num(m.r['state']), 1 if offset < 0 else 4)
                equal(bool(m.queue), offset < 0)
                if offset >= 0:
                    equal(m.rx_irqs[-1]['cause'], 'timeout')
                    equal(m.read(m.r['rx'], m.num(m.r['rx_meta'])), packet)
    check('below-exact-above-timeout', boundaries)
    def reset():
        for m, _ in boards():
            m.deliver(ascii_frame(1, 0x51)[:-1])
            m.advance(m.timeout_ticks - 1)
            m.arrive(13)
            m.advance(m.timeout_ticks - 1)
            equal(m.num(m.r['state']), 1)
            m.advance(1)
            equal(m.num(m.r['state']), 4)
    check('arrival-resets-silence', reset)
    def empty():
        for m, _ in boards():
            m.advance(2 * m.timeout_ticks)
            equal(m.rx_irqs, [])
            equal(m.timeout, False)
            m.deliver(ascii_frame(1, 0x51));m.advance(m.timeout_ticks)
            count = len(m.rx_irqs)
            m.advance(2 * m.timeout_ticks)
            equal(len(m.rx_irqs), count)
            equal(m.timeout, False)
    check('timeout-requires-nonempty-FIFO', empty)
    def overflow():
        for m, _ in boards():
            for byte in range(FIFO_DEPTH):
                m.arrive(byte, service=False)
            try:
                m.arrive(8, service=False)
            except AssertionError as exc:
                assert 'FIFO overflow' in str(exc)
            else:
                raise AssertionError('ninth byte accepted')
            equal(bytes(m.queue), bytes(range(FIFO_DEPTH)))
    check('FIFO-depth-overflow-explicit', overflow)
    def ordering():
        for arrival_first in (False, True):
            for m, _ in boards():
                m.deliver(ascii_frame(1, 0x51))
                m.advance(m.timeout_ticks, service=not arrival_first)
                if arrival_first:
                    m.arrive(13)
                    equal(m.num(m.r['state']), 1)
                    m.advance(m.timeout_ticks)
                    equal(m.num(m.r['state']), 4)
                else:
                    equal(m.num(m.r['state']), 4)
                    count = len(m.rx_irqs)
                    m.arrive(13)
                    equal(len(m.rx_irqs), count)
                    equal(bytes(m.queue), b'\r')
    check('same-time-event-orders', ordering)
    def adjacent(separated):
        from .selftest import ascii_payload
        for m, ispatched in boards():
            # Two independently valid ASCII requests with a foreign first ADR.
            # State 1 keeps appending even at a fresh '~': EMU1101-EXT retains case A.
            foreign = ascii_frame(2, 0x51)
            own = ascii_frame(1, 0x51)
            m.deliver(foreign)
            m.advance(m.timeout_ticks if separated else m.timeout_ticks - m.character_ticks - 1)
            if separated:
                equal(m.work(ispatched), b'')
                equal(m.num(m.r['state']), 0)
            m.deliver(own)
            m.advance(m.timeout_ticks)
            equal(m.read(m.r['rx'], m.num(m.r['rx_meta'])), own if separated else foreign + own)
            out = m.work(ispatched)
            if separated:
                assert out, 'separated own ASCII request unanswered'
                equal(ascii_payload(out, 1)[0], 0)
            else:
                equal(out, b'')
    check('adjacent-ASCII-short-gap-merges', lambda: adjacent(False))
    check('processed-timeout-separates-ASCII', lambda: adjacent(True))
    equal(tuple(row['name'] for row in rows), REQUIRED)
    return rows
