#!/usr/bin/env python3
"""Version-bound, offline four-part audit. Executes shipped Thumb, models MMIO.

Run with patcher venv, Python -I, cwd /private/tmp. No ports, no image writes.
NVM model: sector erase and 1->0 word programming; a cut can stop after ANY
programmed word. Flash timing, brownout voltage and torn bits within a word
are not electrically simulated. CRC/readers/writers are actual firmware code.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
from pathlib import Path
import argparse, hashlib, json, sys
from collections import deque
ROOT = PROJECT_ROOT
sys.path.insert(0, str(PATCHER_ROOT))
from seplos.image import Image
from seplos.machine import Machine, PowerLoss, ascii_frame, frame
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_PRIMASK, UC_ARM_REG_LR

OUT = ROOT / 'local/research/validation/evidence/Vierfachpruefung-2026-10-23'
OEM = ROOT / 'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex'


def profiles():
    result = {}
    for version in ('1.5.1', '1.6.1'):
        d = json.loads(research_input('marker-uart0-' + version).read_text())
        suffix = 'POWER_RTC' if version == '1.5.1' else 'CUTOFF_POSITIVE'
        path = ROOT / f'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V{version.replace(".", "_")}_{suffix}].ehex'
        im = Image.read(path)
        assert d['status'] == 'passed' and im.sha == d['build']['app_sha256']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == d['output_file_sha256']
        result[version] = (im, d['facts'], d['build'])
    original = Image.read(OEM)
    assert original.sha == '5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95'
    result['OEM'] = (original, result['1.5.1'][1], {})
    return {k: result[k] for k in ('OEM', '1.5.1', '1.6.1')}


class NV:
    """Intercept ONLY hardware primitives, let all record code run unchanged."""
    def __init__(self, image, facts, flash=None):
        self.m = Machine(image, facts)
        self.m.put(0x25000, flash if flash is not None else b'\xff' * 0x8000)
        self.ops = []
        self.cut = None
        self.m.callback = self.callback

    def callback(self, m, pc):
        f = m.f
        if pc in (f['iap_read'], f['iap_write']):
            return True  # suppress Machine's high-level stub, execute real code
        if pc not in (0xbcec, f['iap_erase'], f['iap_program']):
            return False
        r0, r1, r2 = (m.uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if pc == 0xbcec:
            assert 0x25000 <= r0 and r0 + 4*r2 <= 0x2d000
            m.put(r1, m.read(r0, 4*r2)); m.ret(0); return True
        if pc == f['iap_erase']:
            assert r0 % 4096 == 0 and 0x25000 <= r0 < 0x2d000
            m.put(r0, b'\xff' * 4096)
            self.event(('erase', r0, 0)); m.ret(0); return True
        if pc == f['iap_program']:
            assert 0x25000 <= r0 and r0 + 4*r2 <= 0x2d000
            for i in range(r2):
                a = r0 + 4*i
                m.put(a, bytes(x & y for x, y in zip(m.read(a, 4), m.read(r1+4*i, 4))))
                self.event(('word', r0, i+1))
            m.ret(0); return True
        return False

    def event(self, op):
        self.ops.append(op)
        if self.cut == len(self.ops):
            raise PowerLoss('audit: power cut after primitive/word')

    def flash(self):
        return self.m.read(0x25000, 0x8000)

    def boot_parameters(self):
        self.m.defaults(1)


def persistence(profs):
    rows = []
    def add(**row):
        rows.append(dict(passed=True, **row))
    for label, (im, f, _) in profs.items():
        nv = NV(im, f); nv.boot_parameters(); m = nv.m
        # Persist OLD full parameter record before attempting a different P0.
        m.put(f['ram']['words'], (3550).to_bytes(2, 'little')); m.run(f['functions']['serializer'])
        initial = nv.flash()
        nv.ops.clear(); m.put(f['ram']['words'], (3600).to_bytes(2, 'little')); m.run(f['functions']['serializer'])
        operation_count = len(nv.ops)
        assert operation_count == 90, (label, nv.ops)
        for cut in range(1, operation_count+1):
            a = NV(im, f, initial); a.boot_parameters(); a.m.put(f['ram']['words'], (3600).to_bytes(2, 'little'))
            a.ops.clear(); a.cut = cut
            try: a.m.run(f['functions']['serializer'])
            except PowerLoss: pass
            else: raise AssertionError('missing injected cut')
            b = NV(im, f, a.flash()); b.boot_parameters()
            value = b.m.num(f['ram']['words'], 2)
            assert value in (3550, 3600), (label, cut, value)
            if label != '1.6.1':
                assert value == (3550 if cut < 45 else 3600), (label, cut, value)
            latch = b.m.num(f['cutoff']['ram']) if label == '1.6.1' else None
            # A single valid unlocked mirror does not release the persistent latch.
            if label == '1.6.1':
                assert latch == int(1 <= cut < 45 or 46 <= cut < 90), (cut, latch)
            add(image=label, kind='parameter-word-cut', cut=cut, stopped_at=a.ops[-1], P0=value,
                reboot_lock=latch, boot_repair_ops=len(b.ops))

        # Two valid but different records: OEM selects primary, never newest-by-age.
        older = NV(im, f, initial); older.boot_parameters(); newer = nv.flash()
        divergent = bytearray(initial)
        divergent[:4096] = newer[:4096]
        a = NV(im, f, bytes(divergent)); a.boot_parameters()
        assert a.m.num(f['ram']['words'], 2) == 3600
        add(image=label, kind='two-valid-different-primary-wins', P0=3600, boot_repair_ops=len(a.ops),
            reboot_lock=a.m.num(f['cutoff']['ram']) if label == '1.6.1' else None)

        # Both CRCs bad: OEM loader restores defaults; cutoff remains conservative.
        bad = bytearray(initial)
        for offset in (171, 4096+171): bad[offset] ^= 1
        a = NV(im, f, bytes(bad)); a.boot_parameters()
        latch = a.m.num(f['cutoff']['ram']) if label == '1.6.1' else None
        if latch is not None: assert latch == 1
        add(image=label, kind='both-parameter-crcs-invalid', P0=a.m.num(f['ram']['words'], 2),
            reboot_lock=latch, boot_repair_ops=len(a.ops))

        # SOC block6 still uses the original, unmodified mirrored OEM writer/reader.
        base = NV(im, f); base.boot_parameters()
        for address, value in ((0x20000cd4, 7500), (0x20000cd6, 28000)):
            base.m.put(address, value.to_bytes(2, 'little'))
        base.m.run(0x5564); oldflash = base.flash()
        for cut in range(1, 15):
            a = NV(im, f, oldflash); a.boot_parameters()
            a.m.put(0x20000cd4, (18000).to_bytes(2, 'little')); a.m.put(0x20000cd6, (28000).to_bytes(2, 'little'))
            a.ops.clear(); a.cut = cut
            try: a.m.run(0x5564)
            except PowerLoss: pass
            else: raise AssertionError('missing SOC cut')
            b = NV(im, f, a.flash()); b.boot_parameters(); b.m.run(0x55ce)
            remaining = b.m.num(0x20000cd4, 2)
            assert remaining == (7500 if cut < 7 else 18000), (label, cut, remaining)
            add(image=label, kind='SOC-word-cut', cut=cut, stopped_at=a.ops[-1], remaining_cAh=remaining,
                soc_tenths=b.m.num(0x20000cd8, 2), boot_repair_ops=len(b.ops))
        bad = bytearray(oldflash)
        for offset in (0x6000+20, 0x7000+20): bad[offset] ^= 1
        a = NV(im, f, bytes(bad)); a.boot_parameters()
        a.m.put(f['ram']['words']+118, (12345).to_bytes(2, 'little')); a.m.run(0x55ce)
        assert a.m.num(0x20000cd4, 2) == 12345
        add(image=label, kind='both-SOC-crcs-invalid-fallback-P59', remaining_cAh=12345,
            learned_full_cAh=a.m.num(0x20000cd6, 2))
    return rows


def startup(profs):
    """Execute reset/scatter init and isolated scheduler/watchdog control code.

    Skipped callees are explicitly listed; this is NOT a full hardware boot.
    Instruction-budget expiry proves a synthetic stuck-status wait, not that
    the status occurs on a real board. No time-to-watchdog-reset is inferred.
    """
    from seplos.thumb import Code
    rows = []
    def add(label, kind, **kw): rows.append(dict(image=label, kind=kind, passed=True, **kw))
    for label, (im, facts, build) in profs.items():
        reset = int.from_bytes(im.app[4:8], 'little') & ~1
        m = Machine(im, facts)
        m.put(0x20000000, b'\xa5' * 0x2000)
        m.pause = facts['functions']['main']; m.run(reset)
        assert m.uc.reg_read(UC_ARM_REG_PC) == 0x60f0
        assert m.uc.reg_read(UC_ARM_REG_SP) == im.sp
        if label == '1.6.1': assert m.read(im.sp, 4) == bytes(4)
        add(label, 'actual-reset-and-scatter-init-reaches-main', PC='0x60f0', SP=hex(im.sp),
            added_cache_zeroed=label == '1.6.1')

        m = Machine(im, facts)
        for region in (0x41000000, 0x43000000, 0x44000000, 0x45000000):
            m.uc.mem_map(region, 0x1000)
        m.uc.mem_map(0x50030000, 0x20000)
        m.pause = 0x6152
        try: m.run(reset)
        except AssertionError as exc:
            assert 'instruction limit' in str(exc)
        else: raise AssertionError('missing peripheral completion did not block boot')
        assert m.uc.reg_read(UC_ARM_REG_PC) in (0xc0e4, 0xc0e6, 0xc0e8)
        add(label, 'startup-waits-for-peripheral-bit5-without-local-timeout',
            status_address='0x50040040', PC=hex(m.uc.reg_read(UC_ARM_REG_PC)),
            before_app_watchdog_configuration=True, real_hardware_fault_not_established=True)
        # Supply precisely the absent completion event; do not skip native init.
        m.put(0x50040040, (0x20).to_bytes(4, 'little')); m.run(reset)
        assert m.uc.reg_read(UC_ARM_REG_PC) == 0x6152
        assert m.uc.reg_read(UC_ARM_REG_PRIMASK) == 0
        assert m.num(0x50002000, 4) & ((1<<10)|(1<<12)|(1<<13)|(1<<15)) == 0
        add(label, 'actual-boot-initializers-reach-main-loop', PC='0x6152',
            interrupts_enabled=True, power_outputs_low=True,
            MMIO='register model with peripheral completion bit5 supplied; no NVIC scheduling')

        for entry, ctrl, expected in ((0x5722, 2, 0), (0x5722, 0, 1), (0x5722, 0x80, 2), (0x56fa, 0x42, 0)):
            m = Machine(im, facts); reinits = []
            def cb_i2c(board, pc):
                if pc == 0x5694: reinits.append(pc); board.ret(); return True
                return False
            m.callback = cb_i2c
            m.put(0x5001800c, ctrl.to_bytes(4, 'little'))
            returned = m.run(entry)
            assert returned == expected
            assert bool(reinits) == (entry == 0x56fa)
            add(label, 'bounded-I2C-wait', entry=hex(entry), injected_control=hex(ctrl),
                return_value=returned, loop_limit=25000 if entry == 0x56fa else 5000,
                reinitialization_stubbed=bool(reinits))

        # Timer0 at 5ms/tick: load at tick400, enable measurement at tick600.
        for before in (398, 399, 400, 598, 599, 600):
            m = Machine(im, facts); calls = []
            code = Code(im.app)
            callees = {i.target for i in code.body(0x5ff0) if i.op == 'bl'}
            if build.get('cutoff'): callees.add(build['entries']['hook_cut_loader'])
            def cb(board, pc):
                if pc in callees:
                    calls.append(pc); board.ret(1); return True
                return False
            m.callback = cb; m.put(0x200000aa, before.to_bytes(2, 'little'))
            m.run(0x5ff0)
            expected_loader = build['entries'].get('hook_cut_loader', 0x496a) if build else 0x496a
            assert (expected_loader in calls) == (before == 399)
            assert (0x18c4 in calls) == (before == 599)
            assert bool(m.num(0x200000a8) & 2) == (before == 599)
            add(label, 'timer0-startup-threshold', counter_before=before,
                counter_after=m.num(0x200000aa, 2), calls=[hex(c) for c in calls],
                all_direct_callees_stubbed=True)

        # Timer1 feeds ONLY at full 0xff liveness mask; run all256 values.
        m = Machine(im, facts); feeds = []
        def cb(board, pc):
            if pc == 0x9044: board.ret(); return True  # isolate watchdog handshake
            return False
        m.callback = cb
        def observe(uc, access, address, size, value, user):
            if address == 0x50009010: feeds.append(value)
        m.uc.hook_add(UC_HOOK_MEM_WRITE, observe)
        for mask in range(256):
            feeds.clear(); m.put(0x200000a9, bytes([mask])); m.run(0x60cc)
            assert feeds == ([0x55] if mask == 255 else [])
            assert m.num(0x200000a9) == (0 if mask == 255 else mask)
        add(label, 'timer1-watchdog-all256-liveness-masks', masks=256,
            required_mask='FF', feed='55', coulomb_tick_stubbed=True)

        # Hardware FLASH read busy waits. Force persistent flags, bound emulator.
        for entry, status_at, status, stop_pcs in (
            (0xc7dc, 0x43000064, 0, (0xc7e8, 0xc7ea, 0xc7ec)),
            (0xbcec, 0x44000008, 1 << 16, (0xbcfa, 0xbcfc, 0xbcfe)),
            (0xbcec, 0x44000008, 1 << 21, (0xbd14, 0xbd16, 0xbd18)),
        ):
            m = Machine(im, facts)
            m.uc.mem_map(0x43000000, 0x1000); m.uc.mem_map(0x44000000, 0x1000)
            m.callback = lambda board, pc: pc == 0xbcec  # execute actual primitive
            m.put(0x40000400, (1).to_bytes(4, 'little'))
            m.put(status_at, status.to_bytes(4, 'little'))
            m.uc.reg_write(UC_ARM_REG_R0, 0x25000)
            m.uc.reg_write(UC_ARM_REG_R1, 0x20002000)
            m.uc.reg_write(UC_ARM_REG_R2, 1)
            try: m.run(entry, count=3000)
            except AssertionError as exc:
                assert 'instruction limit' in str(exc)
            else: raise AssertionError('stuck hardware flag unexpectedly returned')
            assert m.uc.reg_read(UC_ARM_REG_PC) in stop_pcs
            add(label, 'unbounded-FLASH-status-wait', entry=hex(entry), status_address=hex(status_at),
                injected_status=hex(status), PC=hex(m.uc.reg_read(UC_ARM_REG_PC)), instruction_budget=3000)
    return rows


PORTS = {
    'R': dict(uart=0x50010000, irq=0x296, state=0x20000108, rx=0x20000304, limit=380),
    'C': dict(uart=0x50011000, irq=0x25a6, state=0x20000dfe, rx=0x20000dff, limit=230),
    'D': dict(uart=0x50012000, irq=0x759c, state=0x20001426, rx=0x200014f4, limit=200),
}


class MultiUART(Machine):
    """Three independent register/FIFO models, actual original IRQ handlers."""
    def __init__(self, image, facts):
        self.fifos = {p: deque() for p in PORTS}
        self.timeouts = {p: False for p in PORTS}
        self.transmitted = {p: bytearray() for p in PORTS}
        super().__init__(image, facts)

    def _read(self, uc, access, address, size, value, user):
        for port, d in PORTS.items():
            u, q = d['uart'], self.fifos[port]
            if address == u+8:
                status = ((1<<16) if q else 0) | ((1<<21) if q and self.timeouts[port] else 0)
                status |= (1<<27) if self.num(u+4, 4)&0x40 else 0
                self.put(address, status.to_bytes(4, 'little')); return
            if address == u+12: self.put(address, len(q).to_bytes(4, 'little')); return
            if address == u:
                assert q, ('FIFO underflow', port)
                self.put(address, q.popleft().to_bytes(4, 'little'))
                if not q: self.timeouts[port] = False
                return
        super()._read(uc, access, address, size, value, user)

    def _write(self, uc, access, address, size, value, user):
        for port, d in PORTS.items():
            if address == d['uart']: self.transmitted[port].append(value & 255)
        super()._write(uc, access, address, size, value, user)

    def feed_port(self, port, data):
        q = self.fifos[port]; d = PORTS[port]; self.timeouts[port] = False
        for j in range(0, len(data), 7):
            q.extend(data[j:j+7]); self.run(d['irq'])
        if q: self.timeouts[port] = True; self.run(d['irq'])
        assert not q


def uart_interrupts(profs):
    from seplos.thumb import Code
    rows = []
    def add(label, kind, **kw): rows.append(dict(image=label, kind=kind, passed=True, **kw))
    original = profs['OEM'][0]
    for label, (im, f, build) in profs.items():
        for start, end in ((0x1aa, 0x2a2), (0x74a6, 0x75a8)):
            assert im.app[start:end] == original.app[start:end]
        for port, d in PORTS.items():
            first = frame(3, 0x47) if port == 'D' else ascii_frame(3, 0x51)
            second = frame(2, 0xa2) if port == 'D' else ascii_frame(2, 0x51)
            m = MultiUART(im, f); m.defaults(3); m.feed_port(port, first)
            ready = m.num(d['state']); before = m.read(d['rx'], len(first))
            assert before == first and (ready & 8 if port == 'D' else ready == 4)
            m.feed_port(port, second); after = m.read(d['rx'], len(first))
            protected = port == 'C' and label != 'OEM'
            assert after == (first if protected else second), (label, port, after)
            add(label, 'ready-buffer-followed-by-foreign-frame', port=port,
                original_preserved=protected, before_state=ready, after_state=m.num(d['state']),
                before_hex=before.hex(), after_hex=after.hex())

            for size in (d['limit']-1, d['limit'], d['limit']+1, d['limit']*2+3):
                m = MultiUART(im, f); m.defaults(3)
                guard = 2 if port == 'D' else 4  # D length metadata starts at RX+202
                m.put(d['rx'], b'\xa5' * (d['limit']+guard))
                data = (b'\x55' if port == 'D' else b'~') + b'Z' * (size-1)
                m.feed_port(port, data)
                assert m.read(d['rx']+d['limit'], guard) == b'\xa5'*guard, (label, port, size)
                add(label, 'receive-limit-canary', port=port, input_bytes=size,
                    data_limit=d['limit'], canary_bytes=guard, canary_unchanged=True, final_state=m.num(d['state']))

        # None of these new revisions changed C timeout/init; freeze bindings.
        assert im.app[0x23dc:0x2476] == original.app[0x23dc:0x2476]
        assert im.app[0xb970:0xba4e] == original.app[0xb970:0xba4e]
        add(label, 'C-timeout-init-byte-identical-to-reviewed-OEM',
            timeout_chars=100, baud=9600, nominal_ms=100*10/9600*1000,
            previous_evidence='local/research/uart1-reception/evidence/UART1-Empfangspause-2026-10-21-final.json')

        # Actual FLASH primitives always CPSIE, even if their caller was masked.
        for entry in (0xbc88, 0xbcb6):
            for initial_mask in (0, 1):
                m = Machine(im, f); m.uc.mem_map(0x43000000, 0x1000); m.uc.mem_map(0x44000000, 0x1000)
                m.put(0x200000fc, (0x3e001).to_bytes(4, 'little'))
                m.put(0x43000064, (1).to_bytes(4, 'little'))
                def primitive(board, pc):
                    if pc in (0xbc88, 0xbcb6): return True
                    if pc == 0x3e000: board.ret(0); return True
                    return False
                m.callback = primitive
                m.uc.reg_write(UC_ARM_REG_R0, 0x25000)
                m.uc.reg_write(UC_ARM_REG_R1, 0x20001068)
                m.uc.reg_write(UC_ARM_REG_R2, 1)
                m.uc.reg_write(UC_ARM_REG_PRIMASK, initial_mask); m.run(entry)
                assert m.uc.reg_read(UC_ARM_REG_PRIMASK) == 0
                add(label, 'FLASH-primitive-unconditionally-enables-interrupts',
                    entry=hex(entry), initial_PRIMASK=initial_mask, final_PRIMASK=0,
                    ROM_service_stubbed=True, FLASH_done_status_supplied=True)
    return rows


def hooks(profs):
    """Instrument every hook entry/return while running all mandatory checks.

    Register values are observed, not rewritten. All returning invocations must
    preserve R4..R11 and SP. Deliberate reset/power-cut stops are reported as
    incomplete invocations, never counted as verified returns. Min SP excludes
    an automatically scheduled real NVIC exception frame (not modeled here).
    """
    from seplos.thumb import Code, encode_bl
    from seplos.selftest import validate
    from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11
    regs = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
    original = profs['OEM'][0]
    rows = []
    for label in ('1.5.1', '1.6.1'):
        im, facts, build = profs[label]
        for name, site in build['hooks'].items():
            assert im.app[site:site+4] == encode_bl(site, build['entries'][name])
        sites = set(build['hooks'].values()); assert len(sites) == len(build['hooks'])
        allowed = {j for site in sites for j in range(site, site+4)}
        if build.get('cutoff'):
            z = facts['cutoff']['zero_size_offset']; allowed.update(range(z, z+4))
        differences = [a for a, (x,y) in enumerate(zip(original.app, im.app)) if x != y]
        assert set(differences) <= allowed
        names = {}
        for name, entry in build['entries'].items():
            if name.startswith('hook_'): names.setdefault(entry, []).append(name)
        stats = {a: dict(names=n, entered=0, returned=0, max_stack_bytes=0, min_SP=im.sp) for a,n in names.items()}
        trackers = []
        old_init = Machine.__init__
        old_execute = Machine.execute
        def monitored_init(m, image, binding):
            old_init(m, image, binding)
            if image.sha != im.sha: return
            track = dict(frames=[], min_SP=im.sp, instruction_count=0)
            trackers.append(track)
            def finish(address):
                stack = track['frames']; sp = m.uc.reg_read(UC_ARM_REG_SP)
                while stack and address == stack[-1]['return_PC']:
                    v = stack.pop(); s = stats[v['entry']]
                    assert sp == v['SP'], ('hook stack', label, s['names'], hex(sp), hex(v['SP']))
                    observed = tuple(m.uc.reg_read(r) for r in regs)
                    assert observed == v['registers'], ('hook callee registers', label, s['names'], observed, v['registers'])
                    s['returned'] += 1
                    s['max_stack_bytes'] = max(s['max_stack_bytes'], v['SP']-v['min_SP'])
                    s['min_SP'] = min(s['min_SP'], v['min_SP'])
            m._audit_finish = finish
            def observe(uc, address, size, user):
                track['instruction_count'] += 1
                stack = track['frames']
                if not stack and address not in stats: return
                sp = uc.reg_read(UC_ARM_REG_SP)
                track['min_SP'] = min(track['min_SP'], sp)
                for v in stack: v['min_SP'] = min(v['min_SP'], sp)
                finish(address)
                if address in stats:
                    stats[address]['entered'] += 1
                    stack.append(dict(entry=address, return_PC=uc.reg_read(UC_ARM_REG_LR)&~1,
                        SP=sp, min_SP=sp, registers=tuple(uc.reg_read(r) for r in regs)))
            m.uc.hook_add(UC_HOOK_CODE, observe)
        def monitored_execute(m, *args, **kwargs):
            try: return old_execute(m, *args, **kwargs)
            finally:
                # Unicorn's stop address is reached BEFORE its code hook fires.
                if hasattr(m, '_audit_finish'): m._audit_finish(m.uc.reg_read(UC_ARM_REG_PC))
        Machine.__init__ = monitored_init
        Machine.execute = monitored_execute
        extra = []
        try:
            checks = validate(original, im, facts, build)
            if build.get('cutoff'):
                # Existing suite did not enter the heater wrapper itself.
                # Cover normal/locked paths with heater and relay assignments.
                d = facts['cutoff']; r = facts['ram']
                for locked in (False, True):
                    for heating_assignment in (False, True):
                        m = Machine(im, facts); m.defaults(1)
                        group = m.num(r['group0']+3)
                        m.put(r['group0']+3, bytes([(group | 64) if heating_assignment else (group & ~64)]))
                        m.put(d['ram'], bytes([int(locked)])); m.put(d['onoff'], b'\x0f')
                        m.run(build['entries']['hook_cut_heater'])
                        if locked and heating_assignment: assert not m.num(d['onoff']) & 8
                        extra.append(dict(locked=locked, heating_assignment=heating_assignment, passed=True))
        finally:
            Machine.__init__ = old_init; Machine.execute = old_execute
        assert len(checks) == (178 if label == '1.5.1' else 237)
        assert all(x['passed'] for x in checks)
        missing = [s['names'] for s in stats.values() if not s['entered']]
        assert not missing, ('hooks never exercised', missing)
        assert all(s['returned'] for s in stats.values()), stats
        pending = [dict(names=stats[v['entry']]['names'], return_PC=hex(v['return_PC']),
            SP=hex(v['SP']), min_SP=hex(v['min_SP'])) for t in trackers for v in t['frames']]
        assert len(pending) == (8 if label == '1.5.1' else 32), ('unexpected incomplete hook invocations', pending)
        rows.append(dict(passed=True, image=label, kind='all-mandatory-tests-with-hook-ABI-monitor',
            mandatory_checks=checks, hook_sites=len(sites), unique_hook_entries=len(names),
            additional_heater_checks=extra,
            changed_OEM_byte_count=len(differences), original_SP=hex(im.sp),
            lowest_observed_SP=hex(min(t['min_SP'] for t in trackers)),
            hooks={hex(a):s for a,s in stats.items()}, incomplete_invocations=pending,
            instruction_count=sum(t['instruction_count'] for t in trackers),
            no_universal_stack_bound_claim=True))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['persistence', 'startup', 'uart', 'hooks', 'all'])
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if not __debug__: p.error('Python -O unsupported')
    if a.out.exists(): p.error('output already exists; select a fresh path')
    profs = profiles()
    phases = {'persistence': persistence, 'startup': startup, 'uart': uart_interrupts, 'hooks': hooks}
    models = dict(persistence='actual record CRC/writers/readers; sector erase, read and word programming modeled',
        startup='actual reset/init, scheduler thresholds, watchdog and wait loops; selected callees/MMIO modeled as stated',
        uart='actual R/C/D IRQs and FLASH primitives; FIFO/timeouts, ROM service and completion flags modeled',
        hooks='all actual-Thumb mandatory tests plus passive hook return/ABI/SP monitoring; their existing hardware models')
    results = {}
    for phase in phases if a.phase == 'all' else (a.phase,):
        rows = phases[phase](profs)
        results[phase] = dict(passed=True, count=len(rows), model=models[phase], checks=rows)
        print(json.dumps(dict(passed=True, phase=phase, scenario_groups=len(rows))), flush=True)
    result = dict(passed=True, phase=a.phase, hardware_access=False,
        images={k: dict(app_sha256=v[0].sha, build_id=v[2].get('build_id')) for k,v in profs.items()},
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        **(dict(phases=results) if a.phase == 'all' else {k:v for k,v in results[a.phase].items() if k != 'passed'}))
    with a.out.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(passed=True, phase=a.phase, output=str(a.out))))


if __name__ == '__main__': main()
