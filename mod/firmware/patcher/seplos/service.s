/*1.6.2: read-only diagnostic, native SOC serialization, verified restart.
 * No service RAM; existing IAP buffers, caller stack and native output codecs.
 */
.p2align 2
.thumb_func
.Lsvc_C_diag:
    push {r1, r2, r3, r4, r5, r6, r7, lr}
    movs r0, #0
    ldr r4, =RX
    ldr r1, =RX_META
    ldrb r1, [r1]
    cmp r1, #20
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #13]
    cmp r1, #0x30
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #14]
    cmp r1, #0x34
    bne .Lsvc_C_diag_return
    /* Parser proved checksum/address; enforce exact original service header. */
    ldrb r1, [r4, #1]
    cmp r1, #0x32
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #2]
    cmp r1, #0x30
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #5]
    cmp r1, #0x34
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #6]
    cmp r1, #0x36
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #9]
    cmp r1, #0x45
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #10]
    cmp r1, #0x30
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #11]
    cmp r1, #0x30
    bne .Lsvc_C_diag_return
    ldrb r1, [r4, #12]
    cmp r1, #0x32
    bne .Lsvc_C_diag_return
    ldr r0, =INFO
    bl .Lsvc_diag
    ldr r1, =TX_LENGTH
    movs r0, #0x26
    strh r0, [r1]
    movs r0, #0
    strb r0, [r1, #6]
    movs r0, #1
.Lsvc_C_diag_return:
    pop {r1, r2, r3, r4, r5, r6, r7, pc}
.ltorg

/* Output: ten bytes, stored at the caller's existing stride-two INFO buffer. */
.thumb_func
.Lsvc_diag:
    push {r3, r4, r5, r6, r7, lr}
    sub sp, #16
    mov r7, r0
    mov r6, sp
    movs r0, #1
    strb r0, [r6]
    ldr r0, =CUT_NV_PRIMARY
    bl .Lsvc_read_pair
    ldr r0, =IAP_BUFFER
    movs r1, #171
    bl .Lsvc_class
    strb r0, [r6, #1]
    ldr r1, =IAP_BUFFER
    bl .Lsvc_lock
    strb r0, [r6, #7]
    ldr r0, =CUT_NV_SCRATCH
    movs r1, #171
    bl .Lsvc_class
    strb r0, [r6, #2]
    ldr r1, =CUT_NV_SCRATCH
    bl .Lsvc_lock
    strb r0, [r6, #8]
    ldrb r0, [r6, #1]
    ldrb r1, [r6, #2]
    movs r2, #173
    bl .Lsvc_pair_equal
    strb r0, [r6, #3]
    ldr r0, =SVC_SOC_PRIMARY
    bl .Lsvc_read_pair
    ldr r0, =IAP_BUFFER
    movs r1, #20
    bl .Lsvc_class
    strb r0, [r6, #4]
    ldr r0, =CUT_NV_SCRATCH
    movs r1, #20
    bl .Lsvc_class
    strb r0, [r6, #5]
    ldrb r0, [r6, #4]
    ldrb r1, [r6, #5]
    movs r2, #22
    bl .Lsvc_pair_equal
    strb r0, [r6, #6]
    ldr r0, =CUT_RAM
    movs r2, #0
    ldrb r1, [r0]
    cmp r1, #0
    beq .Lsvc_cache_consistency
    movs r2, #1
.Lsvc_cache_consistency:
    ldrb r1, [r0, #2]
    cmp r1, #1
    bne .Lsvc_cache_magic
    adds r2, #2
.Lsvc_cache_magic:
    ldrb r1, [r0, #1]
    cmp r1, #0xa6
    bne .Lsvc_cache_done
    adds r2, #4
.Lsvc_cache_done:
    strb r2, [r6, #9]
    movs r0, #0
.Lsvc_diag_copy:
    ldrb r1, [r6, r0]
    lsls r2, r0, #1
    strb r1, [r7, r2]
    adds r0, #1
    cmp r0, #10
    blo .Lsvc_diag_copy
    add sp, #16
    pop {r3, r4, r5, r6, r7, pc}
.ltorg

.thumb_func
.Lsvc_read_pair:
    push {r4, lr}
    mov r4, r0
    ldr r1, =IAP_BUFFER
    movs r2, #64
    ldr r3, =CUT_FLASH_READ+1
    blx r3
    movs r0, #1
    lsls r0, #12
    adds r0, r4, r0
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #64
    ldr r3, =CUT_FLASH_READ+1
    blx r3
    pop {r4, pc}
.ltorg

/* Never call OEM IAP reader: it may erase/repair a mirror. */
.thumb_func
.Lsvc_class:
    push {r3, r4, r5, r6, r7, lr}
    mov r4, r0
    mov r5, r1
    movs r1, #0
.Lsvc_erased:
    ldrb r0, [r4, r1]
    cmp r0, #255
    bne .Lsvc_not_erased
    adds r1, #1
    cmp r1, #255
    bls .Lsvc_erased
    movs r0, #0
    b .Lsvc_class_return
.Lsvc_not_erased:
    ldrb r0, [r4]
    cmp r0, #0xa0
    bne .Lsvc_invalid
    ldrb r0, [r4, #1]
    cmp r0, r5
    bne .Lsvc_invalid
    cmp r5, #171
    bne .Lsvc_crc
    ldrb r0, [r4, #2]
    cmp r0, #60
    bne .Lsvc_invalid
    movs r1, #123
    ldrb r0, [r4, r1]
    cmp r0, #27
    bne .Lsvc_invalid
    movs r1, #151
    ldrb r0, [r4, r1]
    cmp r0, #10
    bne .Lsvc_invalid
    movs r1, #162
    ldrb r0, [r4, r1]
    cmp r0, #8
    bne .Lsvc_invalid
.Lsvc_crc:
    mov r0, r4
    mov r1, r5
    ldr r3, =CUT_NV_CRC+1
    blx r3
    ldrb r1, [r4, r5]
    adds r5, #1
    ldrb r2, [r4, r5]
    lsls r2, #8
    orrs r1, r2
    cmp r0, r1
    bne .Lsvc_invalid
    movs r0, #1
    b .Lsvc_class_return
.Lsvc_invalid:
    movs r0, #2
.Lsvc_class_return:
    pop {r3, r4, r5, r6, r7, pc}
.ltorg

.Lsvc_lock:
    cmp r0, #1
    bne .Lsvc_lock_unknown
    movs r0, #163
    ldrb r1, [r1, r0]
    movs r0, #32
    tst r0, r1
    beq .Lsvc_locked
    movs r0, #0
    bx lr
.Lsvc_locked:
    movs r0, #1
    bx lr
.Lsvc_lock_unknown:
    movs r0, #255
    bx lr
.Lsvc_pair_equal:
    cmp r0, #1
    bne .Lsvc_not_comparable
    cmp r1, #1
    bne .Lsvc_not_comparable
    ldr r0, =IAP_BUFFER
    ldr r1, =CUT_NV_SCRATCH
    b .Lsvc_compare
.Lsvc_not_comparable:
    movs r0, #0
    bx lr
.Lsvc_compare:
    movs r3, #0
.Lsvc_compare_loop:
    push {r4, r5}
    ldrb r4, [r0, r3]
    ldrb r5, [r1, r3]
    cmp r4, r5
    pop {r4, r5}
    bne .Lsvc_different
    adds r3, #1
    cmp r3, r2
    blo .Lsvc_compare_loop
    movs r0, #1
    bx lr
.Lsvc_different:
    movs r0, #2
    bx lr
.ltorg

/* Snapshot with native serializer; r4 mask is saved at native frame SP+0. */
.thumb_func
.Lsvc_checkpoint:
    push {r4, r5, r6, lr}
    mrs r4, primask
    ldr r6, =SVC_SAVED_SOC
    ldrh r5, [r6]
    cpsid i
    ldr r3, =CAPACITY_SAVE+1
    blx r3
.Lsvc_save_return:
    msr primask, r4
    bl .Lsvc_verify_soc_pair
    cmp r0, #1
    beq .Lsvc_checkpoint_done
    strh r5, [r6]
    movs r0, #0
.Lsvc_checkpoint_done:
    msr primask, r4
    pop {r4, r5, r6, pc}
.ltorg

/* Only this exact caller gets verified writes; all automatic saves stay OEM. */
.global hook_service_soc_iap
.thumb_func
hook_service_soc_iap:
    adr r3, .Lsvc_iap_anchor
    ldr r2, =.Lsvc_iap_anchor-.Lsvc_save_return
    subs r3, r3, r2
    adds r3, #1
    ldr r2, [sp, #12]
    cmp r2, r3
    beq .Lsvc_checked_iap
    ldr r3, =IAP_WRITE+1
    bx r3
.Lsvc_checked_iap:
    push {r4, r5, r6, lr}
    ldr r2, [sp, #16]
    msr primask, r2
    ldr r4, =IAP_BUFFER
    ldrb r1, [r4, #1]
    cmp r1, #20
    bne .Lsvc_write_fail
    mov r0, r4
    ldr r3, =CUT_NV_CRC+1
    blx r3
    strb r0, [r4, #20]
    lsrs r0, #8
    strb r0, [r4, #21]
    ldr r5, =SVC_SOC_PRIMARY
    bl .Lsvc_write_soc_one
    cmp r0, #1
    bne .Lsvc_write_fail
    ldr r5, =SVC_SOC_BACKUP
    bl .Lsvc_write_soc_one
    pop {r4, r5, r6, pc}
.Lsvc_write_fail:
    movs r0, #0
    pop {r4, r5, r6, pc}
.p2align 2
.Lsvc_iap_anchor:
.ltorg

.Lsvc_write_soc_one:
    push {r4, lr}
    mov r0, r5
    ldr r3, =IAP_ERASE+1
    blx r3
    mov r0, r5
    mov r1, r4
    movs r2, #6
    ldr r3, =IAP_PROGRAM+1
    blx r3
    mov r0, r5
    bl .Lsvc_verify_soc_one
    pop {r4, pc}
.Lsvc_verify_soc_one:
    push {r4, lr}
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #6
    ldr r3, =CUT_FLASH_READ+1
    blx r3
    ldr r0, =IAP_BUFFER
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #22
    bl .Lsvc_compare
    cmp r0, #1
    beq .Lsvc_verify_return
    movs r0, #0
.Lsvc_verify_return:
    pop {r4, pc}
.Lsvc_verify_soc_pair:
    push {r4, lr}
    ldr r0, =SVC_SOC_PRIMARY
    bl .Lsvc_verify_soc_one
    cmp r0, #1
    bne .Lsvc_verify_pair_done
    ldr r0, =SVC_SOC_BACKUP
    bl .Lsvc_verify_soc_one
.Lsvc_verify_pair_done:
    pop {r4, pc}
.ltorg

/* Entry is a nonreturning BL inside the original six-word R power frame.
 * A failed checkpoint must unwind that frame, never enter the next function.
 */
.global hook_service_R_reset
.thumb_func
hook_service_R_reset:
    push {r4, r5, r6, lr}
    ldr r4, =M0_UART0_RX
    ldrb r0, [r4, #3]
    bl .Lext_nibble
    lsls r5, r0, #4
    ldrb r0, [r4, #4]
    bl .Lext_nibble
    orrs r5, r0
    cmp r5, #255
    beq .Lsvc_R_reset_silent
    ldr r0, =ADDRESS
    ldrb r0, [r0]
    cmp r0, #21
    bhi .Lsvc_R_reset_silent
    cmp r0, r5
    bne .Lsvc_R_reset_silent
    bl .Lsvc_checkpoint
    cmp r0, #1
    bne .Lsvc_R_reset_error
    ldr r3, =RESET+1
    blx r3
.Lsvc_R_reset_error:
    ldr r0, =M0_UART0_RTN
    movs r1, #8
    strb r1, [r0]
    b .Lsvc_R_reset_return
.Lsvc_R_reset_silent:
    ldr r0, =M0_UART0_STATE
    movs r1, #0
    strb r1, [r0]
.Lsvc_R_reset_return:
    pop {r4, r5, r6}
    add sp, #4
    pop {r3, r4, r5, r6, r7, pc}
.ltorg
