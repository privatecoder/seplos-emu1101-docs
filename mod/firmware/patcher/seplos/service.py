"""Full-profile service role proof and source composition; no image address table."""
from pathlib import Path
from .analysis import unique
from .thumb import Code


def discover_service(image,facts):
    c=Code(image.app);f=facts['functions'];r=facts['ram'];p=facts['power_rtc'];d=facts['cutoff']
    save=f['capacity_save'];body=c.body(save)
    if c.ins[save].token()!=['push','{r4, r5, r6, lr}']:
        raise ValueError('unsupported SOC serializer frame')
    call=unique([i for i in body if i.op=='bl' and i.target==f['iap_write']],'SOC IAP call')
    if [i.op for i in body if i.op in ('bl','blx')]!=['bl']:
        raise ValueError('SOC serializer has additional calls')
    if any('sp' in i.args for i in body if i.at!=save):
        raise ValueError('SOC serializer changes SP before contextual hook')
    if c.ins[call.at-2].token()!=['movs','r0, #0x6']:
        raise ValueError('SOC serializer block is not six')
    tail=c.window(call.at+4,3)
    if [i.token() for i in tail]!=[['ldrh','r0, [r4, #0x10]'],['strh','r0, [r5, #0x14]'],['pop','{r4, r5, r6, pc}']]:
        raise ValueError('unsupported SOC serializer checkpoint tail')
    measure=c.ins[save+2].literal
    if measure!=r['learned']-14 or c.ins[save+4].literal!=r['iap_buffer']:
        raise ValueError('SOC serializer RAM binding')
    load=tail[-1].at+2
    prefix=c.window(load,4)
    if [i.token() for i in prefix[:2]]!=[['push','{r3, r4, r5, r6, r7, lr}'],['movs','r0, #0x6']] or prefix[2].op!='bl' or prefix[2].target!=f['iap_read'] or prefix[3].literal!=measure:
        raise ValueError('SOC boot loader does not follow serializer')
    if c.ins[p['power_handler']].token()!=['push','{r3, r4, r5, r6, r7, lr}']:
        raise ValueError('unsupported R power handler frame')
    reset=unique([i for i in c.body(p['power_handler']) if i.op=='bl' and i.target==p['reset']],'R reset call')
    roles=dict(saved_soc=measure+0x54,soc_primary=d['nv_primary']+6*4096,
        soc_backup=d['nv_backup']+6*4096,soc_save=save,soc_write_site=call.at,
        r_reset_site=reset.at,soc_load=load,soc_len=20,soc_bytes=22,soc_words=6)
    roles['hooks']={'hook_service_soc_iap':call.at,'hook_service_R_reset':reset.at}
    roles['evidence']=[dict(hook=k,site=v,original_target=c.ins[v].target,
        opcode=image.app[v:v+4].hex()) for k,v in roles['hooks'].items()]
    facts['service']=roles
    return roles


def source_service(source):
    replacements={
        'address_ok:\n    cmp r2, #0':
        'address_ok:\n    bl .Lsvc_C_diag\n    cmp r0, #1\n    bne .Lsvc_C_continue\n    b handled\n.Lsvc_C_continue:\n    cmp r2, #0',
        '    /* Original watchdog reset does not return and cannot send an ACK. */':
        '    bl .Lsvc_checkpoint\n    cmp r0, #1\n    beq .Lsvc_C_reset_ready\n    b .Lext_rtc_error\n.Lsvc_C_reset_ready:\n    /* Original watchdog reset does not return and cannot send an ACK. */',
        '    cmp r0, #0x33\n    m0_bne .Lm0_bad':
        '    cmp r0, #0x34\n    m0_beq .Lsvc_R_diag\n    cmp r0, #0x33\n    m0_bne .Lm0_bad',
        '.Lm0_clear:\n':
        '.Lsvc_R_diag:\n    ldr r0, =M0_UART0_INFO\n    bl .Lsvc_diag\n    movs r0, #0x26\n    b .Lm0_success\n.Lm0_clear:\n',
    }
    for old,new in replacements.items():
        if source.count(old)!=1:raise ValueError('unknown service source contract: '+old)
        source=source.replace(old,new)
    return source+'\n'+Path(__file__).with_name('service.s').read_text()
