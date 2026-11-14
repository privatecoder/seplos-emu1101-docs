/* UART0-only exclusion owns the native RX buffer. Other IRQs remain live.
 * The native timer changes RX count on expiry, never the completed length or
 * frame bytes. Its expiry bit may arrive during validation/native decoding;
 * the native finalizer absorbs it exactly once before the next request.
 */
.balign 2
.thumb_func
hook_poll_start:
    push {r4, r5, r6, lr}
    bl poll_lock_uart0
    ldr r4, =POLL_FLAGS
    ldrb r0, [r4]
    movs r1, #1
    tst r0, r1
    bne poll_start_native
    /* Reset every new request even if there was no inactive timer tick. */
    mrs r3, PRIMASK
    cpsid i
    ldr r1, =POLL_COUNTER
    movs r2, #0
    strb r2, [r1]
    ldrb r0, [r4]
    movs r1, #2
    bics r0, r1
    strb r0, [r4]
    ldr r1, =POLL_RX_COUNT
    strh r2, [r1]
    msr PRIMASK, r3
poll_start_native:
    ldr r3, =(POLL_START + 1)
    blx r3
    bl poll_unlock_uart0
    pop {r4, r5, r6, pc}

.balign 2
.thumb_func
hook_poll_evaluate:
    push {r4, r5, r6, lr}
    bl poll_lock_uart0
    ldr r4, =POLL_FLAGS
    ldrb r0, [r4]
    movs r1, #1
    tst r0, r1
    beq poll_evaluate_return
    movs r1, #0x30
    tst r0, r1
    bne poll_evaluate_broadcast
    ldr r5, =POLL_STATE
    ldrb r0, [r5]
    cmp r0, #4
    bne poll_evaluate_expiry
    ldr r0, =POLL_RX_LENGTH
    ldrh r0, [r0]
    cmp r0, #82
    bne poll_evaluate_discard
    bl poll_validate
    cmp r0, #0
    beq poll_evaluate_discard
    /* Promote only a bounded, nonmutatingly validated complete response. */
    mrs r3, PRIMASK
    cpsid i
    ldrb r0, [r4]
    movs r1, #2
    orrs r0, r1
    strb r0, [r4]
    msr PRIMASK, r3
    b poll_evaluate_native
poll_evaluate_discard:
    movs r0, #0
    strb r0, [r5]
    ldr r1, =POLL_RX_COUNT
    strh r0, [r1]
poll_evaluate_expiry:
    ldrb r0, [r4]
    movs r1, #2
    tst r0, r1
    beq poll_evaluate_return
poll_evaluate_native:
    ldr r3, =(POLL_EVALUATE + 1)
    blx r3
    /* No rejected/consumed frame may be evaluated again or cross requests. */
    ldr r1, =POLL_STATE
    movs r0, #0
    strb r0, [r1]
    ldr r1, =POLL_RX_COUNT
    strh r0, [r1]
poll_evaluate_return:
    bl poll_unlock_uart0
    pop {r4, r5, r6, pc}
poll_evaluate_broadcast:
    ldr r3, =(POLL_EVALUATE + 1)
    blx r3
    b poll_evaluate_return

/* R6 holds exactly the incoming UART0 enable bit. W1C/W1S preserve all other
 * enables and pending IRQs. The barriers finish exclusion before buffer access.
 * This does not touch PRIMASK, including when the caller is already masked.
 */
.thumb_func
poll_lock_uart0:
    ldr r0, =0xe000e100
    ldr r6, [r0]
    movs r1, #POLL_IRQ_MASK
    ands r6, r1
    ldr r0, =0xe000e180
    str r1, [r0]
    dsb
    isb
    bx lr
.thumb_func
poll_unlock_uart0:
    ldr r0, =0xe000e100
    str r6, [r0]
    dsb
    isb
    bx lr

/* Fixed 82-byte frame: all ASCII hex characters, matching address, 5A,
 * C040 length/check nibble, CR and additive checksum. No native parser runs
 * until this check succeeds; malformed input cannot mutate shared metadata.
 */
.thumb_func
poll_validate:
    push {r4, r5, r6, r7, lr}
    sub sp, #4
    ldr r4, =POLL_RX_BUFFER
    ldrb r0, [r4]
    cmp r0, #0x7e
    bne poll_invalid_header
    movs r1, #81
    ldrb r0, [r4, r1]
    cmp r0, #13
    bne poll_invalid_header
    ldrb r0, [r4, #1]
    cmp r0, #0x32
    bne poll_invalid_header
    ldrb r0, [r4, #2]
    cmp r0, #0x30
    bne poll_invalid_header
    ldrb r0, [r4, #5]
    cmp r0, #0x34
    bne poll_invalid_header
    ldrb r0, [r4, #6]
    cmp r0, #0x36
    bne poll_invalid_header
    ldrb r0, [r4, #7]
    cmp r0, #0x35
    bne poll_invalid_header
    ldrb r0, [r4, #8]
    cmp r0, #0x41
    bne poll_invalid_header
    ldrb r0, [r4, #9]
    cmp r0, #0x43
    bne poll_invalid_header
    ldrb r0, [r4, #10]
    cmp r0, #0x30
    bne poll_invalid_header
    ldrb r0, [r4, #11]
    cmp r0, #0x34
    bne poll_invalid_header
    ldrb r0, [r4, #12]
    cmp r0, #0x30
    beq poll_validate_address
poll_invalid_header:
    b poll_invalid
poll_validate_address:
    ldrb r0, [r4, #3]
    bl poll_nibble
    cmp r0, #16
    bhs poll_invalid
    lsls r5, r0, #4
    ldrb r0, [r4, #4]
    bl poll_nibble
    cmp r0, #16
    bhs poll_invalid
    orrs r5, r0
    ldr r0, =POLL_INDEX
    ldrb r0, [r0]
    cmp r0, r5
    bne poll_invalid
    movs r5, #1
    movs r6, #0
    movs r7, #0
poll_validate_loop:
    ldrb r0, [r4, r5]
    str r0, [sp]
    bl poll_nibble
    cmp r0, #16
    bhs poll_invalid
    cmp r5, #77
    bhs poll_validate_checksum
    ldr r0, [sp]
    adds r6, r6, r0
    b poll_validate_next
poll_validate_checksum:
    lsls r7, r7, #4
    orrs r7, r0
poll_validate_next:
    adds r5, r5, #1
    cmp r5, #81
    blo poll_validate_loop
    rsbs r6, r6, #0
    uxth r6, r6
    cmp r6, r7
    bne poll_invalid
    movs r0, #1
    b poll_valid_return
poll_invalid:
    movs r0, #0
poll_valid_return:
    add sp, #4
    pop {r4, r5, r6, r7, pc}
.thumb_func
poll_nibble:
    subs r0, #0x30
    cmp r0, #9
    bls poll_nibble_return
    subs r0, #7
    cmp r0, #10
    blo poll_nibble_bad
    cmp r0, #15
    bls poll_nibble_return
poll_nibble_bad:
    movs r0, #16
poll_nibble_return:
    bx lr
.ltorg
