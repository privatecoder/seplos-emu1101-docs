"""Read or change the display format of one addressed pack.

Select --port explicitly; RS485-1/2 uses UART0 at 19200 baud.
Optional --uart1 uses CAN-socket RS485 at 9600 baud and requires MAINT parameter access.
Only Group7.Bit4 changes; display enable and protection parameters are preserved.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import uuid

ROOT=PROJECT_ROOT


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


ascii=load('display_ascii_codec','maintenance_client.py')
client=load('display_binary_codec','parameter_client.py')
address_check=load('display_address_check','restart_pack.py').valid_address


def exchange_ascii(port,address,command,info=b''):
    request=ascii.frame(command,info.hex().upper(),address)
    port.reset_input_buffer();port.timeout=.05
    if port.write(request)!=len(request):raise OSError('Incomplete transmission')
    port.flush()
    _,(rtn,data)=ascii.read_reply(lambda wait:port.read(512),request,timeout=4)
    if rtn:raise ValueError(f'BMS returned RTN {rtn:02X}')
    return data


def read_config(port,address,uart1):
    if uart1:
        port.reset_input_buffer()
        return client.read_parameters(client.SerialStream(port),address,timeout=4)
    raw=exchange_ascii(port,address,0x47)
    if len(raw)!=169 or raw[0]!=address:raise ValueError('Invalid UART0 parameter block or wrong pack address')
    return client.decode_parameters(raw[1:],address)


def read_telemetry(port,address):
    return exchange_ascii(port,address,0x42)


def capacity_guard(raw,config,address):
    if len(raw)!=75 or raw[0]!=0 or raw[1]!=address or raw[2]!=16:
        raise ValueError('No complete 16S telemetry for target address; no write')
    learned=int.from_bytes(raw[55:57],'big');nominal=config['parameters_u16'][58]
    if abs(learned-nominal)>=1000:
        raise ValueError('Capacity difference at least 10 Ah: A1 would change learned capacity; aborted')
    return dict(learned_cAh=learned,nominal_cAh=nominal)


def write_config(port,address,config,uart1):
    payload=client.encode_parameters(config,address)
    name=bytes.fromhex(config['device_name_hex'])
    if len(name)!=10:raise ValueError('Device name must contain exactly 10 bytes')
    if uart1:
        port.reset_input_buffer()
        ack=client.exchange(client.SerialStream(port),address,0xA1,payload,timeout=4)
    else:
        ack=exchange_ascii(port,address,0xA1,bytes([address])+payload+name)
    if ack:raise ValueError('Unexpected data in write ACK')


def set_format(port,address,mode,backup_dir,uart1=False):
    address_check(address)
    if mode not in ('kurz','erweitert','status'):raise ValueError('Unknown display format')
    before=read_config(port,address,uart1)
    old=before['function_switches'][7]
    result=dict(address=address,route='uart1' if uart1 else 'uart0',before_group7=old,
                after_group7=old,format='erweitert' if old&16 else 'kurz',
                lcd_enabled=bool(old&8),changed=False)
    if mode=='status' or bool(old&16)==(mode=='erweitert'):return result
    telemetry=read_telemetry(port,address);capacity=capacity_guard(telemetry,before,address)
    requested=copy.deepcopy(before)
    requested['function_switches'][7]=(old|16) if mode=='erweitert' else (old&~16)
    # Validate the complete block before saving or writing.
    client.encode_parameters(requested,address)
    backup_dir=Path(backup_dir);backup_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path=backup_dir/f'pack-{address:02d}-display-{stamp}-{uuid.uuid4().hex[:8]}.json'
    with path.open('x') as output:
        json.dump(dict(address=address,route=result['route'],parameters=before,
                       telemetry_hex=telemetry.hex(),capacity_guard=capacity),output,indent=2)
        output.write('\n')
    result['backup']=str(path)
    if read_config(port,address,uart1)!=before:
        raise RuntimeError(f'Parameters changed concurrently; no write. Backup: {path}')
    try:
        write_config(port,address,requested,uart1)
    except (OSError,ValueError,RuntimeError) as error:
        raise RuntimeError(f'Write outcome unknown/rejected; no retry. Read fresh state. Backup: {path}. {error}') from error
    try:observed=read_config(port,address,uart1)
    except (OSError,ValueError,RuntimeError) as error:
        raise RuntimeError(f'Write acknowledged, readback failed; no retry. Backup: {path}. {error}') from error
    if observed!=requested:raise RuntimeError(f'Readback differs; no more write attempts. Backup: {path}')
    result.update(changed=True,after_group7=requested['function_switches'][7],format=mode,readback_verified=True)
    with path.with_name(path.stem+'-result.json').open('x') as output:
        json.dump(dict(result,parameters=observed),output,indent=2);output.write('\n')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address',type=lambda value:int(value,10),help='Pack address decimal 0..15, for example 07')
    parser.add_argument('mode',choices=('kurz','erweitert','status'))
    parser.add_argument('--port',required=True)
    parser.add_argument('--uart1',action='store_true',help='CAN-socket RS485/9600 instead of RS485-1/2/19200')
    parser.add_argument('--backup-dir',type=Path,default=LOCAL_ROOT/'devices/backups/parameters')
    args=parser.parse_args(argv)
    try:
        address_check(args.address)
        import serial
        with serial.Serial(args.port,9600 if args.uart1 else 19200,timeout=.05,write_timeout=3,exclusive=True) as port:
            result=set_format(port,args.address,args.mode,args.backup_dir,args.uart1)
        print(f"Pack {args.address:02d}: Display format {result['format']}, Group 7 = {result['after_group7']:02X}, Display port {'an' if result['lcd_enabled'] else 'aus'}.")
        print('Change acknowledged and read back.' if result['changed'] else 'No change written.')
        if result.get('backup'):print('Backup: '+result['backup'])
        return 0
    except (OSError,ValueError,RuntimeError,ImportError) as error:
        print(f'Error: {error}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
