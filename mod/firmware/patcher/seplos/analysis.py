"""Conservative code-role discovery; no OEM hash/version-to-address table."""
from pathlib import Path
import json
import struct
from .thumb import Code


def unique(values, what):
    if len(values) != 1:
        raise ValueError(f'{what}: expected one proven match, found {len(values)}: {values}')
    return values[0]


def discover(image):
    code = Code(image.app)
    signatures = json.loads(Path(__file__).with_name('signatures.json').read_text())
    functions, evidence = {}, []
    for name, signature in signatures.items():
        hits = [a for a in code.ins if [i.token() for i in code.window(a, len(signature))] == signature]
        at = unique(hits, name)
        functions[name] = at
        if not code.callers(at):
            raise ValueError(name + ': no direct code caller')
        evidence.append({'role': name, 'at': at, 'tokens': len(signature), 'callers': code.callers(at)})

    # Startup veneer resolves main through a PC-relative literal, not a fixed address.
    start = code.window(0xC0, 5)
    if [i.op for i in start] != ['ldr', 'mov', 'bl', 'ldr', 'bx'] or start[1].args != 'sp, r0' or start[4].args != 'r0':
        raise ValueError('unknown startup/main veneer')
    if start[0].literal != image.sp or not start[3].literal & 1:
        raise ValueError('startup/vector ABI mismatch')
    functions['main'] = start[3].literal & ~1
    main = code.body(functions['main'])
    main_sites = {i.at for i in main}
    dip_call = unique([a for a in code.callers(functions['dip']) if a in main_sites], 'main DIP call')

    irq = struct.unpack_from('<I', image.app, 0x50)[0]
    if not irq & 1:
        raise ValueError('non-Thumb UART1 IRQ')
    irq &= ~1
    wrapper = code.window(irq, 4)
    if [i.op for i in wrapper] != ['push', 'bl', 'bl', 'pop'] or wrapper[0].args not in ('{lr}', '{r4, lr}') or wrapper[-1].args != wrapper[0].args.replace('lr', 'pc'):
        raise ValueError('unknown UART1 IRQ wrapper')
    functions.update(irq=irq, tx_irq=wrapper[1].target, rx=wrapper[2].target)
    for name in ('rx', 'tx_irq'):
        window = code.window(functions[name], 5)
        if [i.op for i in window[:4]] != ['push', 'ldr', 'ldr', 'lsls'] or window[1].literal != 0x50011000:
            raise ValueError('UART1 hardware ABI mismatch: ' + name)

    dispatchers = []
    for at in code.ins:
        w = code.window(at, 10)
        if [i.op for i in w] != ['push', 'ldr', 'ldrb', 'cmp', 'bne', 'ldr', 'movs', 'strh', 'bl', 'cmp']:
            continue
        if not w[3].args.endswith('#0x7e') or not w[6].args.endswith('#0x12') or not w[9].args.endswith('#0x0'):
            continue
        calls = [a for a in code.callers(at) if a in main_sites]
        if len(calls) != 1:
            continue
        site = calls[0]
        following = code.window(site, 2)
        before = code.window(site-6, 3)
        if len(following) != 2 or following[1].op != 'bl' or [i.op for i in before] != ['ldrb', 'cmp', 'bne'] or not before[1].args.endswith('#0x4'):
            continue
        dispatchers.append((at, site, w[8].at, w[8].target, following[1].target))
    dispatch, dispatch_site, parser_site, parser, modbus = unique(dispatchers, 'UART1 dispatcher/main ordering')
    functions.update(dispatch=dispatch, parser=parser, modbus=modbus)
    if not dip_call < dispatch_site or dispatch_site - dip_call > 2048:
        raise ValueError('unknown DIP/UART1 scheduler layout')
    for owner, callee in (('loader','iap_read'), ('serializer','iap_write'), ('lcd_write','validator'), ('lcd_write','serializer'), ('lcd_write','capacity_save')):
        body = code.body(functions[owner])
        if not any(i.op == 'bl' and i.target == functions[callee] for i in body):
            raise ValueError(f'{owner}/{callee}: call relationship missing')
    hooks = {'hook_rx': wrapper[2].at, 'hook_dispatch': dispatch_site, 'hook_uart1': parser_site, 'hook_dip': dip_call}
    for name, site in hooks.items():
        evidence.append({'hook': name, 'site': site, 'original_target': code.ins[site].target, 'opcode': image.app[site:site+4].hex()})
    return {'functions': functions, 'hooks': hooks, 'sp': image.sp, 'evidence': evidence, 'original_app_size': len(image.app), 'original_app_sha256': image.sha}
