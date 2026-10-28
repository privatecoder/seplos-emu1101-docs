"""Restart one pack over UART0/RS485-1/2 at 19200 baud and verify its return.

Decimal address 0..15, for example 07. Select the adapter explicitly with --port.
No broadcast, flashing or automatic restart retries.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

spec=importlib.util.spec_from_file_location('restart_ascii',Path(__file__).with_name('maintenance_client.py'))
ascii=importlib.util.module_from_spec(spec);spec.loader.exec_module(ascii)


def valid_address(address):
    if type(address) is not int or not 0<=address<=15:
        raise ValueError('Pack address must be decimal 0..15; broadcasts are forbidden')
    return address


def query(port,address,command,timeout=3):
    request=ascii.frame(command,'',address)
    port.reset_input_buffer();port.timeout=.05
    if port.write(request)!=len(request):raise OSError('Incomplete query write')
    port.flush()
    _,(rtn,payload)=ascii.read_reply(lambda wait:port.read(512),request,timeout)
    if rtn:raise ValueError(f'BMS returned RTN{rtn:02X}')
    return payload


def restart(port,address,wait=20,now=time.monotonic,sleep=time.sleep):
    valid_address(address)
    if not math.isfinite(wait) or wait<1:raise ValueError('Wait must be at least 1 s')
    version=query(port,address,0x51)
    serial=query(port,address,0xA4)
    request=ascii.frame(0x45,'000600',address)
    port.reset_input_buffer()
    written=port.write(request);port.flush()
    if written!=len(request):
        raise RuntimeError('Restart sent partially; outcome unknown, do not retry automatically')
    deadline=now()+wait;outage=False
    while now()<deadline:
        try:
            returned=query(port,address,0x51,timeout=min(.7,max(.01,deadline-now())))
        except TimeoutError:
            outage=True
        else:
            if outage:
                returned_serial=query(port,address,0xA4)
                if returned!=version or returned_serial!=serial:
                    raise RuntimeError('Version or serial number changed after restart')
                return dict(address=address,baud=19200,route='uart0',outage_observed=True,
                            returned=True,version_hex=returned.hex(),bms_sn_hex=serial.hex(),
                            reset_frame=request.hex(),reset_sent_once=True)
        sleep(min(.25,max(0,deadline-now())))
    raise RuntimeError('Restart sent, return after outage not confirmed; no automatic retry')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address',type=lambda value:int(value,10),help='decimal 0..15, for example 07')
    parser.add_argument('--port',default=None)
    parser.add_argument('--wait',type=float,default=20,help='Seconds to await return, default: 20')
    parser.add_argument('--dry-run',action='store_true',help='Print the restart frame without accessing hardware')
    parser.add_argument('--log',type=Path,help='New JSON file for result or failure')
    args=parser.parse_args(argv);output=None
    try:
        valid_address(args.address)
        if not math.isfinite(args.wait) or args.wait<1:raise ValueError('Invalid wait time')
        if args.dry_run:
            print(ascii.frame(0x45,'000600',args.address).decode().rstrip());return 0
        if not args.port:parser.error('--port is required unless --dry-run is selected')
        if args.log:output=args.log.open('x')
        import serial
        print(f'Pack {args.address:02d} via {args.port}, UART0/19200 baud: one restart and return check.',flush=True)
        with serial.Serial(args.port,19200,timeout=.05,write_timeout=3,exclusive=True) as port:
            result=restart(port,args.address,args.wait)
        if output:json.dump(dict(passed=True,**result),output,indent=2);output.write('\n')
        print(f'Pack {args.address:02d} reachable again; outage and identical serial number confirmed.')
        return 0
    except (OSError,ValueError,RuntimeError,ImportError) as error:
        if output:json.dump(dict(passed=False,address=args.address,error=str(error)),output,indent=2);output.write('\n')
        print(f'Error: {error}',file=sys.stderr);return 1
    finally:
        if output:output.close()


if __name__=='__main__':raise SystemExit(main())
