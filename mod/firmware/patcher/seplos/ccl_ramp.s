/* Full 1.6.7: 1..20 A down per online pack/update; up remains native 1 A. */
.p2align 2
.global hook_ccl_decrease
.thumb_func
hook_ccl_decrease:
    push {r0, r1, r4, lr}
    bl .Lccl_effective
    muls r2, r0, r2
    pop {r0, r1, r4}
    pop {r3}
    mov lr, r3
    subs r3, r1, r0
    cmp r3, r2
    bx lr

/* No extra RAM: unused fourth byte of the existing Full cache. */
.Lccl_effective:
    ldr r0, =CCL_RAM
    ldrb r0, [r0]
    cmp r0, #1
    blo .Lccl_default
    cmp r0, #20
    bhi .Lccl_default
    bx lr
.Lccl_default:
    movs r0, #1
    bx lr
.ltorg

/* Decode trailer only; caller separately verifies native record CRC/shape. */
.Lccl_trailer:
    adds r0, #173
    ldrb r1, [r0]
    cmp r1, #0xe7
    bne .Lccl_trailer_bad
    ldrb r1, [r0, #1]
    cmp r1, #1
    blo .Lccl_trailer_bad
    cmp r1, #20
    bhi .Lccl_trailer_bad
    ldrb r0, [r0, #2]
    eors r0, r1
    cmp r0, #255
    bne .Lccl_trailer_bad
    mov r0, r1
    bx lr
.Lccl_trailer_bad:
    movs r0, #0
    bx lr

/* Matching valid mirrored extensions required; fallback never repairs flash. */
.Lccl_load:
    push {r0, r1, r2, r3, r4, lr}
    movs r4, #1
    cmp r0, #1
    blo .Lccl_load_done
    cmp r0, #2
    bhi .Lccl_load_done
    cmp r1, #1
    blo .Lccl_load_done
    cmp r1, #2
    bhi .Lccl_load_done
    ldr r0, =IAP_BUFFER
    bl .Lccl_trailer
    cmp r0, #0
    beq .Lccl_load_done
    mov r4, r0
    ldr r0, =CUT_NV_SCRATCH
    bl .Lccl_trailer
    cmp r0, r4
    beq .Lccl_load_done
    movs r4, #1
.Lccl_load_done:
    ldr r0, =CCL_RAM
    strb r4, [r0]
    pop {r0, r1, r2, r3, r4, pc}
.ltorg

/* Serializer owns all 176 bytes; native payload/checksum remain unchanged. */
.Lccl_store:
    push {r0, r1, r2, lr}
    bl .Lccl_effective
    ldr r1, =IAP_BUFFER+173
    movs r2, #0xe7
    strb r2, [r1]
    strb r0, [r1, #1]
    movs r2, #255
    eors r0, r2
    strb r0, [r1, #2]
    pop {r0, r1, r2, pc}
.ltorg

/* r0 raw frame, r1 length, r2 INFO output, r3 UART1 flag.
 * Negative r0 delegates existing services; otherwise length and RTN. */
.Lccl_service:
    push {r4, r5, r6, r7, lr}
    sub sp, #12
    mov r4, r0
    mov r5, r1
    mov r6, r2
    mov r7, r3
    ldrb r0, [r4, #13]
    cmp r0, #0x30
    bne .Lccl_original
    ldrb r0, [r4, #14]
    cmp r0, #0x37
    beq .Lccl_check
    cmp r0, #0x38
    bne .Lccl_original
.Lccl_check:
    mov r0, r4
    mov r1, r5
    bl .Lrem_raw
    cmp r0, #1
    beq .Lccl_valid
    b .Lccl_bad
.Lccl_valid:
    ldrb r0, [r4, #14]
    cmp r0, #0x38
    beq .Lccl_write
    cmp r5, #20
    beq .Lccl_reply
    b .Lccl_bad
.Lccl_write:
    cmp r5, #22
    bne .Lccl_bad
    cmp r7, #0
    beq .Lccl_permitted
    ldr r0, =GROUP0
    ldrb r0, [r0]
    movs r1, #1
    tst r0, r1
    beq .Lccl_denied
.Lccl_permitted:
    ldrb r0, [r4, #15]
    bl .Lext_nibble
    lsls r7, r0, #4
    ldrb r0, [r4, #16]
    bl .Lext_nibble
    orrs r7, r0
    cmp r7, #1
    blo .Lccl_bad
    cmp r7, #20
    bhi .Lccl_bad
    bl .Lccl_effective
    str r0, [sp]
    ldr r4, =CCL_RAM
    strb r7, [r4]
    bl .Lcut_serializer
    cmp r0, #1
    beq .Lccl_reply
    ldr r0, [sp]
    strb r0, [r4]
    movs r1, #8
    b .Lccl_error
.Lccl_reply:
    bl .Lccl_effective
    strb r0, [r6, #2]
    movs r0, #1
    strb r0, [r6]
    strb r0, [r6, #4]
    strb r0, [r6, #6]
    movs r0, #20
    strb r0, [r6, #8]
    movs r0, #28
    movs r1, #0
    b .Lccl_return
.Lccl_denied:
    movs r1, #4
    b .Lccl_error
.Lccl_bad:
    movs r1, #5
.Lccl_error:
    movs r0, #18
    b .Lccl_return
.Lccl_original:
    movs r0, #0
    mvns r0, r0
.Lccl_return:
    add sp, #12
    pop {r4, r5, r6, r7, pc}
.ltorg
