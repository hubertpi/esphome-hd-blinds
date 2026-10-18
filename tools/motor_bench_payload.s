/* Assemble Thumb-2 for Cortex-M4 at 0x2000f000.
 * PARAMETER 0x5a5a0075 is replaced by Python with the requested duty.
 * Original firmware is verified before these fixed-address calls.
 */

.syntax unified
.thumb
cpsid i
ldr r0, =0xe000edfc
ldr r1, [r0]
orr r1, r1, #0x1000000
str r1, [r0]
ldr r0, =0xe0001000
ldr r1, [r0]
orr r1, r1, #1
str r1, [r0]
movs r0, #1
ldr r4, =0x105f5
blx r4
ldr r4, =0xe0001004
ldr r5, [r4]
ldr r6, =400000
settle:
ldr r0, [r4]
subs r0, r0, r5
cmp r0, r6
blo settle
ldr r4, =0x10719
blx r4
ldr r4, =0x40018000
ldr r5, =0xe0001004
ldr r6, [r5]
ldr r7, =20000000
movs r0, #0
mov r8, r0
mov r11, r0
ldr r9, [r4, #0x6c]
ldr r10, [r4, #0x1c]
adds r10, #1
wait:
ldr r0, [r5]
subs r0, r0, r6
cmp r0, r7
bhs done
cmp r11, #0
bne wait
ldr r0, [r4, #0xc]
lsls r0, r0, #31
bpl wait
movs r0, #1
str r0, [r4, #0x14]
adds r8, #1
cmp r8, #40
blo wait
movs r0, #0
mov r8, r0
adds r9, #1
str r9, [r4, #0x6c]
str r9, [r4, #0x7c]
cmp r9, r10
blo wait
ldr r0, =0x5a5a0075
cmp r0, #100
beq full
subs r1, r10, #1
mul r0, r1, r0
movs r1, #100
udiv r0, r0, r1
b setpoint
full:
mov r0, r10
setpoint:
str r0, [r4, #0x6c]
str r0, [r4, #0x7c]
mov r9, r0
movs r0, #1
mov r11, r0
ldr r6, [r5]
b wait
done:
movs r0, #0
ldr r4, =0x105f5
blx r4
bkpt #0
b .
