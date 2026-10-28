"""Recover an already responding UART0 bootloader; no application reset required.

Only use with one pack connected to the RS485-1/2 adapter. The bootloader
has no pack addressing. No retries of write commands; abort on invalid ACK.
Usage: python -I flash_recovery.py PORT IMAGE EXPECTED_SHA256 NEW_LOG
Validates the full EHEX before opening the device. Uses the hardware-tested
256-byte OEM stream and UART0 port; only exact empty WFB write ACKs pass.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
import hashlib
import importlib.util
from pathlib import Path
import sys
import time

spec = importlib.util.spec_from_file_location('recovery_codec', Path(__file__).with_name('flash_gap.py'))
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


def validate(raw, commands, address=0):
    if not raw.startswith(b'::::') or not raw.endswith(b'\r' * 4) or len(raw) < 17:
        raise ValueError('Incomplete bootloader ACK: ' + raw.hex())
    if len(raw) != 17 + int.from_bytes(raw[7:9], 'big'):
        raise ValueError('Bootloader ACK length mismatch')
    if (sum(raw[4:-6]) + int.from_bytes(raw[-6:-4], 'big')) & 65535:
        raise ValueError('Bootloader ACK checksum mismatch')
    if raw[4:7] not in commands or int.from_bytes(raw[9:11], 'big') != address:
        raise ValueError('Unexpected bootloader ACK: ' + raw.hex())
    return raw[11:-6]


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port');parser.add_argument('image');parser.add_argument('expected_sha256');parser.add_argument('new_log')
    args=parser.parse_args()
    port_path, image_path, expected_sha, log_path = args.port, args.image, args.expected_sha256, args.new_log
    image = Path(image_path)
    if hashlib.sha256(image.read_bytes()).hexdigest() != expected_sha:
        raise ValueError('Image SHA256 does not match verified release')
    stream = codec.stream_of(image)
    blocks = [stream[i:i+256].ljust(256, b'\0') for i in range(0, len(stream), 256)]
    plan = [(b'WFE', 0, b'')] + [(b'WFD', 16*i, block) for i, block in enumerate(blocks)] + [(b'WFG', 0, b'')]
    # Validate every outgoing frame before opening the device or writing flash.
    frames = [codec.boot_frame(command, address, data) for command, address, data in plan]
    for frame, (command, address, data) in zip(frames, plan):
        if validate(frame, (command,), address) != data:
            raise ValueError('Unexpected outgoing frame')
    started = time.monotonic()
    with Path(log_path).open('x') as log:
        port = codec.Port(port_path, log)
        try:
            port.send(codec.boot_frame(b'RFL'))
            reply = port.read_until(lambda raw: raw.endswith(b'\r'*4), 3)
            if validate(reply, (b'RFB',)) != b'\1\0':
                raise ValueError('Only verified 256-byte bootloader is supported')
            time.sleep(.35)
            for frame, (command, address, _) in zip(frames, plan):
                port.send(frame)
                reply = port.read_until(lambda raw: raw.endswith(b'\r'*4), 10)
                if validate(reply, (b'WFB',)):
                    raise ValueError('Unexpected nonempty write ACK')
                log.flush()
                if command != b'WFD' or (address//16+1) % 25 == 0:
                    print(f'{command.decode()} block={address//16} acknowledged, {time.monotonic()-started:.1f}s', flush=True)
                if command != b'WFG':
                    time.sleep(.35)
            log.write('STATE all blocks acknowledged; application verification still required\n')
            print(f'{len(blocks)} blocks acknowledged; verify the application separately', flush=True)
        finally:
            import os
            os.close(port.fd)


if __name__ == '__main__':
    main()
