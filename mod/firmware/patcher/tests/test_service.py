"""Storage diagnostics, verified SOC checkpoint and reset ordering."""
from pathlib import Path
import copy, json, sys, unittest
import hashlib, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.build import build
from seplos.machine import Machine,ascii_frame
from seplos.selftest import ascii_payload
from seplos.marker_uart0_tests import uart0_exchange
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_SP


def soc_record(remaining=12000,full=28000):
    data=b'\xa0\x14'+remaining.to_bytes(2,'little')+full.to_bytes(2,'little')
    data+=(123456).to_bytes(4,'little')+(654321).to_bytes(4,'little')
    data+=(23).to_bytes(2,'little')+(45).to_bytes(2,'little')+(67).to_bytes(2,'little')
    crc=0xffff
    for byte in data:
        crc^=byte
        for _ in range(8):crc=(crc>>1)^(0xa001 if crc&1 else 0)
    return data+crc.to_bytes(2,'little')+b'\xff\xff'


class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
        cls.facts=fixture('oem-16.06.13-facts')['facts']
        cls.facts=copy.deepcopy(cls.facts)
        cls.image,cls.report=build(cls.original,cls.facts,13,maint_version='1.6.3')

    def board(self,address=1):
        m=Machine(self.image,self.facts);m.defaults(address)
        m.put(m.r['group0'],bytes([m.num(m.r['group0'])|8]))
        m.run(m.f['serializer']);m.nv_ops.clear();m.nv_step=0;m.saves.clear()
        base=m.r['learned']-14
        m.put(base+12,(12000).to_bytes(2,'little'));m.put(base+14,(28000).to_bytes(2,'little'))
        m.put(base+16,(428).to_bytes(2,'little'));m.put(base+0x54,(111).to_bytes(2,'little'))
        m.put(base+0x58,(123456).to_bytes(4,'little'));m.put(base+0x5c,(654321).to_bytes(4,'little'))
        m.put(base+0x60,(23).to_bytes(2,'little'))
        m.put(m.r['coulomb_max']+24,(45).to_bytes(2,'little'));m.put(m.r['coulomb_max']+26,(67).to_bytes(2,'little'))
        return m

    def diag(self,m,port='C',target=None,data=b'\4'):
        adr=m.num(m.r['address']);packet=ascii_frame(adr if target is None else target,0x64,data)
        if port=='R':
            raw=uart0_exchange(m,packet)
            return ascii_payload(raw,adr) if raw else None
        raw=m.transact(packet,True)
        return ascii_payload(raw,adr) if raw else None

    def reset(self,m,port='C',target=None,first=0):
        adr=m.num(m.r['address']);packet=ascii_frame(adr if target is None else target,0x45,bytes([first,6,0]))
        m.pause=m.facts['power_rtc']['reset'];m.output.clear()
        if port=='R':
            raw=uart0_exchange(m,packet)
            if m.uc.reg_read(UC_ARM_REG_PC)==m.pause:return None
            return ascii_payload(raw,adr) if raw else None
        m.feed(packet);site=m.facts['hooks']['hook_dispatch'];m.execute(site,site+4)
        if m.uc.reg_read(UC_ARM_REG_PC)==m.pause:return None
        m.pause=None;raw=m.drain()
        return ascii_payload(raw,adr) if raw else None

    def test_version_and_capabilities(self):
        m=self.board();rtn,data=ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1)
        self.assertEqual((rtn,data[:4],data[7:10],data[-1]),(0,b'MNT\4',b'\1\6\3',0xfe))

    def test_diagnostics_read_only_on_R_C_and_slaves(self):
        for adr in (0,1,11,21):
            for port in ('R','C'):
                with self.subTest(address=adr,port=port):
                    m=self.board(adr);m.put(m.r['group0'],b'\0')
                    for a in (0x2b000,0x2c000):m.put(a,soc_record())
                    before=m.read(0x25000,0x8000);cache=m.read(m.facts['cutoff']['ram'],4)
                    self.assertEqual(self.diag(m,port),(0,bytes([1,1,1,1,1,1,1,0,0,6])))
                    self.assertEqual(m.read(0x25000,0x8000),before);self.assertEqual(m.read(m.facts['cutoff']['ram'],4),cache)
                    self.assertEqual(m.nv_ops,[]);self.assertEqual(m.saves,[])

    def test_diagnostics_corrupt_copies_no_repair(self):
        m=self.board();m.put(0x25000+171,bytes([m.num(0x25000+171)^1]))
        m.put(0x2b000,b'\xff'*256);m.put(0x2c000,soc_record());m.put(0x2c000+20,b'\0\0')
        before=m.read(0x25000,0x8000)
        self.assertEqual(self.diag(m),(0,bytes([1,2,1,0,0,2,0,255,0,6])))
        self.assertEqual(m.read(0x25000,0x8000),before);self.assertEqual(m.nv_ops,[])

    def test_foreign_and_FF_diagnostics_silent(self):
        for port in ('R','C'):
            for target in (0,2,255):
                m=self.board();self.assertIsNone(self.diag(m,port,target));self.assertEqual(m.nv_ops,[])

    def test_reset_saves_both_copies_before_watchdog(self):
        for port,first in (('C',0),('R',0),('R',1)):
            with self.subTest(port=port,first=first):
                m=self.board();sp=m.uc.reg_read(UC_ARM_REG_SP)
                self.assertIsNone(self.reset(m,port,first=first))
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),m.facts['power_rtc']['reset'])
                self.assertEqual(m.read(0x2b000,22),soc_record()[:22]);self.assertEqual(m.read(0x2c000,22),soc_record()[:22])
                self.assertEqual(len(m.nv_ops),4);self.assertEqual(m.read(0x25000,4096),m.read(0x26000,4096))

    def test_checkpoint_failure_returns08_no_reset_preserves_backup(self):
        for port in ('R','C'):
            with self.subTest(port=port):
                m=self.board();old=soc_record(7500)
                for a in (0x2b000,0x2c000):m.put(a,old)
                m.nv_fail_at={2};sp=m.uc.reg_read(UC_ARM_REG_SP)
                self.assertEqual(self.reset(m,port),(8,b''))
                self.assertNotIn(m.facts['power_rtc']['reset'],m.executed)
                self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP),sp)
                self.assertEqual(m.read(0x2c000,24),old)
                self.assertEqual(m.num(m.r['learned']-14+0x54,2),111)

    def test_C_denied_reset_does_not_save(self):
        m=self.board();m.put(m.r['group0'],bytes([m.num(m.r['group0'])&~8]))
        self.assertEqual(self.reset(m),(5,b''));self.assertEqual(m.nv_ops,[])

    def test_R_broadcast_reset_is_silent_and_does_not_save(self):
        m=self.board();self.assertIsNone(self.reset(m,'R',255));self.assertEqual(m.nv_ops,[])
        self.assertNotIn(m.facts['power_rtc']['reset'],m.executed)

    def test_R_invalid_local_address_never_resets(self):
        for local in (22,255):
            m=self.board(local);self.assertIsNone(self.reset(m,'R',local));self.assertEqual(m.nv_ops,[])
            self.assertNotIn(m.facts['power_rtc']['reset'],m.executed)


    def test_publication_requires_service_suite_and_capabilities(self):
        from seplos.cli import run_worker,SCHEMA
        from seplos.marker_uart0_tests import REQUIRED as M
        from seplos.permissions_tests import REQUIRED as P
        from seplos.service_tests import REQUIRED as S
        source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
        base=dict(schema=SCHEMA,mode='patch',maint_version='1.6.3',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='maint163-real-thumb-v1',suite_complete=True,
            tests=[dict(name=n,passed=True) for n in [*M,*P,*S,*[f'cutoff-{i}' for i in range(40)]]],build=dict(patch_version='1.6.3',info_format=4,info_bytes=19,uart0_marker=True,image_flags=254,positive_flags=True,service=True,extended_diagnostics=True,checkpoint_before_reset=True))
        for kind,error in (('capability','service capabilities missing'),('suite','mandatory service suite incomplete')):
            report=copy.deepcopy(base)
            if kind=='capability':report['build']['image_flags']&=~64
            else:report['tests']=[t for t in report['tests'] if t['name']!=S[0]]
            with tempfile.TemporaryDirectory() as temp:
                worker=Path(temp)/'worker.py'
                worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
                result,artifacts=run_worker(source,'patch',worker=worker,maint_version='1.6.3')
                self.assertEqual(artifacts,{});self.assertIn(error,result['error'])


if __name__=='__main__':unittest.main()
