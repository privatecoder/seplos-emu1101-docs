/* Short saved-mask cleanup. No new RAM, hardware calls or literal pool. */
.balign 2
.thumb_func
hook_scheduler_atomic:
    push {r2, lr}
    mrs r2, PRIMASK
    cpsid i
    ldrb r0, [r5]
    orrs r0, r6
    movs r1, #0xfb
    ands r0, r1
    strb r0, [r5]
    msr PRIMASK, r2
    pop {r2, pc}
