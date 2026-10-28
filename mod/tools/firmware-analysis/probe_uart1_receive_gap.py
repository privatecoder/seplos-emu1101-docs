#!/usr/bin/env python3
"""Read-only, hash-bound UART1 gap/ownership proof using actual Cortex-M0 code.

The UART time/FIFO interrupt source is modeled from Synwit's documented formula:
TimeoutTime/(Baudrate/10), only while RX FIFO is nonempty. Instructions/IRQ/
parsers/dispatchers/sender are actual OEM/MAINT Thumb. CPU/peripheral execution
is not cycle accurate. No serial/network interfaces are opened.
Run with patcher venv Python -I from /private/tmp; --out must be a new file.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
from pathlib import Path
from fractions import Fraction
import argparse
import hashlib
import json
import sys

ROOT = PROJECT_ROOT
sys.path.insert(0, str(PATCHER_ROOT))
from seplos.image import Image
from seplos.machine import Machine, UART, ascii_frame, frame
from seplos.selftest import ascii_payload
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

SDK = 'https://github.com/Synwit-Co-Ltd/SWM181_Lib/blob/main/SWM181_StdPeriph_Driver/CSL/SWM181_StdPeriph_Driver/SWM181_uart.h'
INIT = 0x23dc
UART_INIT = 0xb970
OEM_SHA = '5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95'
PROFILES = [
    ('OEM16.06.13', None, 'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex', OEM_SHA),
    ('MAINT1.5-PowerRTC', 'power-rtc-1.5',
     'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V1_5_POWER_RTC].ehex',
     '58f45b854822d1f06eabb663fb2cd8f55d41485dd003eb6d52c2585477d0ca7a'),
    ('MAINT1.6', 'pack-lock-1.6',
     'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V1_6_CUTOFF].ehex',
     'be2ecc7549c7ee16d46eed1f10c256d7231cc5ed961ec90f0bae87e0cfc40d2d'),
    ('MAINT1.6-POSITIVE', 'pack-lock-positive-1.6',
     'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V1_6_CUTOFF_POSITIVE].ehex',
     '010ac5446b644a739611ccaffda85542365dbfccbe5753ede1c1e6b2bc776ae8'),
]


class BusRx:
    """One receiver; immediate IRQ, optional main service after modeled idle.

    Unlike Machine.feed(), honor the configured RXThreshold=6 for data IRQs.
    Intermediate bytes drain at >6 FIFO entries; the tail waits for RX timeout.
    Near-boundary RX-start-vs-RX-complete details are not electrically modeled.
    The compared 100/105/120/150/200-ms gaps avoid the nominal 104.167-ms boundary.
    """
    def __init__(self, board, patched, baud, ticks, threshold):
        self.m, self.patched = board, patched
        self.timeout_ms = Fraction(ticks * 10_000, baud)
        self.threshold = threshold

    def deliver(self, data):
        self.m.timeout = False
        for byte in data:
            self.m.queue.append(byte)
            if len(self.m.queue) > self.threshold:
                self.m.run(self.m.f['irq'])
        assert 0 < len(self.m.queue) <= self.threshold

    def idle(self, ms, service=True):
        fired = bool(self.m.queue and Fraction(ms) > self.timeout_ms)
        if fired:
            self.m.timeout = True
            for _ in range(100):
                if not self.m.queue:
                    break
                self.m.run(self.m.f['irq'])
            assert not self.m.queue
        if service:
            self.work()
        return fired

    def work(self):
        if self.m.num(self.m.r['state']) == 4:
            self.m.dispatch(self.patched)
        return self.m.drain()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if not __debug__:
        ap.error('Python -O unsupported')
    if args.out.exists():
        ap.error('Report exists; choose a new filename')
    base = json.loads(research_input(PROFILES[2][1]).read_text())
    original = Image.read(ROOT / PROFILES[0][2])
    assert original.sha == OEM_SHA
    rows, hashes = [], {}

    def check(label, kind, **data):
        rows.append(dict(image=label, name=kind, passed=True, **data))

    for label, report_name, image_name, expected in PROFILES:
        report = json.loads(research_input(report_name).read_text()) if report_name else base
        facts = report['facts']
        image = Image.read(ROOT / image_name)
        assert image.sha == expected, label
        patched = report_name is not None
        hashes[label] = dict(path=image_name, app_sha256=image.sha,
                             file_sha256=hashlib.sha256((ROOT/image_name).read_bytes()).hexdigest())
        assert image.app[INIT:0x2476] == original.app[INIT:0x2476]
        assert image.app[UART_INIT:0xba4e] == original.app[UART_INIT:0xba4e]

        def board(address):
            m = Machine(image, facts)
            m.defaults(address)
            return m

        m = board(3)
        configs = []
        def capture_config(m, pc):
            if pc == UART_INIT:
                pointer = m.uc.reg_read(UC_ARM_REG_R1)
                assert m.uc.reg_read(UC_ARM_REG_R0) == UART
                configs.append(m.read(pointer, 13))
            return False
        m.callback = capture_config
        # Additional interrupt-controller priority registers used by OEM init.
        m.uc.mem_map(0x45000000, 0x1000)
        clock_pointer = int.from_bytes(image.app[0xbc1c:0xbc20], 'little')
        # Clock is a fixture; requested baud and TOTIME are measured from real code.
        m.put(clock_pointer, (24_000_000).to_bytes(4, 'little'))
        m.run(INIT)
        assert len(configs) == 1
        config = configs[0]
        baud = int.from_bytes(config[:4], 'little')
        ticks, threshold = config[11], config[7]
        control = m.num(UART+4, 4)
        assert (baud, ticks, threshold) == (9600, 100, 6)
        assert config[12] == 1 and (control >> 24) == 100 and control & (1 << 14)
        check(label, 'actual-UART1-init', baud=baud, timeout_chars=ticks,
              timeout_ms=float(Fraction(ticks*10_000, baud)), rx_threshold=threshold,
              ctrl_hex=f'{control:08X}', config_hex=config.hex())

        def bus(address):
            return BusRx(board(address), patched, baud, ticks, threshold)

        responses = {}
        for cmd in (0x42, 0x44):
            response = board(2).transact(ascii_frame(2, cmd, b'\x02'), patched)
            assert ascii_payload(response, 2)[0] == 0
            responses[cmd] = response
        for address in (0, 3):
            for foreign_cmd, response in responses.items():
                for own_cmd in (0x42, 0x44):
                    request = ascii_frame(address, own_cmd, bytes([address]))
                    for gap in (0, 100, 105, 120, 150, 200):
                        b = bus(address)
                        b.deliver(response)
                        state_before = b.m.num(b.m.r['state'])
                        fifo_before = len(b.m.queue)
                        fired = b.idle(gap)
                        assert not b.m.output
                        b.deliver(request)
                        b.idle(200, service=False)
                        combined = b.m.read(b.m.r['rx'], b.m.num(b.m.r['rx_meta']))
                        if not fired:
                            assert combined == response + request
                        out = b.work()
                        assert bool(out) == (gap > b.timeout_ms), (label,address,gap,out)
                        if out:
                            assert ascii_payload(out, address)[0] == 0
                        assert b.m.transact(request, patched), 'must recover without reset'
                        check(label, 'foreign-response-to-addressed-request', address=address,
                              foreign_command=foreign_cmd, own_command=own_cmd, gap_ms=gap,
                              timeout_between=fired, answered=bool(out),
                              rx_state_after_foreign=state_before, foreign_tail_fifo=fifo_before,
                              foreign_bytes=len(response), request_bytes=len(request),
                              combined_before_dispatch=combined.hex() if not fired else None)

            # The timeout has happened, but main has not yet dispatched the frame.
            # Original RX accepts a new '~' in state4; MAINT preserves the ready buffer.
            b = bus(address); response = responses[0x42]
            request = ascii_frame(address, 0x42, bytes([address]))
            b.deliver(response); assert b.idle(200, service=False)
            assert b.m.num(b.m.r['state']) == 4
            saved = b.m.read(b.m.r['rx'], len(response))
            b.deliver(request); b.idle(200, service=False)
            preserved = b.m.read(b.m.r['rx'], len(response)) == saved
            assert preserved == patched
            out = b.work()
            assert bool(out) == (not patched)
            assert b.m.transact(request, patched)
            check(label, 'ready-frame-main-deliberately-delayed', address=address,
                  ready_buffer_preserved=preserved, next_request_answered=bool(out),
                  following_request_recovers=True)

        for address in (0, 3):
            # Conversely: protect an OWN ready request against later foreign traffic.
            # This demonstrates the OEM overwrite defect, not merely the new drop.
            b = bus(address)
            request = ascii_frame(address, 0x42, bytes([address]))
            b.deliver(request); assert b.idle(200, service=False)
            saved = b.m.read(b.m.r['rx'], len(request))
            b.deliver(responses[0x44]); b.idle(200, service=False)
            preserved = b.m.read(b.m.r['rx'], len(request)) == saved
            assert preserved == patched
            out = b.work()
            assert bool(out) == patched
            if out:
                assert ascii_payload(out, address)[0] == 0
            check(label, 'own-ready-request-protected-against-foreign-overwrite',
                  address=address, own_request_preserved=preserved, answered=bool(out))

        m = board(3)
        assert m.transact(ascii_frame(3, 0x42, b'\x03'), patched)
        assert m.num(m.r['state']) == 0
        assert m.transact(ascii_frame(3, 0x44, b'\x03'), patched)
        check(label, 'own-response-next-request-without-foreign-traffic-no-echo')

        if patched:
            binary_response = board(2).transact(frame(2, 0x47), True)
            assert binary_response[:3] == bytes([0x55, 2, 0x47])
            for direction, response, request in (
                ('ASCII-to-binary', responses[0x42], frame(3, 0x47)),
                ('binary-to-ASCII', binary_response, ascii_frame(3, 0x42, b'\x03')),
            ):
                for gap in (100, 200):
                    b = bus(3); b.deliver(response); b.idle(gap)
                    b.deliver(request); b.idle(200, service=False)
                    out = b.work()
                    assert bool(out) == (gap == 200), (label,direction,gap,out)
                    check(label, 'mixed-protocol-gap', direction=direction,
                          gap_ms=gap, answered=bool(out))

    result = dict(schema='seplos-uart1-gap-proof-1', status='passed',
                  scope='OEM16.06.13 and three selected MAINT builds; modeled UART events, actual Thumb',
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  uart_reference=SDK, uart_timeout_formula='100*10/9600 seconds',
                  images=hashes, tests=rows, tests_passed=len(rows), hardware_tested=False,
                  limitations=['Not cycle accurate or an electrical RS485 trace',
                               '100 ms app sleep is not necessarily 100 ms of wire silence',
                               'Delayed-main case is deliberately scheduled, not a measured main-loop latency'])
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False); stream.write('\n')
    print(json.dumps(dict(status='passed', tests=len(rows), report=str(args.out))))


if __name__ == '__main__':
    main()
