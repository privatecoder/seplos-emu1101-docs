#!/usr/bin/env python3
"""Reusable SOC facts and emulator setup for verified OEM16.06.13/MAINT1.6.

This is a version-bound analysis profile, not a BMS controller implementation.
It names the fields, units, entry points, flags, persistence and command rules
already proved by the Cortex-M0 counterexamples. run() executes real Thumb.
No serial/network access. Imported without Unicorn until load_images() is used.
Running this module prints the knowledge contract as JSON, without emulation.
"""

# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, PATCHER_ROOT, research_input
from pathlib import Path
import hashlib
import json
import sys

ROOT = PROJECT_ROOT
FUNCTIONS={
    'capacity_command':0x09b4,'capacity_save':0x5564,'capacity_load':0x55ce,
    'voltage_rules':0x8c08,'low_voltage_correction':0x8dc8,
    'calibration_gate':0x8e0c,'capacity_learning':0x8e4c,
    'soc_update':0x8f56,'coulomb_tick':0x9044,'soc_alarms':0x9190,
    'cycle_count':0x9250,'discharge':0x7184,'charge':0x6ffa,
    'empty_shutdown_cause':0x887c,'power_state':0x8a24,
}
RAM={
    'words':0x20001300,'small':0x200013f0,'group0':0x20000028,'group5':0x2000002d,
    'max_cell':0x20000cc8,'min_cell':0x20000cca,'current':0x20000cd0,
    'pack_voltage':0x20000cd2,'remaining':0x20000cd4,'learned_full':0x20000cd6,
    'soc_tenths':0x20000cd8,'saved_soc_tenths':0x20000d1c,'soc_whole':0x20000d1e,
    'charge_max':0x200015e0,'charge':0x200015ec,
    'plausibility_seconds':0x20001602,'low_charge_seconds':0x20001604,
    'voltage90_seconds':0x20001606,'voltage_full_seconds':0x20001608,
    'event2':0x20000031,'event6':0x20000035,'event8_internal':0x20000005,
    'system_status':0x200000ac,'soc_flags':0x200000f5,'onoff':0x200000b5,
    'onoff_previous':0x200000b6,'power_gpio':0x50002000,
    'charge_voltage_drift_threshold':0x20000d0e,
}
BITS={
    'soc_warning':4,'soc_protection':8,'intermittent_wait':2,
    'full_flag':2,'empty_flag':1,'current_zero_uncalibrated':16,
    'system_discharge':1,'system_charge':2,'system_standby':16,'system_off':32,
    'system_charge3A':128,'discharge_on':1,'charge_on':2,'precharge_on':16,
    'discharge_gpio':1<<13,'charge_gpio':1<<12,'precharge_gpio':1<<15,
}
PROFILE={
    'name':'OEM16.06.13 / fixed MAINT1.6 SOC contract',
    'version_scope':'Never apply these addresses to another OEM without revalidation',
    'oem_app_sha256':'5c36a7e08fb881b3c2ca6a22888ecb63585c3eb6811fb67b67cc9d0d0ecdde95',
    'maint_app_sha256':'be2ecc7549c7ee16d46eed1f10c256d7231cc5ed961ec90f0bae87e0cfc40d2d',
    'maint_build_id':'18daf61d8a93671d','functions':FUNCTIONS,'ram':RAM,'bits':BITS,
    'units':{'charge':'0.01 A*s, signed32','charge_max':'0.01 A*s',
             'current':'0.01 A, signed16','remaining':'0.01 Ah','learned_full':'0.01 Ah',
             'cell_voltage':'mV','pack_voltage':'0.01 V','soc_tenths':'0.1 percent',
             'soc_whole':'(soc_tenths+5)//10, integer percent','timers':'1-second calls'},
    'formulas':{'remaining':'Q//3600','soc_tenths':'min(1000, remaining*1000//learned_full)',
                'soc_whole':'(soc_tenths+5)//10','full_counter':'learned_full*3600'},
    'counting':{'period_seconds':1,'charging':'Q += current_cA',
        'discharging':'Q += signed_current_cA; negative for discharge',
        'limits':'clamp Q to0..learned_full*3600 during soc_update',
        'upper_hold':'charging and soc_tenths>=982 and max_cell<P0: no increment',
        'lower_hold':'discharging and soc_tenths<9 and no cell/pack UVP: no decrement',
        'idle':'normally subtract3 centiAs; above P80 subtract20; voltage/low-SOC exceptions apply',
        'voltage_is_not_SOC':'no continuous voltage-to-SOC conversion or neighbour-pack equalization'},
    'parameters':{'nominal_capacity':58,'fallback_remaining':59,'soc_warning':78,
                  'soc_protection':79,'recharge_resume':80,'cycle_accumulation':81},
    'voltage_rules':[
        {'target_percent':23,'pack_per_cell_V':3.30,'min_cell_V':3.200,'low_charge_seconds_gt':1800,'old_soc_tenths_lt':180},
        {'target_percent':70,'pack_per_cell_V':3.37,'min_cell_V':3.320,'low_charge_seconds_gt':1800,'old_soc_tenths_lt':650},
        {'target_percent':90,'condition':'(pack>=N*3.40 and min>=3.340 for>1800s) OR max>=P0','low_charge_seconds_gt':30,'old_soc_tenths_lt':850},
        {'target_percent':98,'condition':'pack>=N*Vfull and min>=3.350 for>30s','low_charge_seconds_gt':30,'old_soc_tenths_lt':950},
        {'target_percent':100,'condition':'pack>=N*Vfull and min>=3.350 for>1800s','low_charge_seconds_gt':30,'old_soc_tenths_lt':990},
    ],
    'voltage_prerequisites':{'min_mV_ge':2000,'max_mV_le':4300,
        'plausible_calibrated_seconds_gt':30,'charge3A_status_on_cA':301,
        'charge3A_status_off_below_cA':281,'Vfull':'clamp(P0,3450,3500)//10 in0.01V'},
    'soc_only_rules':{
        'warning':'soc_whole<P78; Event6.bit2 if Group5.bit2; no local discharge cutoff',
        'protection':'soc_whole<P79; Event6.bit3 if Group5.bit3; normal discharge/precharge inhibit',
        'recovery_exception':'original charge3A status bypasses normal discharge inhibit; UVP has extra branch',
        'counting_floor':'discharging and soc_whole<P79+1 and min_cell>P2: stop decrementing Q',
        'intermittent':'full_flag and soc_whole>P80 and Group5.bit1; removes normal charge eligibility; Hard-Stop is separate',
        'empty_shutdown':'(UVP or empty_flag) and no charging after60calls; SOC<P79 alone is not this cause',
    },
    'rounding_examples':{'synthetic_parameters':{'P78':15,'P79':5,'P80':96},
        'warning_tenths':144,'no_warning_tenths':145,
        'protection_tenths':44,'no_protection_tenths':45,
        'counting_floor_example_tenths':54,
        'floor_condition':'min_cell>P2; exact stopping value depends on prior Q and one-second current step'},
    'commands':{
        '49/3B':{'info':'00 3B u16_BE_cAh','effect':'Q=value*3600; P59 field unchanged','guard':'value<=learned_full','immediate_save':False,'UART1_MAINT1_6':'RTN04'},
        '49/3A':{'info':'00 3A u16_BE_cAh','effect':'learned_full=value; Qmax=value*3600; P58 field unchanged','guard':'remaining<=value','immediate_save':False},
        'A1/P59':{'effect':'parameter/fallback field only; does not set Q'},
        'A1/capacity':{'effect':'if abs(P58-learned_full)>=1000cAh: learned_full=P58, Qmax=P58*3600, save6'},
    },
    'persistence':{'block':6,'primary':0x2b000,'backup':0x2c000,'record_length':20,
        'periodic_interval':None,'checkpoint':'no charge/discharge bits; abs(SOC-saved_SOC)>50 tenths',
        'other_triggers':['new cycle','learning complete','controlled shutdown','A1 capacity correction','45/type5'],
        'fallback':'remaining=P59, full=P58, energy/cycles=0',
        'reset':'no automatic Q save before watchdog reset; older valid checkpoint may return'},
    'evidence':['local/research/soc/evidence/SOC-2026-10-21-final.json',
                'local/research/soc/evidence/SOC-Abschaltung-2026-10-21-final.json'],
}


def profile_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def load_images():
    if not __debug__:raise RuntimeError('Python -O is unsupported')
    sys.path.insert(0,str(PATCHER_ROOT))
    from seplos.image import Image
    from seplos.machine import Machine
    report=json.loads(research_input('pack-lock-1.6').read_text())
    oem=Image.read(ROOT/'vendor/firmware/CAN1101[V16.06.13_PN01_250607].ehex')
    patched=Image.read(ROOT/'local/releases/CAN1101[V16.06.13_PN01_250607_MAINT_V1_6_CUTOFF].ehex')
    if oem.sha!=PROFILE['oem_app_sha256'] or patched.sha!=PROFILE['maint_app_sha256']:
        raise ValueError('SOC profile image SHA mismatch; re-analyse this build first')
    if report['build']['build_id']!=PROFILE['maint_build_id']:
        raise ValueError('SOC profile build ID mismatch')
    facts=report['facts']
    if facts['ram']['coulomb_max']!=RAM['charge_max'] or facts['ram']['learned']!=RAM['learned_full']:
        raise ValueError('SOC RAM binding mismatch')
    for start,end in ((0x9b4,0xa22),(0x5564,0x5694),(0x8c08,0x92bc),(0x7184,0x7254)):
        if oem.app[start:end]!=patched.app[start:end]:raise ValueError('Reviewed SOC code changed')
    return dict(facts=facts,machine_class=Machine,images={'OEM16.06.13':oem,'MAINT1.6':patched})


def write(machine,name,value,width,signed=False):
    machine.put(RAM[name],int(value).to_bytes(width,'little',signed=signed))


def seed_soc(machine,tenths,full=28000):
    """Synthetic initial condition, not a hardware write or controller rule."""
    if not 0<=tenths<=1000 or not 0<full<=65000:raise ValueError('Synthetic capacity range')
    remaining=full*tenths//1000
    for key,value,width in (('remaining',remaining,2),('learned_full',full,2),
        ('charge',remaining*3600,4),('charge_max',full*3600,4),
        ('soc_tenths',tenths,2),('saved_soc_tenths',tenths,2),('soc_whole',(tenths+5)//10,2)):
        write(machine,key,value,width)


def new_board(loaded,label):
    """16S synthetic board, no alarms, no patch latch, discharge already on."""
    from unicorn.arm_const import UC_ARM_REG_R0
    m=loaded['machine_class'](loaded['images'][label],loaded['facts']);m.defaults(0)
    m.soc_record=None;m.soc_saves=[];facts=loaded['facts'];f=facts['functions'];r=facts['ram']
    def iap(board,pc):
        if board.uc.reg_read(UC_ARM_REG_R0)!=6:return False
        if pc==f['iap_read']:
            if board.soc_record is not None:board.put(r['iap_buffer'],board.soc_record)
            board.ret(int(board.soc_record is not None));return True
        if pc==f['iap_write']:
            a=r['iap_buffer'];board.soc_record=board.read(a,board.num(a+1))
            board.soc_saves.append(board.soc_record.hex());board.ret(1);return True
        return False
    m.callback=iap
    for index,value in ((0,3550),(1,3450),(2,3000),(3,3100),(58,28000),(59,7500)):
        m.put(RAM['words']+index*2,value.to_bytes(2,'little'))
    for index,value in ((5,16),(18,15),(19,5),(20,96),(21,80)):
        m.put(RAM['small']+index,bytes([value]))
    m.put(RAM['group0'],bytes.fromhex('ffdfff3fbf9fbf1f'))
    for key,value,width in (('max_cell',3298,2),('min_cell',3296,2),('pack_voltage',5275,2),
        ('current',0,2),('system_status',16,1),('event2',0,1),('event6',0,1),
        ('event8_internal',0,1),('soc_flags',0,1),('onoff',3,1),('onoff_previous',1,1),
        ('power_gpio',BITS['charge_gpio']|BITS['discharge_gpio'],4),
        ('charge_voltage_drift_threshold',5440,2)):
        write(m,key,value,width)
    seed_soc(m,177);return m


def run(machine,role):
    return machine.run(FUNCTIONS[role])


def read_state(machine):
    onoff=machine.num(RAM['onoff']);gpio=machine.num(RAM['power_gpio'],4)
    return dict(soc_tenths=machine.num(RAM['soc_tenths'],2),soc_whole=machine.num(RAM['soc_whole'],2),
        event2=machine.num(RAM['event2']),event6=machine.num(RAM['event6']),
        discharge_permitted=bool(onoff&BITS['discharge_on']),precharge_running=bool(onoff&BITS['precharge_on']),
        discharge_gpio_high=bool(gpio&BITS['discharge_gpio']),soc_flags=machine.num(RAM['soc_flags']))


if __name__=='__main__':print(json.dumps(PROFILE,indent=2))
