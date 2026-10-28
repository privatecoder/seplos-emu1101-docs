/* Standalone parameterized MAINT1.5. Provenance: ../PROVENANCE.md */
.syntax unified
.cpu cortex-m0
.thumb
.section .text,"ax",%progbits
.global hook_rx
.thumb_func
hook_rx:
    push {r3, r4, r5, r6, r7, lr}
    ldr r4, =UART1
    ldr r5, =STATE
    ldr r6, =RX_META
    ldr r0, [r4, #8]
    lsls r0, r0, #15
    bpl .Lrx_return
    movs r7, #0
.Lrx_loop:
    ldr r0, [r4, #12]
    uxtb r0, r0
    cmp r0, #1
    bls .Lrx_last
    ldr r0, [r4]
    uxtb r0, r0
    bl .Lrx_byte
    adds r7, #1
    cmp r7, #8
    blo .Lrx_loop
    b .Lrx_return
.Lrx_last:
    cmp r0, #1
    bne .Lrx_return
    ldr r0, [r4, #8]
    lsls r0, r0, #10
    bpl .Lrx_return
    ldr r0, [r4]
    uxtb r0, r0
    bl .Lrx_byte
    ldrb r0, [r5]
    cmp r0, #5
    beq .Lrx_reset
    cmp r0, #1
    bne .Lrx_return
    ldrb r1, [r6, #1]
    ldr r2, =RX
    ldrb r0, [r2]
    cmp r0, #0x55
    beq .Lrx_binary
    cmp r0, #0x01
    beq .Lrx_modbus
    cmp r1, #18
    blo .Lrx_reset
    b .Lrx_ready
.Lrx_binary:
    cmp r1, #7
    blo .Lrx_reset
    b .Lrx_ready
.Lrx_modbus:
    cmp r1, #8
    bne .Lrx_reset
.Lrx_ready:
    strb r1, [r6]
    movs r0, #4
    strb r0, [r5]
.Lrx_return:
    pop {r3, r4, r5, r6, r7, pc}
.Lrx_reset:
    movs r0, #0
    strb r0, [r5]
    strb r0, [r6, #1]
    b .Lrx_return
.Lrx_byte:
    ldrb r1, [r5]
    cmp r1, #1
    beq .Lrx_append
    cmp r1, #0
    bne .Lbyte_return
    cmp r0, #0x55
    beq .Lrx_start
    cmp r0, #0x7e
    beq .Lrx_start
    cmp r0, #1
    bne .Lbyte_return
.Lrx_start:
    ldr r2, =RX
    strb r0, [r2]
    movs r1, #1
    strb r1, [r6, #1]
    strb r1, [r5]
    bx lr
.Lrx_append:
    ldrb r1, [r6, #1]
    cmp r1, #RX_LIMIT
    bhs .Lrx_overflow
    ldr r2, =RX
    strb r0, [r2, r1]
    adds r1, #1
    strb r1, [r6, #1]
.Lbyte_return:
    bx lr
.Lrx_overflow:
    movs r1, #5
    strb r1, [r5]
    bx lr
.ltorg
.p2align 2
.global hook_dispatch
.thumb_func
hook_dispatch:
    push {r3, r4, r5, r6, r7, lr}
    ldr r4, =RX
    ldr r5, =STATE
    ldrb r0, [r4]
    cmp r0, #0x55
    beq .Lbinary
    ldr r3, =DISPATCH+1
    blx r3
    pop {r3, r4, r5, r6, r7, pc}
.Lbinary:
    ldrb r0, [r5]
    cmp r0, #4
    bne .Ldispatch_return
    movs r0, #3
    strb r0, [r5]
    ldrb r0, [r4, #1]
    cmp r0, #21
    bhi .Lsilent
    ldr r1, =ADDRESS
    ldrb r6, [r1]
    cmp r0, r6
    bne .Lsilent
    ldr r1, =RX_META
    ldrb r7, [r1]
    cmp r7, #7
    blo .Lsilent
    ldrb r0, [r4, #3]
    adds r0, #7
    cmp r0, r7
    bne .Lsilent
    subs r0, r7, #1
    ldrb r0, [r4, r0]
    cmp r0, #0xaa
    bne .Lsilent
    adds r0, r4, #1
    subs r1, r7, #4
    ldr r3, =CRC+1
    blx r3
    subs r1, r7, #3
    ldrb r2, [r4, r1]
    lsls r2, #8
    adds r1, #1
    ldrb r1, [r4, r1]
    orrs r2, r1
    cmp r0, r2
    bne .Lsilent
    ldrb r0, [r4, #2]
    cmp r0, #0x47
    beq .Lread
    cmp r0, #0xa1
    beq .Lwrite
    cmp r0, #0xa2
    beq .Lserial1
    cmp r0, #0xa4
    beq .Lserial2
    movs r0, #0x81
    b .Lerror
.Lserial1:
    ldr r1, =STRING1
    b .Lserial
.Lserial2:
    ldr r1, =STRING2
.Lserial:
    ldrb r0, [r4, #3]
    cmp r0, #0
    bne .Lbad_length
    ldr r0, =TX+4
    movs r2, #30
    bl .Lcopy
    ldrb r0, [r4, #2]
    movs r1, #30
    b .Lreply
.Lsilent:
    movs r0, #0
    strb r0, [r5]
.Ldispatch_return:
    pop {r3, r4, r5, r6, r7, pc}
.Lbad_length:
    movs r0, #0x87
.Lerror:
    movs r1, #0
    b .Lreply
.Lread:
    ldrb r0, [r4, #3]
    cmp r0, #0
    bne .Lbad_length
    ldr r0, =TX
    adds r0, #4
    movs r1, #0x3c
    strb r1, [r0]
    adds r0, #1
    ldr r1, =WORDS
    movs r2, #60
.Lread_words:
    ldrh r3, [r1]
    lsrs r7, r3, #8
    strb r7, [r0]
    strb r3, [r0, #1]
    adds r0, #2
    adds r1, #2
    subs r2, #1
    bne .Lread_words
    movs r1, #0x1b
    strb r1, [r0]
    adds r0, #1
    ldr r1, =SMALL
    movs r2, #27
    bl .Lcopy
    movs r1, #8
    strb r1, [r0]
    adds r0, #1
    ldr r1, =GROUP0
    movs r2, #8
    bl .Lcopy
    ldr r1, =NAME
    movs r2, #10
    bl .Lcopy
    movs r0, #0x47
    movs r1, #168
    b .Lreply
.ltorg
.p2align 2
.Lwrite:
    ldr r0, =GROUP0
    ldrb r0, [r0]
    lsls r1, r0, #31
    bmi .La1_enabled
.La1_denied:
    movs r0, #0xe3
    b .Lerror
.La1_enabled:
    ldrb r1, [r4, #3]
    cmp r1, #158
    bne .La1_original
    movs r1, #154
    ldrb r1, [r4, r1]
    eors r1, r0
    movs r2, #12
    tst r1, r2
    bne .La1_denied
.La1_original:
    ldrb r0, [r4, #3]
    cmp r0, #158
    beq .Lwrite_length_ok
    b .Lbad_length
.Lwrite_length_ok:
    ldrb r0, [r4, #4]
    cmp r0, #0x3c
    bne .Lbad_markers
    movs r1, #125
    ldrb r0, [r4, r1]
    cmp r0, #0x1b
    bne .Lbad_markers
    movs r1, #153
    ldrb r0, [r4, r1]
    cmp r0, #8
    beq .Ldecode
.Lbad_markers:
    movs r0, #0x83
    b .Lerror
.Ldecode:
    adds r0, r4, #5
    ldr r1, =SHADOW_WORDS
    movs r2, #60
.Lwrite_words:
    ldrb r3, [r0]
    lsls r3, #8
    ldrb r7, [r0, #1]
    orrs r3, r7
    strh r3, [r1]
    adds r0, #2
    adds r1, #2
    subs r2, #1
    bne .Lwrite_words
    mov r1, r0
    adds r1, #1
    ldr r0, =SHADOW_SMALL
    movs r2, #27
    bl .Lcopy
    ldr r3, =VALIDATOR+1
    blx r3
    cmp r0, #0
    bne .Lcommit_switches
    movs r0, #0xe2
    b .Lerror
.Lcommit_switches:
    mov r1, r4
    adds r1, #154
    ldr r0, =GROUP0
    movs r2, #8
    bl .Lcopy
    ldr r3, =SERIALIZER+1
    blx r3
    ldr r0, =WORDS+116
    ldrh r1, [r0]
    ldr r2, =LEARNED
    ldrh r0, [r2]
    subs r0, r0, r1
    bpl .Labs_capacity
    rsbs r0, r0, #0
.Labs_capacity:
    ldr r3, =1000
    cmp r0, r3
    blo .Lwrite_ok
    strh r1, [r2]
    ldr r2, =3600
    muls r1, r2, r1
    ldr r0, =COULOMB_MAX
    str r1, [r0]
    ldr r3, =CAPACITY_SAVE+1
    blx r3
.Lwrite_ok:
    movs r0, #0xa1
    movs r1, #0
    b .Lreply
.ltorg
.p2align 2
.Lreply:
    ldr r7, =TX
    movs r2, #0x55
    strb r2, [r7]
    strb r6, [r7, #1]
    strb r0, [r7, #2]
    strb r1, [r7, #3]
    adds r4, r1, #4
    adds r1, #3
    adds r0, r7, #1
    ldr r3, =CRC+1
    blx r3
    lsrs r2, r0, #8
    strb r2, [r7, r4]
    adds r4, #1
    strb r0, [r7, r4]
    adds r4, #1
    movs r0, #0xaa
    strb r0, [r7, r4]
    adds r4, #1
    ldr r1, =TX_LENGTH
    strh r4, [r1]
    ldr r3, =UART1_SEND+1
    blx r3
    pop {r3, r4, r5, r6, r7, pc}
.Lcopy:
    cmp r2, #0
    beq .Lcopy_done
.Lcopy_loop:
    ldrb r3, [r1]
    strb r3, [r0]
    adds r0, #1
    adds r1, #1
    subs r2, #1
    bne .Lcopy_loop
.Lcopy_done:
    bx lr
.ltorg

.macro fail_if_ne
    beq .Lvalid\@
    b error
.Lvalid\@:
.endm
.global hook_uart1
.thumb_func
hook_uart1:
    push {r4, r5, r6, lr}
    /* OEM parser normalizes ADR before checksum: validate its raw hex first. */
    bl .Lraw_address_guard
    cmp r0, #1
    beq .Lraw_address_ok
    b silent
.Lraw_address_ok:
    ldr r3, =PARSER+1
    blx r3
    cmp r0, #1
    beq parsed
    pop {r4, r5, r6, pc}
parsed:
    ldr r4, =COMMAND
    ldrb r1, [r4]
    cmp r1, #0x45
    beq .Lextended_call
    cmp r1, #0x4d
    beq .Lextended_call
    cmp r1, #0x4e
    beq .Lextended_call
    cmp r1, #0x64
    beq maintenance_request
    pop {r4, r5, r6, pc}
.Lextended_call:
    bl .Lextended
    pop {r4, r5, r6, pc}
maintenance_request:
    ldr r5, =TX_LENGTH
    ldr r6, =RX
    ldr r2, =ADDRESS
    ldrb r2, [r2]
    cmp r2, #21
    bls .Linfo_local_valid
    b silent
.Linfo_local_valid:
    ldrb r1, [r5, #10]
    cmp r1, r2
    beq address_ok
    b silent
address_ok:
    cmp r2, #0
    beq .Lmaintenance_common
    /* Nonzero packs only accept exact INFO03; state/actions stay master-only. */
    ldr r0, =RX_META
    ldrb r1, [r0]
    cmp r1, #20
    bne .Lslave_maintenance_silent
    ldrb r1, [r6, #13]
    cmp r1, #0x30
    bne .Lslave_maintenance_silent
    ldrb r1, [r6, #14]
    cmp r1, #0x33
    beq .Lmaintenance_common
.Lslave_maintenance_silent:
    b silent
.Lmaintenance_common:
    ldrb r1, [r6, #1]
    cmp r1, #0x32
    fail_if_ne
    ldrb r1, [r6, #2]
    cmp r1, #0x30
    fail_if_ne
    ldrb r1, [r6, #5]
    cmp r1, #0x34
    fail_if_ne
    ldrb r1, [r6, #6]
    cmp r1, #0x36
    fail_if_ne
    ldr r4, =RX_META
    ldrb r1, [r4]
    cmp r1, #20
    beq status_request
    cmp r1, #24
    beq action_request
    b error
status_request:
    ldrb r1, [r6, #9]
    cmp r1, #0x45
    fail_if_ne
    ldrb r1, [r6, #12]
    cmp r1, #0x32
    fail_if_ne
    ldrb r1, [r6, #10]
    cmp r1, #0x30
    fail_if_ne
    ldrb r1, [r6, #11]
    cmp r1, #0x30
    fail_if_ne
    ldrb r1, [r6, #13]
    cmp r1, #0x30
    fail_if_ne
    ldrb r1, [r6, #14]
    cmp r1, #0x32
    beq reply
    cmp r1, #0x33
    beq info_reply
    b error
info_reply:
    ldr r1, =INFO
    adr r2, .Lpatch_info_template
    movs r3, #0
info_copy:
    ldrb r0, [r2, r3]
    lsls r4, r3, #1
    strb r0, [r1, r4]
    adds r3, r3, #1
    cmp r3, #18
    blo info_copy
    ldr r2, =VERSION_ADDRESS
    ldrb r0, [r2]
    strb r0, [r1, #8]
    ldrb r0, [r2, #1]
    strb r0, [r1, #10]
    movs r0, #0x36
    strh r0, [r5]
    movs r0, #0
    strb r0, [r5, #6]
    b handled
action_request:
    ldrb r1, [r6, #9]
    cmp r1, #0x41
    fail_if_ne
    ldrb r1, [r6, #10]
    cmp r1, #0x30
    fail_if_ne
    ldrb r1, [r6, #11]
    cmp r1, #0x30
    fail_if_ne
    ldrb r1, [r6, #12]
    cmp r1, #0x36
    fail_if_ne
    ldrb r1, [r6, #13]
    cmp r1, #0x30
    fail_if_ne
    ldrb r2, [r6, #14]
    cmp r2, #0x30
    beq token
    cmp r2, #0x31
    fail_if_ne
token:
    ldrb r1, [r6, #15]
    cmp r1, #0x43
    fail_if_ne
    ldrb r1, [r6, #16]
    cmp r1, #0x33
    fail_if_ne
    ldrb r1, [r6, #17]
    cmp r1, #0x35
    fail_if_ne
    ldrb r1, [r6, #18]
    cmp r1, #0x41
    fail_if_ne
    cmp r2, #0x30
    beq turn_off
turn_on:
    ldr r0, =GROUP0
    ldrb r0, [r0]
    lsls r1, r0, #29
    bmi .Lstart_allowed
    b error
.Lstart_allowed:
    ldr r0, =GROUP0+7
    ldrb r0, [r0]
    movs r1, #0x20
    tst r0, r1
    fail_if_ne
    ldr r4, =0x00023000
    ldr r0, [r4]
    movs r1, #0
    mvns r1, r1
    cmp r0, r1
    beq program_marker
    cmp r0, #0
    beq reply
    b error
program_marker:
    sub sp, #8
    movs r0, #0
    str r0, [sp]
    mov r0, r4
    mov r1, sp
    movs r2, #1
    ldr r3, =IAP_PROGRAM+1
    blx r3
    add sp, #8
    ldr r0, [r4]
    cmp r0, #0
    fail_if_ne
    b reply
turn_off:
    ldr r4, =0x00023000
    ldr r0, [r4]
    movs r1, #0
    mvns r1, r1
    cmp r0, r1
    beq reply
    cmp r0, #0
    fail_if_ne
    mov r0, r4
    ldr r3, =IAP_ERASE+1
    blx r3
    ldr r0, [r4]
    movs r1, #0
    mvns r1, r1
    cmp r0, r1
    fail_if_ne
reply:
    ldr r0, =0x00023000
    ldr r0, [r0]
    ldr r1, =INFO
    strb r0, [r1]
    lsrs r0, r0, #8
    strb r0, [r1, #2]
    lsrs r0, r0, #8
    strb r0, [r1, #4]
    lsrs r0, r0, #8
    strb r0, [r1, #6]
    ldr r2, =SLAVES
    ldrb r2, [r2]
    strb r2, [r1, #8]
    movs r0, #0x1C
    strh r0, [r5]
    movs r0, #0
    strb r0, [r5, #6]
    b handled
error:
    movs r0, #0x12
    strh r0, [r5]
    movs r0, #5
    strb r0, [r5, #6]
handled:
    movs r0, #0
    pop {r4, r5, r6, pc}
silent:
    ldr r1, =STATE
    movs r2, #0
    strb r2, [r1]
    movs r0, #0
    pop {r4, r5, r6, pc}
.p2align 2
.ltorg
.p2align 2
.global patch_info_template
patch_info_template:
.Lpatch_info_template:
    .ascii "MNT"
    .byte 3, 0, 0, BASE_REVISION, 1, 5
    .ascii "UPID0000"
    .byte IMAGE_FLAGS
.p2align 2

.global hook_dip
.thumb_func
hook_dip:
    push {r4, lr}
    ldr r3, =DIP+1
    blx r3
    ldr r0, =0x00023000
    ldr r0, [r0]
    movs r1, #0
    mvns r1, r1
    cmp r0, r1
    beq dip_done
    ldr r0, =ADDRESS
    ldrb r0, [r0]
    cmp r0, #0
    bne dip_done
    ldr r0, =GROUP0+7
    ldrb r0, [r0]
    movs r1, #0x20
    tst r0, r1
    bne dip_done
    ldr r0, =SLAVES
    movs r1, #0
    strb r1, [r0]
dip_done:
    pop {r4, pc}
.p2align 2
.ltorg

/* Power/RTC use the original action branch/drivers; UART0 buffers stay intact. */
.macro ext_ne
    beq .Lext_valid\@
    b .Lext_error
.Lext_valid\@:
.endm
.p2align 2
.thumb_func
.Lextended:
    push {r3, r4, r5, r6, r7, lr}
    sub sp, #8
    mov r7, r1
    ldr r4, =RX
    ldr r5, =TX_LENGTH
    ldr r0, =ADDRESS
    ldrb r0, [r0]
    cmp r0, #21
    bls .Lext_address_valid
    b .Lext_silent
.Lext_address_valid:
    ldrb r1, [r5, #10]
    cmp r0, r1
    beq .Lext_address_match
    b .Lext_silent
.Lext_address_match:
    ldrb r0, [r4, #1]
    cmp r0, #0x32
    ext_ne
    ldrb r0, [r4, #2]
    cmp r0, #0x30
    ext_ne
    ldrb r0, [r4, #5]
    cmp r0, #0x34
    ext_ne
    ldrb r0, [r4, #6]
    cmp r0, #0x36
    ext_ne
    cmp r7, #0x4d
    beq .Lext_get_header
    ldr r0, =GROUP0
    ldrb r0, [r0]
    movs r1, #8
    tst r0, r1
    .if POSITIVE_FLAGS
    bne .Lext_allowed
    .else
    beq .Lext_allowed
    .endif
    b .Lext_error
.Lext_allowed:
    cmp r7, #0x45
    bne .Lext_set_header
    movs r2, #3
    adr r1, .Lext_len3
    b .Lext_check_header
.Lext_get_header:
    movs r2, #0
    adr r1, .Lext_len0
    b .Lext_check_header
.Lext_set_header:
    movs r2, #7
    adr r1, .Lext_len7
.Lext_check_header:
    ldr r0, =RX_META
    ldrb r0, [r0]
    lsls r3, r2, #1
    adds r3, #18
    cmp r0, r3
    ext_ne
    movs r0, #0
.Lext_header_loop:
    adds r3, r4, r0
    ldrb r3, [r3, #9]
    ldrb r6, [r1, r0]
    cmp r3, r6
    ext_ne
    adds r0, #1
    cmp r0, #4
    blo .Lext_header_loop
    mov r1, sp
    adds r0, r4, #0
    adds r0, #13
    bl .Lext_decode
    cmp r0, #1
    ext_ne
    cmp r7, #0x4d
    beq .Lext_get
    cmp r7, #0x4e
    beq .Lext_set
    mov r6, sp
    ldrb r0, [r6]
    cmp r0, #0
    ext_ne
    ldrb r0, [r6, #1]
    cmp r0, #6
    beq .Lext_reset
    cmp r0, #4
    ext_ne
    ldrb r1, [r6, #2]
    cmp r1, #0x10
    beq .Lext_switch
    cmp r1, #0x1f
    ext_ne
.Lext_switch:
    bl .Lext_power
    b .Lext_success
.Lext_reset:
    ldrb r0, [r6, #2]
    cmp r0, #0
    ext_ne
    /* Original watchdog reset does not return and cannot send an ACK. */
    ldr r3, =RESET+1
    blx r3
    b .Lext_error
.Lext_get:
    ldr r3, =RTC_READ+1
    blx r3
    cmp r0, #0
    bne .Lext_get_ok
    b .Lext_rtc_error
.Lext_get_ok:
    ldr r6, =RTC+4
    ldrb r0, [r6]
    ldr r1, =2000
    adds r0, r0, r1
    ldr r2, =INFO
    lsrs r1, r0, #8
    strb r1, [r2]
    strb r0, [r2, #2]
    movs r0, #1
.Lext_get_copy:
    ldrb r1, [r6, r0]
    lsls r3, r0, #1
    adds r3, r3, r2
    strb r1, [r3, #2]
    adds r0, #1
    cmp r0, #6
    blo .Lext_get_copy
    movs r0, #0x20
    strh r0, [r5]
    movs r0, #0
    strb r0, [r5, #6]
    b .Lext_done
.Lext_set:
    mov r0, sp
    bl .Lext_calendar
    cmp r0, #1
    ext_ne
    mov r6, sp
    ldrb r0, [r6]
    lsls r0, #8
    ldrb r1, [r6, #1]
    orrs r0, r1
    ldr r1, =2000
    subs r0, r0, r1
    ldr r1, =RTC+4
    strb r0, [r1]
    adds r0, r1, #1
    adds r1, r6, #2
    movs r2, #5
    bl .Lcopy
    ldr r3, =RTC_WRITE+1
    blx r3
    cmp r0, #0
    beq .Lext_rtc_error
.Lext_success:
    movs r0, #0x12
    strh r0, [r5]
    movs r0, #0
    strb r0, [r5, #6]
    b .Lext_done
.Lext_rtc_error:
    movs r0, #8
    b .Lext_fail
.Lext_error:
    movs r0, #5
.Lext_fail:
    strb r0, [r5, #6]
    movs r0, #0x12
    strh r0, [r5]
    b .Lext_done
.Lext_silent:
    ldr r1, =STATE
    movs r0, #0
    strb r0, [r1]
.Lext_done:
    movs r0, #0
    add sp, #8
    pop {r3, r4, r5, r6, r7, pc}
.p2align 2
.Lext_len0: .ascii "0000"
.Lext_len3: .ascii "A006"
.Lext_len7: .ascii "200E"
.ltorg

/* Preserve the original action's pop ABI. RX[0]='~' excludes its FF special case. */
.thumb_func
.Lext_power:
    push {r3, r4, r5, r6, r7, lr}
    ldr r0, =RX-31
    movs r3, #0
    ldr r2, =POWER_ACTION+1
    bx r2
.ltorg

/* Strict uppercase hex decode into the caller's eight-byte stack scratch. */
.thumb_func
.Lext_decode:
    push {r3, r4, r5, r6, r7, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    cmp r6, #0
    beq .Ldecode_ok
.Lext_decode_loop:
    ldrb r0, [r4]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Ldecode_bad
    lsls r7, r0, #4
    ldrb r0, [r4, #1]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Ldecode_bad
    orrs r0, r7
    strb r0, [r5]
    adds r4, #2
    adds r5, #1
    subs r6, #1
    bne .Lext_decode_loop
.Ldecode_ok:
    movs r0, #1
    pop {r3, r4, r5, r6, r7, pc}
.Ldecode_bad:
    movs r0, #0
    pop {r3, r4, r5, r6, r7, pc}
.Lext_nibble:
    subs r0, #0x30
    cmp r0, #9
    bls .Lnibble_done
    subs r0, #7
    cmp r0, #10
    blo .Lnibble_bad
    cmp r0, #15
    bls .Lnibble_done
.Lnibble_bad:
    movs r0, #255
.Lnibble_done:
    bx lr

.thumb_func
.Lraw_address_guard:
    push {r4, lr}
    ldr r4, =RX
    ldrb r0, [r4, #3]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Lraw_address_bad
    ldrb r0, [r4, #4]
    bl .Lext_nibble
    cmp r0, #15
    bhi .Lraw_address_bad
    movs r0, #1
    pop {r4, pc}
.Lraw_address_bad:
    movs r0, #0
    pop {r4, pc}
.ltorg

/* Gregorian dates2000..2099, time00:00:00..23:59:59; no partial RTC commit. */
.thumb_func
.Lext_calendar:
    push {r4, lr}
    mov r4, r0
    ldrb r0, [r4]
    lsls r0, #8
    ldrb r1, [r4, #1]
    orrs r0, r1
    ldr r1, =2000
    subs r0, r0, r1
    cmp r0, #99
    bhi .Lcalendar_bad
    mov r3, r0
    ldrb r0, [r4, #2]
    subs r0, #1
    cmp r0, #11
    bhi .Lcalendar_bad
    adr r1, .Lmonth_days
    ldrb r1, [r1, r0]
    cmp r0, #1
    bne .Lcalendar_day
    movs r0, #3
    tst r3, r0
    bne .Lcalendar_day
    adds r1, #1
.Lcalendar_day:
    ldrb r0, [r4, #3]
    cmp r0, #1
    blo .Lcalendar_bad
    cmp r0, r1
    bhi .Lcalendar_bad
    ldrb r0, [r4, #4]
    cmp r0, #23
    bhi .Lcalendar_bad
    ldrb r0, [r4, #5]
    cmp r0, #59
    bhi .Lcalendar_bad
    ldrb r0, [r4, #6]
    cmp r0, #59
    bhi .Lcalendar_bad
    movs r0, #1
    pop {r4, pc}
.Lcalendar_bad:
    movs r0, #0
    pop {r4, pc}
.p2align 2
.Lmonth_days:
    .byte 31,28,31,30,31,30,31,31,30,31,30,31
.ltorg
