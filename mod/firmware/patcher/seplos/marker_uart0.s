.macro m0_bne target
    beq .Lm0_short\@
    b \target
.Lm0_short\@:
.endm
.macro m0_beq target
    bne .Lm0_short\@
    b \target
.Lm0_short\@:
.endm
.macro m0_bhi target
    bls .Lm0_short\@
    b \target
.Lm0_short\@:
.endm
/* Revision1: use only existing R buffers/encoder and original IAP primitive.
 * R=UART0. C state/payload and display buffers are never borrowed.
 * The parser wrapper returns0 for handled64 so OEM dispatch skips its RTN04
 * default and proceeds to its unchanged encoder/sender. STATE4 must remain.
 */
.p2align 2
.global hook_uart0_marker_parser
.thumb_func
hook_uart0_marker_parser:
    push {r3, r4, r5, r6, r7, lr}
    ldr r4, =M0_UART0_RX
    ldrb r0, [r4, #7]
    cmp r0, #0x36
    m0_bne .Lm0_original
    ldrb r0, [r4, #8]
    cmp r0, #0x34
    m0_bne .Lm0_original
    /* Strict raw hex before OEM normalizes invalid nibbles to0. */
    ldr r0, =M0_UART0_RX_LENGTH
    ldrh r6, [r0]
    cmp r6, #20
    beq .Lm0_size
    cmp r6, #24
    beq .Lm0_size
    b .Lm0_drop
.Lm0_size:
    subs r6, #1
    ldrb r0, [r4, r6]
    cmp r0, #13
    m0_bne .Lm0_drop
    movs r5, #1
.Lm0_hex:
    ldrb r0, [r4, r5]
    bl .Lext_nibble
    cmp r0, #15
    m0_bhi .Lm0_drop
    adds r5, #1
    cmp r5, r6
    blo .Lm0_hex
    ldrb r0, [r4]
    cmp r0, #0x7e
    m0_bne .Lm0_drop
    ldrb r0, [r4, #1]
    cmp r0, #0x32
    m0_bne .Lm0_drop
    ldrb r0, [r4, #2]
    cmp r0, #0x30
    m0_bne .Lm0_drop
    ldrb r0, [r4, #5]
    cmp r0, #0x34
    m0_bne .Lm0_drop
    ldrb r0, [r4, #6]
    cmp r0, #0x36
    m0_bne .Lm0_drop
    ldrb r0, [r4, #3]
    bl .Lext_nibble
    lsls r5, r0, #4
    ldrb r0, [r4, #4]
    bl .Lext_nibble
    orrs r5, r0
    ldr r0, =ADDRESS
    ldrb r0, [r0]
    cmp r0, #21
    m0_bhi .Lm0_drop
    cmp r0, r5
    m0_bne .Lm0_drop
    bl .Lm0_parse
    cmp r0, #1
    m0_bne .Lm0_return
    ldr r0, =M0_UART0_COMMAND
    ldrb r0, [r0]
    cmp r0, #0x64
    m0_bne .Lm0_bad
    cmp r6, #19
    bne .Lm0_clear
    ldrb r0, [r4, #13]
    cmp r0, #0x30
    m0_bne .Lm0_bad
    ldrb r0, [r4, #14]
    cmp r0, #0x32
    m0_beq .Lm0_status
    cmp r0, #0x33
    m0_bne .Lm0_bad
    /* Same immutable MNT04 bytes on R and C. */
    adr r4, .Lm0_token
    ldr r0, =.Lm0_token-.Lpatch_info_template
    subs r4, r4, r0
    ldr r5, =M0_UART0_INFO
    movs r6, #0
.Lm0_info_copy:
    ldrb r0, [r4, r6]
    lsls r1, r6, #1
    strb r0, [r5, r1]
    adds r6, #1
    cmp r6, #19
    blo .Lm0_info_copy
    ldr r0, =VERSION_ADDRESS
    ldrb r1, [r0]
    strb r1, [r5, #8]
    ldrb r1, [r0, #1]
    strb r1, [r5, #10]
    movs r0, #0x38
    b .Lm0_success
.Lm0_clear:
    /* Exact00 C3 5A only; starting remains a C/master operation. */
    movs r5, #0
    adr r7, .Lm0_token
.Lm0_token_loop:
    mov r0, r5
    adds r0, #13
    ldrb r0, [r4, r0]
    ldrb r1, [r7, r5]
    cmp r0, r1
    m0_bne .Lm0_bad
    adds r5, #1
    cmp r5, #6
    blo .Lm0_token_loop
    ldr r4, =0x23000
    ldr r0, [r4]
    movs r1, #0
    mvns r1, r1
    cmp r0, r1
    m0_beq .Lm0_status
    cmp r0, #0
    m0_bne .Lm0_bad
    mov r0, r4
    ldr r3, =IAP_ERASE+1
    blx r3
    ldr r0, [r4]
    movs r1, #0
    mvns r1, r1
    cmp r0, r1
    m0_bne .Lm0_bad
.Lm0_status:
    ldr r0, =0x23000
    ldr r0, [r0]
    ldr r1, =M0_UART0_INFO
    strb r0, [r1]
    lsrs r0, #8
    strb r0, [r1, #2]
    lsrs r0, #8
    strb r0, [r1, #4]
    lsrs r0, #8
    strb r0, [r1, #6]
    ldr r0, =SLAVES
    ldrb r0, [r0]
    strb r0, [r1, #8]
    movs r0, #0x1c
.Lm0_success:
    ldr r1, =M0_UART0_TX_LENGTH
    strh r0, [r1]
    ldr r1, =M0_UART0_RTN
    movs r0, #0
    strb r0, [r1]
    b .Lm0_return
.Lm0_bad:
    ldr r1, =M0_UART0_TX_LENGTH
    movs r0, #18
    strh r0, [r1]
    ldr r1, =M0_UART0_RTN
    movs r0, #5
    strb r0, [r1]
    b .Lm0_return
.Lm0_drop:
    ldr r1, =M0_UART0_STATE
    movs r0, #0
    strb r0, [r1]
.Lm0_return:
    movs r0, #0
    pop {r3, r4, r5, r6, r7, pc}
.Lm0_original:
    bl .Lm0_parse
    pop {r3, r4, r5, r6, r7, pc}
.Lm0_parse:
    .if MARKER_CUTOFF
    b .Lmarker_cut_parser
    .else
    ldr r3, =M0_UART0_PARSER+1
    bx r3
    .endif
.p2align 2
.Lm0_token:
    .ascii "00C35A"
.p2align 2
.ltorg
