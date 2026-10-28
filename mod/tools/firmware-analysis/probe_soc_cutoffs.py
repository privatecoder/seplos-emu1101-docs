#!/usr/bin/env python3
"""Execute SOC-only warning/disconnect and counting-floor counterexamples.

No physical ports. Uses the persistent, SHA-bound SOC profile and real Thumb
instructions. A reported discharge permit is not an electrical measurement.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

PROFILE_PATH=Path(__file__).with_name('soc_profile_v16.py')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if not __debug__:parser.error('Python -O is unsupported')
    if args.out.exists():parser.error('Choose a new output')
    assert PROFILE_PATH.exists(),'persistent SOC profile is not implemented'
    spec=importlib.util.spec_from_file_location('soc_cutoff_profile',PROFILE_PATH)
    p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
    loaded=p.load_images();rows=[]
    for label in loaded['images']:
        def test(name,soc=177,event=0,protect=True,full_flag=False,strong_charge=False,expect_discharge=True):
            m=p.new_board(loaded,label);p.seed_soc(m,soc)
            p.write(m,'event2',event,1)
            if not protect:
                m.put(p.RAM['group5'],bytes([m.num(p.RAM['group5'])&~p.BITS['soc_protection']]))
            if full_flag:p.write(m,'soc_flags',p.BITS['full_flag'],1)
            if strong_charge:p.write(m,'system_status',0x82,1)
            p.run(m,'soc_update');p.run(m,'soc_alarms');p.run(m,'discharge')
            state=p.read_state(m)
            assert state['discharge_permitted']==expect_discharge,(name,state)
            rows.append(dict(image=label,name=name,passed=True,
                             minimum_mV=m.num(p.RAM['min_cell'],2),**state))
            return m,state

        _,s=test('17.7-percent-normal-voltage-no-SOC-alarm')
        assert s['event6']&12==0
        _,s=test('14.4-percent-warning-only',144)
        assert s['event6']&12==4
        _,s=test('14.5-percent-rounds-to15-no-warning',145)
        assert s['event6']&12==0
        _,s=test('4.4-percent-protection-normal-voltage',44,expect_discharge=False)
        assert s['event2']==0 and s['event6']&12==8
        assert not s['precharge_running'] and not s['discharge_gpio_high']
        _,s=test('4.5-percent-rounds-to5-no-protection',45)
        assert s['event6']&12==4
        _,s=test('SOC-protection-mask-disabled-retains-warning',44,protect=False)
        assert s['event6']&12==4
        _,s=test('disabling-SOC-protection-does-not-disable-cell-UVP',44,event=8,protect=False,expect_discharge=False)
        assert s['event2']==8
        _,s=test('original-3A-charge-recovery-bypasses-SOC-discharge-inhibit',44,strong_charge=True)
        assert s['event6']&8
        _,s=test('97-percent-without-full-flag-no-intermittent-wait',970)
        assert s['event6']&2==0
        m,s=test('97-percent-with-full-flag-intermittent-wait',970,full_flag=True)
        assert s['event6']&2
        p.run(m,'charge')
        assert m.num(p.RAM['onoff'])&2,'no Hard-Stop: wait alone must not open charge MOSFET'
        rows[-1]['charge_permitted_without_hard_stop']=True

        for minimum,expected in ((3296,0),(3000,-100)):
            m=p.new_board(loaded,label);p.seed_soc(m,54)
            p.write(m,'min_cell',minimum,2);p.write(m,'current',-100,2,signed=True)
            p.write(m,'system_status',1,1);before=m.num(p.RAM['charge'],4)
            p.run(m,'coulomb_tick');delta=m.num(p.RAM['charge'],4)-before
            assert delta==expected,(minimum,delta)
            rows.append(dict(image=label,name='low-SOC-counting-floor-min-cell-'+str(minimum),passed=True,minimum_mV=minimum,delta_centiAs=delta))
    result=dict(passed=True,tests=len(rows),hardware_access=False,firmware_modified=False,
                profile=p.PROFILE['name'],source_profile_sha256=p.profile_sha256(),results=rows,
                source_probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                app_sha256={label:image.sha for label,image in loaded['images'].items()},
                limitations=['Modeling of GPIO/UART/IAP; no physical current or MOSFET measurement',
                             'Inverter reaction to warnings and external low-SOC limits is separate'])
    with args.out.open('x') as output:json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))


if __name__=='__main__':main()
