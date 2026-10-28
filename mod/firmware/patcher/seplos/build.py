"""Assemble versioned MAINT appendix and guard every OEM hook/startup edit."""
from pathlib import Path
import hashlib
import re
import tempfile
from .thumb import llvm,command,encode_bl

PLACEHOLDER=b'UPID0000'


def build(image,facts,base_revision=255,hard_stop=False,*,maint_version):
 from .profiles import require_profile
 require_profile(maint_version)
 positive_flags=True
 revision=True;is_cutoff=maint_version=='1.6.3';service=is_cutoff;configurable=is_cutoff
 if type(base_revision) is not int or not 0<=base_revision<=255:raise ValueError('invalid base revision')
 if image.sha!=facts['original_app_sha256']:raise ValueError('analysis/input digest mismatch')
 from .hardstop import locate,apply
 found=facts.get('hard_stop') or locate(image,facts)
 base=image
 hard_stop_detail={**found,'requested':'preserve','changed':False}
 if hard_stop:base,hard_stop_detail=apply(image,facts,found)
 f=facts['functions'];r=facts['ram']
 constants={k.upper():v for k,v in {**f,**r}.items()}
 constants.update({k.upper():v for k,v in facts['power_rtc'].items()})
 flags=2|int(hard_stop_detail['enabled'])
 hooks=dict(facts['hooks']);evidence=list(facts['evidence'])
 if is_cutoff:
  from .cutoff import discover_cutoff,source16
  cutoff=discover_cutoff(image,facts)
  constants.update({'CUT_'+k.upper():v for k,v in cutoff.items() if type(v) is int})
  hooks.update(cutoff['hooks']);evidence.extend(cutoff['evidence']);flags|=4
 if positive_flags:flags|=8
 constants.update(UART1=0x50011000,VERSION_ADDRESS=facts['version_address'],BASE_REVISION=base_revision,IMAGE_FLAGS=flags,POSITIVE_FLAGS=int(positive_flags))
 if revision:
  from .marker_uart0 import discover_marker_uart0,source_revision
  marker=discover_marker_uart0(image,facts)
  constants.update({'M0_'+k.upper():v for k,v in marker.items() if type(v) is int})
  constants['MARKER_CUTOFF']=int(is_cutoff);flags|=16
  # One owner of the shared BL: revision wrapper chains to the cutoff wrapper.
  if is_cutoff:hooks.pop('hook_cut_uart0_parser')
  hooks.update(marker['hooks']);evidence.extend(marker['evidence'])
  constants['IMAGE_FLAGS']=flags
 if service:
  from .service import discover_service,source_service
  servicing=discover_service(image,facts)
  constants.update({'SVC_'+k.upper():v for k,v in servicing.items() if type(v) is int})
  hooks.update(servicing['hooks']);evidence.extend(servicing['evidence']);flags|=0x60
  constants['IMAGE_FLAGS']=flags
 if maint_version=='1.5.3':
  from .storage_diagnostics import discover_diagnostics,source_diagnostics
  diagnostic=discover_diagnostics(image,facts)
  constants.update({'CUT_'+k.upper():v for k,v in diagnostic.items() if type(v) is int})
  constants['SVC_SOC_PRIMARY']=diagnostic['soc_primary'];flags|=0x20
  constants['IMAGE_FLAGS']=flags
 if configurable:
  from .configurable_hardstop import discover_configurable,source_configurable
  dynamic=discover_configurable(image,facts)
  constants['HS_DEFAULT']=int(hard_stop_detail['enabled']);flags|=0x80
  constants['IMAGE_FLAGS']=flags
  hooks.update(dynamic['hooks']);evidence.extend(dynamic['evidence'])
 if len(set(hooks.values()))!=len(hooks):raise ValueError('duplicate OEM hook site')
 payload=Path(__file__).with_name('payload.s').read_text()
 if is_cutoff:payload=source16(payload)
 if revision:payload=source_revision(payload,maint_version)
 if service:payload=source_service(payload)
 if maint_version=='1.5.3':payload=source_diagnostics(payload)
 if configurable:payload=source_configurable(payload)
 source='\n'.join(f'.equ {k}, 0x{v:x}' for k,v in sorted(constants.items()))+'\n'+payload
 with tempfile.TemporaryDirectory(prefix='seplos-build-') as d:
  d=Path(d);asm=d/'payload.s';obj=d/'payload.o';raw=d/'payload.bin'
  asm.write_text(source)
  command([llvm('llvm-mc'),'-triple=thumbv6m-none-eabi','-filetype=obj','-o',str(obj),str(asm)])
  rel=command([llvm('llvm-objdump'),'-r',str(obj)])
  if 'R_ARM_' in rel:raise ValueError('unresolved assembly relocation: '+rel)
  command([llvm('llvm-objcopy'),'-O','binary','--only-section=.text',str(obj),str(raw)])
  symbols={m[2]:int(m[1],16) for line in command([llvm('llvm-nm'),'--defined-only',str(obj)]).splitlines() if (m:=re.match(r'([0-9a-fA-F]+)\s+[A-Za-z]\s+(hook_\w+|patch_info_template)$',line))}
  appendix=raw.read_bytes()
  dis=command([llvm('llvm-objdump'),'-d','--triple=thumbv6m-none-eabi','--mcpu=cortex-m0',str(obj)]).replace(str(obj),'payload.o')
 if set(hooks)-symbols.keys():raise ValueError('missing appendix entry point')
 start=len(image.app)
 out=bytearray(base.app+appendix)
 if len(out)>=0x10000 or ((len(out)+259)//256)*256>=0x23000:raise ValueError('patch exceeds flash/update-stream boundary')
 for name,site in hooks.items():
  proof=next(e for e in evidence if e.get('hook')==name)
  if image.app[site:site+4].hex()!=proof['opcode']:raise ValueError('hook bytes changed')
  out[site:site+4]=encode_bl(site,start+symbols[name])
 if is_cutoff:
  off=cutoff['zero_size_offset']
  if int.from_bytes(out[off:off+4],'little')!=cutoff['zero_size_old']:raise ValueError('startup zero extent changed')
  out[off:off+4]=(cutoff['zero_size_old']+4).to_bytes(4,'little')
 offset=start+symbols['patch_info_template']+(10 if revision else 9)
 if out[offset:offset+8]!=PLACEHOLDER or out.count(PLACEHOLDER)!=1:raise ValueError('build ID placeholder mismatch')
 build_id=hashlib.sha256(out).digest()[:8]
 out[offset:offset+8]=build_id
 allowed={a for site in hooks.values() for a in range(site,site+4)}
 if is_cutoff:allowed.update(range(cutoff['zero_size_offset'],cutoff['zero_size_offset']+4))
 if hard_stop_detail.get('changed'):allowed.add(hard_stop_detail['offset'])
 if any(x!=y and a not in allowed for a,(x,y) in enumerate(zip(out,image.app))):raise ValueError('non-hook OEM bytes changed')
 result=image.with_app(out)
 if type(image).parse(result.render())!=result:raise ValueError('output container failed roundtrip')
 report={'hard_stop':hard_stop_detail,'info_format':3,'info_bytes':18,'addressed_info':True,'power_rtc':True,'image_flags':flags,'patch_version':'1.5','append_at':start,'appendix_bytes':len(appendix),'app_sha256':result.sha,'build_id':build_id.hex(),'base_revision':base_revision,'base_revision_source':'unknown' if base_revision==255 else 'explicit caller declaration (not code-proven)','entries':{k:start+v for k,v in symbols.items()},'build_id_offset':offset,'disassembly':dis,'resolved_assembly':source}
 report['positive_flags']=positive_flags
 if revision:report.update(info_format=4,info_bytes=19,uart0_marker=True,hooks=hooks)
 if is_cutoff:
  report.update(patch_version='1.6',cutoff=True,hooks=hooks,ram_bytes=4)
  cutoff['entries']={k:v for k,v in report['entries'].items() if k.startswith('hook_cut_')}
 report['patch_version']=maint_version
 if revision:marker['entries']={k:v for k,v in report['entries'].items() if k.startswith('hook_uart0_marker')}
 if service:
  report.update(service=True,extended_diagnostics=True,checkpoint_before_reset=True)
  servicing['entries']={k:v for k,v in report['entries'].items() if k.startswith('hook_service_')}
 if maint_version=='1.5.3':
  report.update(storage_diagnostics=True,extended_diagnostics=True,checkpoint_before_reset=False,ram_bytes=0)
  if len(hooks)!=5 or hooks!={**facts['hooks'],**marker['hooks']}:raise ValueError('storage diagnostics changed OEM hook set')
 if maint_version=='1.5.3':report['positive_power153']=True
 if configurable:
  report.update(configurable_hard_stop=True,hard_stop_default=bool(constants['HS_DEFAULT']))
  report['hard_stop']={**hard_stop_detail,'enabled':None,'configurable':True,'default_enabled':bool(constants['HS_DEFAULT']),'runtime_from_parameter':True}
  dynamic['entries']={k:v for k,v in report['entries'].items() if k=='hook_configurable_hard_stop'}
  if len(hooks)!=21:raise ValueError('MAINT1.6.3 must have21 guarded OEM hooks')
 return result,report
