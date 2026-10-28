/* MAINT1.6 only. Existing parameter buffers, CRC, flash and output tails. */
.p2align 2
.global hook_cut_record
.thumb_func
hook_cut_record:
    push {r3, r4, r5, r6, r7, lr}
    bl .Lcut_mirrors
    mov r4, r0
    mov r5, r1
    ldr r6, =CUT_RAM
    movs r0, #1
    cmp r4, r5
    bne .Lrecord_latch
    cmp r4, #1
    bhi .Lrecord_latch
    movs r0, #0
.Lrecord_latch:
    strb r0, [r6]
    movs r0, #0
    cmp r4, r5
    bne .Lrecord_consistent
    cmp r4, #3
    beq .Lrecord_consistent
    movs r0, #1
.Lrecord_consistent:
    strb r0, [r6, #2]
    movs r0, #0xa6
    strb r0, [r6, #1]
    cmp r4, #1
    beq .Lrecord_primary
    cmp r4, #2
    beq .Lrecord_primary
    cmp r5, #1
    beq .Lrecord_backup
    cmp r5, #2
    beq .Lrecord_backup
    movs r0, #0
    pop {r3, r4, r5, r6, r7, pc}
.Lrecord_backup:
    ldr r0, =IAP_BUFFER
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #128
    lsls r2, #1
    bl .Lcopy
.Lrecord_primary:
    ldr r0, =IAP_BUFFER+CUT_NV_GROUP_OFFSET
    ldrb r1, [r0]
    movs r2, #32
    ldrb r3, [r6]
    cmp r3, #0
    beq .Lrecord_unlocked
    bics r1, r2
    b .Lrecord_masked
.Lrecord_unlocked:
    orrs r1, r2
.Lrecord_masked:
    strb r1, [r0]
    movs r0, #1
    pop {r3, r4, r5, r6, r7, pc}
.ltorg

.global hook_cut_nv_write
.thumb_func
hook_cut_nv_write:
    push {r3, r4, r5, r6, r7, lr}
    ldr r4, =IAP_BUFFER
    ldrb r1, [r4, #1]
    cmp r1, #171
    bne .Lnv_write_fail
    mov r0, r4
    ldr r3, =CUT_NV_CRC+1
    blx r3
    movs r1, #171
    strb r0, [r4, r1]
    adds r1, #1
    lsrs r0, #8
    strb r0, [r4, r1]
    ldr r5, =CUT_NV_PRIMARY
    bl .Lnv_one
    cmp r0, #1
    bne .Lnv_write_fail
    ldr r5, =CUT_NV_BACKUP
    bl .Lnv_one
    pop {r3, r4, r5, r6, r7, pc}
.Lnv_write_fail:
    movs r0, #0
    pop {r3, r4, r5, r6, r7, pc}
.Lnv_one:
    push {r4, lr}
    mov r0, r5
    ldr r3, =IAP_ERASE+1
    blx r3
    mov r0, r5
    mov r1, r4
    movs r2, #44
    ldr r3, =IAP_PROGRAM+1
    blx r3
    mov r0, r5
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #44
    ldr r3, =CUT_FLASH_READ+1
    blx r3
    ldr r0, =CUT_NV_SCRATCH
    movs r1, #0
.Lnv_compare:
    ldrb r2, [r0, r1]
    ldrb r3, [r4, r1]
    cmp r2, r3
    bne .Lnv_one_fail
    adds r1, #1
    cmp r1, #176
    blo .Lnv_compare
    movs r0, #1
    pop {r4, pc}
.Lnv_one_fail:
    movs r0, #0
    pop {r4, pc}
.ltorg

.global hook_cut_loader
.thumb_func
hook_cut_loader:
    push {r4, lr}
    ldr r3, =LOADER+1
    blx r3
    bl .Lcut_sync
    bl hook_cut_enforce
    pop {r4, pc}

/* Return primary and backup classification:0 erased,1 unlocked,2 locked,3 bad.
   No implicit repair: preserve evidence of a torn write across repeated boots. */
.thumb_func
.Lcut_mirrors:
    push {r4, lr}
    ldr r0, =CUT_NV_PRIMARY
    ldr r1, =IAP_BUFFER
    movs r2, #64
    ldr r3, =CUT_FLASH_READ+1
    blx r3
    ldr r0, =IAP_BUFFER
    bl .Lcut_record_status
    mov r4, r0
    ldr r0, =CUT_NV_BACKUP
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #64
    ldr r3, =CUT_FLASH_READ+1
    blx r3
    ldr r0, =CUT_NV_SCRATCH
    bl .Lcut_record_status
    mov r1, r0
    mov r0, r4
    pop {r4, pc}
.Lcut_record_status:
    push {r4, r5, r6, lr}
    mov r4, r0
    movs r1, #0
.Lcut_erased_loop:
    ldrb r2, [r4, r1]
    cmp r2, #255
    bne .Lcut_not_erased
    adds r1, #1
    cmp r1, #255
    bls .Lcut_erased_loop
    movs r0, #0
    pop {r4, r5, r6, pc}
.Lcut_not_erased:
    ldrb r0, [r4]
    cmp r0, #0xa0
    bne .Lcut_record_bad
    ldrb r1, [r4, #1]
    cmp r1, #171
    bne .Lcut_record_bad
    mov r0, r4
    ldr r3, =CUT_NV_CRC+1
    blx r3
    movs r1, #171
    ldrb r2, [r4, r1]
    adds r1, #1
    ldrb r1, [r4, r1]
    lsls r1, #8
    orrs r1, r2
    cmp r0, r1
    bne .Lcut_record_bad
    ldrb r0, [r4, #2]
    cmp r0, #0x3c
    bne .Lcut_record_bad
    movs r1, #163
    ldrb r0, [r4, r1]
    movs r1, #32
    tst r0, r1
    beq .Lcut_record_is_locked
    movs r0, #1
    pop {r4, r5, r6, pc}
.Lcut_record_is_locked:
    movs r0, #2
    pop {r4, r5, r6, pc}
.Lcut_record_bad:
    movs r0, #3
    pop {r4, r5, r6, pc}
.ltorg

/* The state bit is owned by the latch cache, not by imported parameter images. */
.Lcut_sync:
    ldr r0, =GROUP0
    ldrb r1, [r0]
    movs r2, #32
    ldr r3, =CUT_RAM
    ldrb r3, [r3]
    cmp r3, #0
    beq .Lcut_sync_unlocked
    bics r1, r2
    b .Lcut_sync_store
.Lcut_sync_unlocked:
    orrs r1, r2
.Lcut_sync_store:
    strb r1, [r0]
    bx lr

.global hook_cut_serializer_0, hook_cut_serializer_1
.thumb_func
hook_cut_serializer_0:
hook_cut_serializer_1:
.Lcut_serializer:
    push {r4, lr}
    bl .Lcut_sync
    bl hook_cut_enforce
    ldr r3, =SERIALIZER+1
    blx r3
    mov r4, r0
    bl .Lcut_consistency
    mov r0, r4
    pop {r4, pc}
.Lcut_consistency:
    push {r4, lr}
    bl .Lcut_mirrors
    ldr r4, =CUT_RAM
    ldrb r2, [r4]
    adds r2, #1
    movs r3, #0
    cmp r0, r2
    bne .Lconsistency_store
    cmp r1, r2
    bne .Lconsistency_store
    movs r3, #1
.Lconsistency_store:
    strb r3, [r4, #2]
    mov r4, r3
    bl .Lcut_sync
    mov r0, r4
    pop {r4, pc}

.global hook_cut_uart0_a1
.thumb_func
hook_cut_uart0_a1:
    push {r4, lr}
    ldr r3, =CUT_UART0_A1+1
    blx r3
    mov r4, r0
    bl .Lcut_sync
    bl hook_cut_enforce
    mov r0, r4
    pop {r4, pc}
.global hook_cut_lcd_a1
.thumb_func
hook_cut_lcd_a1:
    push {r4, lr}
    ldr r3, =LCD_WRITE+1
    blx r3
    mov r4, r0
    bl .Lcut_sync
    bl hook_cut_enforce
    mov r0, r4
    pop {r4, pc}
.ltorg

/* Stage a new persisted state, verify BOTH independent CRC-valid copies. */
.Lcut_save:
    push {r4, r5, r6, lr}
    mov r4, r0
    ldr r0, =GROUP0
    ldrb r1, [r0]
    movs r2, #32
    cmp r4, #0
    beq .Lcut_save_unlock
    bics r1, r2
    b .Lcut_save_stage
.Lcut_save_unlock:
    orrs r1, r2
.Lcut_save_stage:
    strb r1, [r0]
    ldr r3, =SERIALIZER+1
    blx r3
    cmp r0, #1
    bne .Lcut_save_failed
    bl .Lcut_mirrors
    adds r4, #1
    movs r5, #0
    cmp r0, r4
    bne .Lcut_save_result
    cmp r1, r4
    bne .Lcut_save_result
    movs r5, #1
.Lcut_save_result:
    ldr r0, =CUT_RAM
    strb r5, [r0, #2]
    bl .Lcut_sync
    mov r0, r5
    pop {r4, r5, r6, pc}
.Lcut_save_failed:
    movs r5, #0
    b .Lcut_save_result

/* Input r0=10/1F, r1=0 unicast/1 broadcast. Return0 error/1 apply OEM/2 silent. */
.Lcut_action:
    push {r3, r4, r5, r6, r7, lr}
    mov r4, r0
    mov r5, r1
    ldr r6, =CUT_RAM
    ldrb r7, [r6]
    cmp r4, #0x10
    beq .Lcut_action_on
    cmp r5, #0
    bne .Lcut_apply
    cmp r7, #0
    bne .Lcut_action_off
    ldr r0, =GROUP0
    ldrb r0, [r0]
    movs r1, #16
    tst r0, r1
    .if POSITIVE_FLAGS
    beq .Lcut_apply
    .else
    bne .Lcut_apply
    .endif
.Lcut_action_off:
    movs r0, #1
    strb r0, [r6]
    bl .Lcut_sync
    bl hook_cut_enforce
    cmp r7, #0
    beq .Lcut_write_off
    ldrb r0, [r6, #2]
    cmp r0, #1
    beq .Lcut_apply
.Lcut_write_off:
    movs r0, #1
    bl .Lcut_save
    b .Lcut_action_return
.Lcut_action_on:
    cmp r7, #0
    bne .Lcut_on_latched
    cmp r5, #0
    bne .Lcut_apply
    ldrb r0, [r6, #2]
    cmp r0, #1
    beq .Lcut_apply
    b .Lcut_on_write
.Lcut_on_latched:
    cmp r5, #0
    bne .Lcut_ignore
.Lcut_on_write:
    movs r0, #0
    bl .Lcut_save
    cmp r0, #1
    bne .Lcut_on_failed
    movs r0, #0
    strb r0, [r6]
    bl .Lcut_sync
    b .Lcut_apply
.Lcut_on_failed:
    movs r0, #1
    strb r0, [r6]
    bl .Lcut_sync
    bl hook_cut_enforce
    movs r0, #0
    b .Lcut_action_return
.Lcut_ignore:
    movs r0, #2
    b .Lcut_action_return
.Lcut_apply:
    movs r0, #1
.Lcut_action_return:
    pop {r3, r4, r5, r6, r7, pc}
.ltorg

.global hook_cut_uart0_parser
.thumb_func
hook_cut_uart0_parser:
    push {r4, lr}
    ldr r4, =CUT_UART0_RX
    ldrb r0, [r4, #3]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Lcut_uart0_drop
    ldrb r0, [r4, #4]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Lcut_uart0_drop
    ldr r3, =CUT_UART0_PARSER+1
    blx r3
    pop {r4, pc}
.Lcut_uart0_drop:
    ldr r1, =CUT_UART0_STATE
    movs r0, #0
    strb r0, [r1]
    pop {r4, pc}

.global hook_cut_uart0_power
.thumb_func
hook_cut_uart0_power:
    push {r3, r4, r5, r6, r7, lr}
    sub sp, #8
    ldr r4, =CUT_UART0_RX
    /* Only exact original-format power actions participate in the latch. */
    ldrb r0, [r4, #9]
    cmp r0, #0x41
    bne .Lcut_u0_original
    ldrb r0, [r4, #10]
    cmp r0, #0x30
    bne .Lcut_u0_original
    ldrb r0, [r4, #11]
    cmp r0, #0x30
    bne .Lcut_u0_original
    ldrb r0, [r4, #12]
    cmp r0, #0x36
    bne .Lcut_u0_original
    adds r0, r4, #0
    adds r0, #13
    mov r1, sp
    movs r2, #3
    bl .Lext_decode
    cmp r0, #1
    bne .Lcut_u0_original
    mov r6, sp
    ldrb r0, [r6, #1]
    cmp r0, #4
    bne .Lcut_u0_original
    ldrb r0, [r6, #2]
    cmp r0, #0x10
    beq .Lcut_u0_kind
    cmp r0, #0x1f
    bne .Lcut_u0_original
.Lcut_u0_kind:
    mov r7, r0
    ldrb r0, [r4, #3]
    bl .Lext_nibble
    lsls r5, r0, #4
    ldrb r0, [r4, #4]
    bl .Lext_nibble
    orrs r5, r0
    cmp r5, #255
    beq .Lcut_u0_broadcast
    ldr r0, =ADDRESS
    ldrb r0, [r0]
    cmp r5, r0
    bne .Lcut_u0_silent
    movs r1, #0
    b .Lcut_u0_action
.Lcut_u0_broadcast:
    movs r1, #1
.Lcut_u0_action:
    mov r0, r7
    bl .Lcut_action
    cmp r0, #2
    beq .Lcut_u0_silent
    cmp r0, #1
    beq .Lcut_u0_original
    ldr r0, =CUT_UART0_RTN
    movs r1, #8
    strb r1, [r0]
    b .Lcut_u0_return
.Lcut_u0_original:
    ldr r3, =POWER_HANDLER+1
    blx r3
    bl hook_cut_enforce
    b .Lcut_u0_return
.Lcut_u0_silent:
    ldr r0, =CUT_UART0_STATE
    movs r1, #0
    strb r1, [r0]
.Lcut_u0_return:
    add sp, #8
    pop {r3, r4, r5, r6, r7, pc}
.ltorg

.Lcut_active:
    ldr r1, =CUT_RAM
    ldrb r0, [r1, #1]
    cmp r0, #0xa6
    bne .Lcut_yes
    ldrb r0, [r1]
    cmp r0, #0
    bne .Lcut_yes
    ldr r0, =GROUP0
    ldrb r0, [r0]
    movs r1, #16
    tst r0, r1
    .if POSITIVE_FLAGS
    beq .Lcut_no
    .else
    bne .Lcut_no
    .endif
    ldr r0, =SYSTEM_STATUS
    ldrb r0, [r0]
    movs r1, #32
    tst r0, r1
    bne .Lcut_yes
.Lcut_no:
    movs r0, #0
    bx lr
.Lcut_yes:
    movs r0, #1
    bx lr

.global hook_cut_enforce
.thumb_func
hook_cut_enforce:
.Lcut_enforce:
    push {r4, lr}
    bl .Lcut_active
    cmp r0, #0
    beq .Lcut_enforce_done
    ldr r0, =SYSTEM_STATUS
    ldrb r1, [r0]
    movs r2, #32
    orrs r1, r2
    strb r1, [r0]
    bl .Lcut_charge_force
    bl .Lcut_discharge_force
.Lcut_enforce_done:
    pop {r4, pc}

.global hook_cut_charge
.thumb_func
hook_cut_charge:
    push {r4, lr}
    bl .Lcut_active
    cmp r0, #0
    bne .Lcut_charge_locked
    ldr r3, =CUT_CHARGE+1
    blx r3
    pop {r4, pc}
.Lcut_charge_locked:
    bl .Lcut_charge_force
    pop {r4, pc}
.Lcut_charge_force:
    push {r4, r5, r6, r7, lr}
    ldr r0, =CUT_EVENT8
    ldrb r1, [r0]
    movs r2, #64
    orrs r1, r2
    strb r1, [r0]
    ldr r3, =CUT_CHARGE_TAIL+1
    bx r3

.global hook_cut_discharge
.thumb_func
hook_cut_discharge:
    push {r4, lr}
    bl .Lcut_active
    cmp r0, #0
    bne .Lcut_discharge_locked
    ldr r3, =CUT_DISCHARGE+1
    blx r3
    pop {r4, pc}
.Lcut_discharge_locked:
    bl .Lcut_discharge_force
    pop {r4, pc}
.Lcut_discharge_force:
    push {r4, r5, r6, r7, lr}
    ldr r0, =CUT_ONOFF
    ldrb r1, [r0]
    movs r2, #1
    bics r1, r2
    strb r1, [r0]
    ldr r3, =CUT_DISCHARGE_TAIL+1
    bx r3
.ltorg

.global hook_cut_heater
.thumb_func
hook_cut_heater:
    push {r4, lr}
    bl .Lcut_active
    cmp r0, #0
    beq .Lcut_heat_original
    ldr r0, =CUT_ONOFF+19
    movs r1, #0
    strh r1, [r0]
    ldr r0, =GROUP0+3
    ldrb r0, [r0]
    movs r1, #64
    tst r0, r1
    beq .Lcut_heat_original
    bl .Lcut_heat_force
    pop {r4, pc}
.Lcut_heat_original:
    ldr r3, =CUT_HEATER+1
    blx r3
    pop {r4, pc}
.Lcut_heat_force:
    push {r4, r5, r6, lr}
    ldr r0, =CUT_ONOFF
    ldrb r1, [r0]
    movs r2, #8
    bics r1, r2
    strb r1, [r0]
    ldr r3, =CUT_HEATER_TAIL+1
    bx r3

.global hook_cut_power_state
.thumb_func
hook_cut_power_state:
    push {r3, r4, r5, r6, r7, lr}
    bl .Lcut_active
    cmp r0, #0
    beq .Lcut_state_original
    bl hook_cut_enforce
    ldr r0, =SYSTEM_STATUS
    ldrb r1, [r0]
    movs r2, #17
    bics r1, r2
    strb r1, [r0]
    ldr r2, =CUT_STATE_SHADOW
    ldrb r3, [r2]
    strb r1, [r2]
    movs r1, #32
    tst r3, r1
    bne .Lcut_state_hold
    ldr r0, =CONTROL_FLAGS
    ldrb r2, [r0]
    bics r2, r1
    movs r1, #16
    orrs r2, r1
    strb r2, [r0]
    ldr r0, =CUT_STATE_CONTROL
    ldrb r2, [r0]
    orrs r2, r1
    strb r2, [r0]
.Lcut_state_hold:
    ldr r5, =CUT_STATE_TIMER
    movs r6, #0
    ldr r3, =CUT_STATE_ON_TAIL+1
    bx r3
.Lcut_state_original:
    ldr r3, =CUT_POWER_STATE+1
    blx r3
    pop {r3, r4, r5, r6, r7, pc}
.ltorg

/* Clamp only after actual Off+no-charge-path records; never raise OEM limits. */
.global hook_cut_ccl
.thumb_func
hook_cut_ccl:
    push {r3, r4, r5, r6, r7, lr}
    ldr r3, =CUT_CCL+1
    blx r3
    ldr r4, =CUT_PACK_TABLE
    ldr r0, =CUT_POLL_MASK
    ldr r5, [r0]
    movs r6, #0
    movs r7, #1
.Lcut_ccl_loop:
    tst r5, r7
    beq .Lcut_ccl_next
    ldrb r0, [r4, #29]
    movs r1, #32
    tst r0, r1
    beq .Lcut_ccl_next
    ldrb r0, [r4, #26]
    movs r1, #6
    tst r0, r1
    beq .Lcut_ccl_cap
.Lcut_ccl_next:
    adds r4, #30
    lsls r7, #1
    adds r6, #1
    ldr r0, =SLAVES
    ldrb r0, [r0]
    cmp r6, r0
    bls .Lcut_ccl_loop
    b .Lcut_ccl_done
.Lcut_ccl_cap:
    ldr r4, =CUT_AGGREGATE
    ldrb r5, [r4, #3]
    cmp r5, #0
    beq .Lcut_ccl_zero_eligible
    ldr r0, =WORDS+100
    ldrh r0, [r0]
    movs r1, #10
    /* Original division helper is an OEM pure arithmetic function. */
    ldr r3, =CUT_DIVIDE+1
    blx r3
    ldr r1, =GROUP0+7
    ldrb r1, [r1]
    lsrs r1, #7
    beq .Lcut_ccl_half
    cmp r0, #200
    bls .Lcut_ccl_multiply
    subs r0, #100
    b .Lcut_ccl_multiply
.Lcut_ccl_half:
    lsrs r0, #1
.Lcut_ccl_multiply:
    muls r0, r5, r0
    b .Lcut_ccl_compare
.Lcut_ccl_zero_eligible:
    ldrb r0, [r4, #6]
    ldrb r1, [r4, #1]
    cmp r0, r1
    bhs .Lcut_ccl_all_blocked
    movs r0, #100
    b .Lcut_ccl_compare
.Lcut_ccl_all_blocked:
    movs r0, #0
.Lcut_ccl_compare:
    ldrh r1, [r4, #36]
    cmp r1, r0
    bls .Lcut_ccl_done
    strh r0, [r4, #36]
.Lcut_ccl_done:
    pop {r3, r4, r5, r6, r7, pc}
.ltorg
