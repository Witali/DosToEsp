#include "d2e/native_runtime.h"
#include "d2e/pc_at.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned failures;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__,  \
                    #expression);                                               \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

static void interrupt(d2e_x86_cpu *cpu, uint8_t number, uint16_t ax) {
    cpu->regs[D2E_X86_AX] = ax;
    cpu->stop_reason = D2E_X86_RUNNING;
    d2e_native_interrupt(cpu, number);
}

static void test_identity_and_clock(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    interrupt(cpu, UINT8_C(0x11), 0U);
    CHECK(cpu->stop_reason == D2E_X86_RUNNING);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x0021));

    interrupt(cpu, UINT8_C(0x12), 0U);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(640));

    d2e_pc_at_set_timer_ticks(machine, UINT32_C(0x12345678), 1U);
    interrupt(cpu, UINT8_C(0x1a), 0U);
    CHECK(cpu->regs[D2E_X86_CX] == UINT16_C(0x1234));
    CHECK(cpu->regs[D2E_X86_DX] == UINT16_C(0x5678));
    CHECK(d2e_x86_get_reg8(cpu, 0U) == 1U);
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
}

static void test_text_video(d2e_pc_at *machine, d2e_x86_cpu *cpu,
                            uint8_t *vram) {
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0003));
    CHECK(machine->video_mode == 3U);
    CHECK(machine->columns == 80U);
    CHECK(cpu->memory[UINT16_C(0x449)] == 3U);
    CHECK(cpu->memory[UINT16_C(0x44a)] == 80U);

    cpu->regs[D2E_X86_BX] = 0U;
    cpu->regs[D2E_X86_DX] = UINT16_C(0x0203);
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0200));
    cpu->regs[D2E_X86_BX] = UINT16_C(0x001e);
    cpu->regs[D2E_X86_CX] = 2U;
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0941));
    CHECK(vram[(2U * 80U + 3U) * 2U] == UINT8_C('A'));
    CHECK(vram[(2U * 80U + 3U) * 2U + 1U] == UINT8_C(0x1e));
    CHECK(vram[(2U * 80U + 4U) * 2U] == UINT8_C('A'));

    cpu->regs[D2E_X86_BX] = 0U;
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0800));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x1e41));

    cpu->regs[D2E_X86_BX] = UINT16_C(0x0007);
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0e42));
    CHECK(vram[(2U * 80U + 3U) * 2U] == UINT8_C('B'));
    CHECK(machine->cursor_column[0] == 4U);
}

static void test_cga_pixels(d2e_pc_at *machine, d2e_x86_cpu *cpu,
                            uint8_t *vram) {
    size_t offset;
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0004));
    cpu->regs[D2E_X86_CX] = 7U;
    cpu->regs[D2E_X86_DX] = 3U;
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0c03));
    offset = d2e_cga_row_offset(3U) + 1U;
    CHECK((vram[offset] & UINT8_C(0x03)) == UINT8_C(0x03));
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0d00));
    CHECK(d2e_x86_get_reg8(cpu, 0U) == 3U);
    CHECK(machine->cga.mode == 4U);

    d2e_x86_port_out8(cpu, UINT16_C(0x03d9), UINT8_C(0x20));
    CHECK(cpu->stop_reason == D2E_X86_RUNNING);
    CHECK(machine->cga.color_control == UINT8_C(0x20));
    d2e_x86_port_out8(cpu, UINT16_C(0x03d4), UINT8_C(0x0c));
    d2e_x86_port_out8(cpu, UINT16_C(0x03d5), UINT8_C(0x12));
    CHECK(machine->cga_crtc[UINT8_C(0x0c)] == UINT8_C(0x12));
    CHECK((d2e_x86_port_in8(cpu, UINT16_C(0x03da)) & UINT8_C(0x09)) ==
          UINT8_C(0x09));
}

static void test_keyboard(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    interrupt(cpu, UINT8_C(0x16), UINT16_C(0x0100));
    CHECK((cpu->flags & D2E_X86_FLAG_ZF) != 0U);
    interrupt(cpu, UINT8_C(0x16), UINT16_C(0x0000));
    CHECK(cpu->stop_reason == D2E_X86_WAITING_INPUT);

    CHECK(d2e_pc_at_enqueue_key(machine, UINT8_C('x'), UINT8_C(0x2d)));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x2d78));
    CHECK(machine->key_count == 0U);
    cpu->stop_reason = D2E_X86_RUNNING;

    CHECK(d2e_pc_at_enqueue_key(machine, UINT8_C('x'), UINT8_C(0x2d)));
    interrupt(cpu, UINT8_C(0x16), UINT16_C(0x0100));
    CHECK((cpu->flags & D2E_X86_FLAG_ZF) == 0U);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x2d78));
    interrupt(cpu, UINT8_C(0x16), UINT16_C(0x0000));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x2d78));
    CHECK(machine->key_count == 0U);

    machine->scan_head = 0U;
    machine->scan_count = 0U;
    cpu->segments[D2E_X86_CS] = UINT16_C(0x1723);
    cpu->ip = UINT16_C(0x4567);
    cpu->regs[D2E_X86_SP] = UINT16_C(0x0200);
    cpu->flags = D2E_X86_FLAG_IF | D2E_X86_FLAG_CF | D2E_X86_FLAG_FIXED;
    d2e_x86_write16(cpu, UINT32_C(9) * 4U, UINT16_C(0x14b3));
    d2e_x86_write16(cpu, UINT32_C(9) * 4U + 2U, UINT16_C(0x1723));
    CHECK(d2e_pc_at_enqueue_key(machine, UINT8_C(' '), UINT8_C(0x39)));
    CHECK(d2e_x86_port_in8(cpu, UINT16_C(0x0064)) == UINT8_C(1));
    CHECK(d2e_pc_at_dispatch_keyboard_irq(machine));
    CHECK(cpu->segments[D2E_X86_CS] == UINT16_C(0x1723));
    CHECK(cpu->ip == UINT16_C(0x14b3));
    CHECK(cpu->regs[D2E_X86_SP] == UINT16_C(0x01fa));
    CHECK((cpu->flags & D2E_X86_FLAG_IF) == 0U);
    CHECK(d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS],
                             UINT16_C(0x01fa)) == UINT16_C(0x4567));
    CHECK(d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS],
                             UINT16_C(0x01fc)) == UINT16_C(0x1723));
    CHECK(d2e_x86_read16_seg(cpu, cpu->segments[D2E_X86_SS],
                             UINT16_C(0x01fe)) ==
          (D2E_X86_FLAG_IF | D2E_X86_FLAG_CF | D2E_X86_FLAG_FIXED));
    CHECK(d2e_x86_port_in8(cpu, UINT16_C(0x0060)) == UINT8_C(0x39));
    d2e_x86_port_out8(cpu, UINT16_C(0x0020), UINT8_C(0x20));
    cpu->flags |= D2E_X86_FLAG_IF;
    cpu->regs[D2E_X86_SP] = UINT16_C(0x0200);
    CHECK(d2e_pc_at_dispatch_keyboard_irq(machine));
    CHECK(d2e_x86_port_in8(cpu, UINT16_C(0x0060)) == UINT8_C(0xb9));
    CHECK(d2e_x86_port_in8(cpu, UINT16_C(0x0064)) == 0U);
}

static void test_pit_and_speaker(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    uint8_t first;
    uint8_t second;
    d2e_x86_port_out8(cpu, UINT16_C(0x0043), UINT8_C(0xb6));
    d2e_x86_port_out8(cpu, UINT16_C(0x0042), UINT8_C(0x34));
    d2e_x86_port_out8(cpu, UINT16_C(0x0042), UINT8_C(0x12));
    CHECK(machine->pit_access[2] == 3U);
    CHECK(machine->pit_mode[2] == 3U);
    CHECK(machine->pit_reload[2] == UINT16_C(0x1234));

    first = d2e_x86_port_in8(cpu, UINT16_C(0x0040));
    second = d2e_x86_port_in8(cpu, UINT16_C(0x0040));
    CHECK(first == UINT8_C(0xfe));
    CHECK(second == UINT8_C(0xfe));

    d2e_x86_port_out8(cpu, UINT16_C(0x0061), UINT8_C(0x03));
    first = d2e_x86_port_in8(cpu, UINT16_C(0x0061));
    second = d2e_x86_port_in8(cpu, UINT16_C(0x0061));
    CHECK(first == UINT8_C(0x13));
    CHECK(second == UINT8_C(0x03));
}

static void test_strict_unknown(d2e_x86_cpu *cpu) {
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0xff00));
    CHECK(cpu->stop_reason == D2E_X86_UNHANDLED_INTERRUPT);
    CHECK(cpu->fault_address == UINT32_C(0x10ff));
}

int main(void) {
    uint8_t *const memory = calloc(D2E_X86_MEMORY_SIZE, 1U);
    uint8_t *const vram = calloc(D2E_CGA_VRAM_SIZE, 1U);
    d2e_x86_cpu cpu;
    d2e_pc_at machine;

    if (memory == NULL || vram == NULL) {
        free(vram);
        free(memory);
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, D2E_X86_MEMORY_SIZE, NULL);
    d2e_pc_at_init(&machine, vram, D2E_CGA_VRAM_SIZE);
    d2e_pc_at_attach(&machine, &cpu);

    test_identity_and_clock(&machine, &cpu);
    test_text_video(&machine, &cpu, vram);
    test_cga_pixels(&machine, &cpu, vram);
    test_pit_and_speaker(&machine, &cpu);
    test_keyboard(&machine, &cpu);
    test_strict_unknown(&cpu);

    free(vram);
    free(memory);
    if (failures != 0U) {
        fprintf(stderr, "%u PC/AT BIOS test(s) failed\n", failures);
        return 1;
    }
    puts("PC/AT BIOS tests passed");
    return 0;
}
