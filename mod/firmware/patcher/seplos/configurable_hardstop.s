/*1.6.3: replace only MOVS r4,#mask;LDRB r3,[r3], before native TST/BNE.
 * r0/r1/r2 contain live Event8 pointer/set/clear values. Preserve those and
 * all other original registers. No event, GPIO, parameter or persistent write.
 * Final MOVS reproduces N/Z; TST/MOVS leave original C/V unchanged as well.
 */
.p2align 2
.global hook_configurable_hard_stop
.thumb_func
hook_configurable_hard_stop:
    push {r0, r1, r2, lr}
    ldr r0, =GROUP0
    ldrb r0, [r0]
    movs r1, #128
    tst r0, r1
    beq .Lhs_explicit
    /* Bit7=1 includes old FF. Reuse the immutable image's declared default. */
    .if HS_DEFAULT
    movs r4, #0x73
    .else
    movs r4, #0x71
    .endif
    b .Lhs_load_event
.Lhs_explicit:
    movs r1, #64
    tst r0, r1
    beq .Lhs_soft
    movs r4, #0x73
    b .Lhs_load_event
.Lhs_soft:
    movs r4, #0x71
.Lhs_load_event:
    ldrb r3, [r3]
    pop {r0, r1, r2, pc}
.ltorg
