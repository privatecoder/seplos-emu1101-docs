/* Shared remote reads. Existing hooks, UART INFO and IAP buffers only. */
.p2align 2
.thumb_func
.Lrem_raw_C:
    push {r4, r5, r6, lr}
    ldr r4, =RX
    ldrb r0, [r4, #7]
    cmp r0, #0x34
    bne .Lrem_raw_64
    ldrb r0, [r4, #8]
    cmp r0, #0x42
    beq .Lrem_raw_check
.Lrem_raw_64:
    ldrb r0, [r4, #7]
    cmp r0, #0x36
    bne .Lrem_raw_good
    ldrb r0, [r4, #8]
    cmp r0, #0x34
    bne .Lrem_raw_good
    ldrb r0, [r4, #14]
    cmp r0, #0x35
    beq .Lrem_raw_check
    cmp r0, #0x36
    bne .Lrem_raw_good
.Lrem_raw_check:
    ldr r0, =RX_META
    ldrb r1, [r0]
    mov r0, r4
    bl .Lrem_raw
    pop {r4, r5, r6, pc}
.Lrem_raw_good:
    movs r0, #1
    pop {r4, r5, r6, pc}
.ltorg

/* Strict service header, all raw hex and exact LENGTH character count.
 * OEM parser subsequently proves checksum; no malformed nibbles normalize. */
.thumb_func
.Lrem_raw:
    push {r4, r5, r6, r7, lr}
    sub sp, #4
    mov r4, r0
    mov r6, r1
    cmp r6, #18
    blo .Lrem_raw_bad
    cmp r6, #230
    bhi .Lrem_raw_bad
    ldrb r0, [r4]
    cmp r0, #0x7e
    bne .Lrem_raw_bad
    ldrb r0, [r4, #1]
    cmp r0, #0x32
    bne .Lrem_raw_bad
    ldrb r0, [r4, #2]
    cmp r0, #0x30
    bne .Lrem_raw_bad
    ldrb r0, [r4, #5]
    cmp r0, #0x34
    bne .Lrem_raw_bad
    ldrb r0, [r4, #6]
    cmp r0, #0x36
    bne .Lrem_raw_bad
    subs r6, #1
    ldrb r0, [r4, r6]
    cmp r0, #13
    bne .Lrem_raw_bad
    movs r5, #1
.Lrem_raw_hex:
    ldrb r0, [r4, r5]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Lrem_raw_bad
    adds r5, #1
    cmp r5, r6
    blo .Lrem_raw_hex
    /* Lower 12 bits must equal actual INFO ASCII count. */
    ldrb r0, [r4, #10]
    cmp r0, #0x30
    bne .Lrem_raw_bad
    ldrb r0, [r4, #11]
    bl .Lext_nibble
    lsls r5, r0, #4
    ldrb r0, [r4, #12]
    bl .Lext_nibble
    orrs r0, r5
    mov r7, r6
    subs r7, #17
    cmp r0, r7
    bne .Lrem_raw_bad
    movs r0, #1
    b .Lrem_raw_return
.Lrem_raw_bad:
    movs r0, #0
.Lrem_raw_return:
    add sp, #4
    pop {r4, r5, r6, r7, pc}
.ltorg

/* Existing UART1 parser wrapper calls here before OEM command selection.
 * Return1 for original dispatch; return0 for one reply or silence. */
.thumb_func
.Lrem_C:
    push {r4, r5, r6, r7, lr}
    sub sp, #4
    ldr r0, =COMMAND
    ldrb r7, [r0]
    cmp r7, #0x4b
    beq .Lrem_C_own
    cmp r7, #0x64
    bne .Lrem_C_original
    ldr r4, =RX
    ldrb r0, [r4, #13]
    cmp r0, #0x30
    bne .Lrem_C_original
    ldrb r0, [r4, #14]
    cmp r0, #0x35
    beq .Lrem_C_own
    cmp r0, #0x36
    bne .Lrem_C_original
.Lrem_C_own:
    ldr r0, =ADDRESS
    ldrb r0, [r0]
    cmp r0, #21
    bhi .Lrem_C_silent
    ldr r5, =TX_LENGTH
    ldrb r1, [r5, #10]
    cmp r0, r1
    bne .Lrem_C_silent
    ldr r0, =RX
    ldr r1, =RX_META
    ldrb r1, [r1]
    ldr r2, =INFO
    cmp r7, #0x4b
    beq .Lrem_C_history
    bl .Lrem_service
    b .Lrem_C_reply
.Lrem_C_history:
    bl .Lrem_history
.Lrem_C_reply:
    strh r0, [r5]
    strb r1, [r5, #6]
    movs r0, #0
    b .Lrem_C_return
.Lrem_C_silent:
    ldr r1, =STATE
    movs r0, #0
    strb r0, [r1]
    b .Lrem_C_return
.Lrem_C_original:
    movs r0, #1
.Lrem_C_return:
    add sp, #4
    pop {r4, r5, r6, r7, pc}
.ltorg

/* r0 raw request, r1 frame length, r2 existing stride-two output.
 * Return wire length and RTN; -1 delegates old services unchanged. */
.thumb_func
.Lrem_service:
    push {r4, r5, r6, r7, lr}
    sub sp, #4
    mov r4, r0
    mov r5, r1
    mov r6, r2
    ldrb r0, [r4, #13]
    cmp r0, #0x30
    bne .Lrem_service_original
    ldrb r7, [r4, #14]
    cmp r7, #0x35
    beq .Lrem_service_check
    cmp r7, #0x36
    bne .Lrem_service_original
.Lrem_service_check:
    mov r0, r4
    mov r1, r5
    bl .Lrem_raw
    cmp r0, #1
    bne .Lrem_service_bad
    cmp r7, #0x36
    beq .Lrem_service_soc
    movs r7, #0
    cmp r5, #20
    beq .Lrem_service_cal
    cmp r5, #22
    bne .Lrem_service_bad
    ldrb r0, [r4, #15]
    cmp r0, #0x30
    bne .Lrem_service_bad
    ldrb r0, [r4, #16]
    bl .Lext_nibble
    cmp r0, #2
    bhi .Lrem_service_bad
    mov r7, r0
.Lrem_service_cal:
    mov r0, r6
    cmp r7, #0
    bne .Lrem_service_stored
    bl .Lrem_active
    movs r0, #162
    b .Lrem_service_ok
.Lrem_service_stored:
    mov r1, r7
    bl .Lrem_stored
    movs r0, #134
    b .Lrem_service_ok
.Lrem_service_soc:
    cmp r5, #20
    bne .Lrem_service_bad
    mov r0, r6
    bl .Lrem_soc
    movs r0, #154
.Lrem_service_ok:
    movs r1, #0
    b .Lrem_service_return
.Lrem_service_bad:
    movs r0, #18
    movs r1, #5
    b .Lrem_service_return
.Lrem_service_original:
    movs r0, #0
    mvns r0, r0
.Lrem_service_return:
    add sp, #4
    pop {r4, r5, r6, r7, pc}
.ltorg

/* Native CRC acceptance checks declared length independently of A0/shape. */
.thumb_func
.Lrem_native:
    push {r4, r5, r6, lr}
    mov r4, r0
    ldrb r5, [r4, #1]
    cmp r5, #250
    bhi .Lrem_native_bad
    mov r1, r5
    ldr r3, =CUT_NV_CRC+1
    blx r3
    ldrb r1, [r4, r5]
    adds r5, #1
    ldrb r2, [r4, r5]
    lsls r2, #8
    orrs r1, r2
    cmp r0, r1
    bne .Lrem_native_bad
    movs r0, #1
    pop {r4, r5, r6, pc}
.Lrem_native_bad:
    movs r0, #0
    pop {r4, r5, r6, pc}
.ltorg

.thumb_func
.Lrem_stored:
    push {r4, r5, r6, lr}
    mov r6, r0
    mov r5, r1
    ldr r0, =REM_CAL_PRIMARY
    bl .Lsvc_read_pair
    ldr r4, =IAP_BUFFER
    cmp r5, #1
    beq .Lrem_stored_buffer
    ldr r4, =CUT_NV_SCRATCH
.Lrem_stored_buffer:
    movs r0, #1
    strb r0, [r6]
    strb r5, [r6, #2]
    mov r0, r4
    movs r1, #51
    bl .Lsvc_class
    strb r0, [r6, #4]
    mov r0, r4
    bl .Lrem_native
    strb r0, [r6, #6]
    ldrb r0, [r4, #1]
    strb r0, [r6, #8]
    adds r6, #10
    mov r0, r6
    mov r1, r4
    movs r2, #53
    bl .Lrem_copy
    pop {r4, r5, r6, pc}
.ltorg

/* Raw bytes are retained in native order and copied into stride-two INFO. */
.Lrem_copy:
    cmp r2, #0
    beq .Lrem_copy_return
.Lrem_copy_loop:
    ldrb r3, [r1]
    strb r3, [r0]
    adds r0, #2
    adds r1, #1
    subs r2, #1
    bne .Lrem_copy_loop
.Lrem_copy_return:
    bx lr

/* One bounded RAM snapshot. Descriptors are (address,u16 width,u16 offset).
 * No hardware or flash call occurs under PRIMASK. Restore caller's mask. */
.thumb_func
.Lrem_snapshot:
    push {r4, r5, r6, r7, lr}
    sub sp, #4
    mov r4, r1
    mov r5, r2
    mov r6, r0
    mrs r7, primask
    cpsid i
.Lrem_snapshot_field:
    ldr r0, [r4]
    ldrh r1, [r4, #4]
    ldrh r2, [r4, #6]
    lsls r2, #1
    adds r2, r6, r2
    adds r0, r0, r1
.Lrem_snapshot_byte:
    subs r0, #1
    ldrb r3, [r0]
    strb r3, [r2]
    adds r2, #2
    subs r1, #1
    bne .Lrem_snapshot_byte
    adds r4, #8
    subs r5, #1
    bne .Lrem_snapshot_field
    msr primask, r7
    add sp, #4
    pop {r4, r5, r6, r7, pc}
.ltorg

.thumb_func
.Lrem_active:
    push {r4, lr}
    mov r4, r0
    adr r1, .Lrem_active_table
    movs r2, #30
    bl .Lrem_snapshot
    movs r0, #1
    strb r0, [r4]
    movs r0, #0
    strb r0, [r4, #2]
    ldrb r0, [r4, #4]
    movs r1, #0x1c
    ands r0, r1
    strb r0, [r4, #4]
    pop {r4, pc}
.p2align 2
.Lrem_active_table:
    .word REM_EVENT
    .hword 1,2
    .word REM_CELL_COUNT
    .hword 1,3
    .set rem_i,0
    .rept 16
    .word REM_CELL_GAINS+rem_i*12
    .hword 2,4+rem_i*2
    .set rem_i,rem_i+1
    .endr
    .word REM_VOLTAGE0
    .hword 2,36
    .word REM_VOLTAGE1
    .hword 2,38
    .word REM_CURRENT_A+12
    .hword 2,40
    .word REM_CURRENT_B+12
    .hword 2,42
    .word REM_CURRENT_A+4
    .hword 4,44
    .word REM_CURRENT_B+4
    .hword 4,48
    .word REM_CURRENT_A+14
    .hword 2,52
    .word REM_CURRENT_B+14
    .hword 2,54
    .word REM_CURRENT_A
    .hword 4,56
    .word REM_CURRENT_B
    .hword 4,60
    .word REM_CURRENT_A+8
    .hword 4,64
    .word REM_CURRENT_B+8
    .hword 4,68
.ltorg

.thumb_func
.Lrem_soc:
    push {r4, r5, r6, lr}
    mov r6, r0
    ldr r0, =SVC_SOC_PRIMARY
    bl .Lsvc_read_pair
    movs r0, #1
    strb r0, [r6]
    ldr r0, =IAP_BUFFER
    movs r1, #20
    bl .Lsvc_class
    mov r4, r0
    strb r0, [r6, #2]
    ldr r0, =CUT_NV_SCRATCH
    movs r1, #20
    bl .Lsvc_class
    mov r5, r0
    strb r0, [r6, #4]
    mov r1, r0
    mov r0, r4
    movs r2, #22
    bl .Lsvc_pair_equal
    strb r0, [r6, #6]
    ldr r0, =IAP_BUFFER
    bl .Lrem_native
    mov r4, r0
    ldr r0, =CUT_NV_SCRATCH
    bl .Lrem_native
    movs r1, #0
    cmp r0, #1
    bne .Lrem_soc_primary
    movs r1, #2
.Lrem_soc_primary:
    cmp r4, #1
    bne .Lrem_soc_choice
    movs r1, #1
.Lrem_soc_choice:
    strb r1, [r6, #10]
    lsls r0, #1
    orrs r0, r4
    strb r0, [r6, #8]
    mov r0, r6
    adds r0, #48
    ldr r1, =IAP_BUFFER
    movs r2, #22
    bl .Lrem_copy
    mov r0, r6
    adds r0, #92
    ldr r1, =CUT_NV_SCRATCH
    movs r2, #22
    bl .Lrem_copy
    mov r0, r6
    adr r1, .Lrem_soc_table
    movs r2, #7
    bl .Lrem_snapshot
    pop {r4, r5, r6, pc}
.p2align 2
.Lrem_soc_table:
    .word REM_P58
    .hword 2,6
    .word REM_P59
    .hword 2,8
    .word REM_MEASURE+0x58
    .hword 4,10
    .word REM_MEASURE+0x5c
    .hword 4,14
    .word REM_MEASURE+12
    .hword 2,18
    .word REM_MEASURE+14
    .hword 2,20
    .word REM_MEASURE+16
    .hword 2,22
.ltorg

/* Shared cursor is saved before selection and restored on EEPROM failure. */
.thumb_func
.Lrem_history:
    push {r4, r5, r6, r7, lr}
    sub sp, #4
    mov r4, r0
    mov r5, r1
    mov r6, r2
    cmp r5, #22
    bne .Lrem_history_bad
    ldr r0, =REM_HISTORY_COUNT
    ldrh r0, [r0]
    cmp r0, #0
    beq .Lrem_history_empty
    ldr r1, =500
    cmp r0, r1
    bhi .Lrem_history_failure
    ldr r7, =REM_HISTORY_CURSOR
    ldrh r0, [r7]
    str r0, [sp]
    ldrb r0, [r4, #15]
    bl .Lext_nibble
    lsls r5, r0, #4
    ldrb r0, [r4, #16]
    bl .Lext_nibble
    orrs r5, r0
    adds r0, r6, #2
    mov r1, r5
    ldr r3, =REM_HISTORY_SELECT+1
    blx r3
    ldr r3, =REM_HISTORY_READ+1
    blx r3
    cmp r0, #1
    beq .Lrem_history_record
    ldr r0, [sp]
    strh r0, [r7]
    b .Lrem_history_failure
.Lrem_history_record:
    movs r0, #1
    strb r0, [r6]
    ldr r4, =REM_HISTORY_DATA
    ldrb r0, [r4]
    ldr r1, =2000
    adds r0, r0, r1
    lsrs r1, r0, #8
    strb r1, [r6, #4]
    strb r0, [r6, #6]
    mov r0, r6
    adds r0, #8
    adds r1, r4, #1
    movs r2, #93
    bl .Lrem_copy
    movs r0, #212
    movs r1, #0
    b .Lrem_history_return
.Lrem_history_bad:
    movs r0, #18
    movs r1, #5
    b .Lrem_history_return
.Lrem_history_failure:
    movs r0, #18
    movs r1, #8
    b .Lrem_history_return
.Lrem_history_empty:
    movs r0, #18
    movs r1, #0
.Lrem_history_return:
    add sp, #4
    pop {r4, r5, r6, r7, pc}
.ltorg
