#include "d2e/native_runtime.h"
#include "d2e/pc_at.h"
#include "d2e/text_video.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned failures;

typedef struct speaker_capture {
    d2e_pc_speaker_control control;
    unsigned calls;
} speaker_capture;

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

static void capture_speaker(void *context,
                            const d2e_pc_speaker_control *control) {
    speaker_capture *const capture = (speaker_capture *)context;
    capture->control = *control;
    ++capture->calls;
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

    interrupt(cpu, UINT8_C(0x33), UINT16_C(0x0021));
    CHECK(cpu->regs[D2E_X86_AX] == 0U);

    interrupt(cpu, UINT8_C(0x28), UINT16_C(0x2c00));
    CHECK(cpu->stop_reason == D2E_X86_RUNNING);
    interrupt(cpu, UINT8_C(0x2f), UINT16_C(0x1680));
    CHECK(cpu->stop_reason == D2E_X86_RUNNING);
    CHECK(d2e_x86_get_reg8(cpu, 0U) == 0U);
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

    cpu->segments[D2E_X86_ES] = UINT16_C(0xb800);
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0xfe00));
    CHECK(cpu->segments[D2E_X86_ES] == UINT16_C(0xb800));
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
    CHECK(machine->columns == 40U);

    memset(vram, 0, D2E_CGA_VRAM_SIZE);
    cpu->regs[D2E_X86_BX] = UINT16_C(0x0003);
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0e41));
    CHECK(machine->cursor_column[0] == 1U);
    CHECK(d2e_cp437_font[UINT16_C('A') * 8U + 1U] == UINT8_C(0x1e));
    CHECK(vram[d2e_cga_row_offset(1U)] == UINT8_C(0x3f));
    CHECK(vram[d2e_cga_row_offset(1U) + 1U] == UINT8_C(0xc0));

    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0006));
    CHECK(machine->columns == 80U);
    cpu->regs[D2E_X86_CX] = 639U;
    cpu->regs[D2E_X86_DX] = 199U;
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0c01));
    CHECK((vram[d2e_cga_row_offset(199U) + 79U] & 1U) != 0U);
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0d00));
    CHECK(d2e_x86_get_reg8(cpu, 0U) == 1U);

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
    speaker_capture capture;
    unsigned calls;
    uint8_t first;
    uint8_t second;
    memset(&capture, 0, sizeof(capture));
    d2e_pc_at_set_speaker_callback(machine, &capture, capture_speaker);
    CHECK(capture.calls == 1U);
    CHECK(capture.control.gate == 0U);
    CHECK(capture.control.speaker_data == 0U);

    d2e_x86_port_out8(cpu, UINT16_C(0x0043), UINT8_C(0xb6));
    CHECK(capture.calls == 2U);
    CHECK(capture.control.mode == 3U);
    calls = capture.calls;
    d2e_x86_port_out8(cpu, UINT16_C(0x0042), UINT8_C(0x34));
    CHECK(capture.calls == calls);
    d2e_x86_port_out8(cpu, UINT16_C(0x0042), UINT8_C(0x12));
    CHECK(capture.calls == calls + 1U);
    CHECK(capture.control.reload == UINT16_C(0x1234));
    CHECK(machine->pit_access[2] == 3U);
    CHECK(machine->pit_mode[2] == 3U);
    CHECK(machine->pit_reload[2] == UINT16_C(0x1234));

    first = d2e_x86_port_in8(cpu, UINT16_C(0x0040));
    second = d2e_x86_port_in8(cpu, UINT16_C(0x0040));
    CHECK(first == UINT8_C(0xfe));
    CHECK(second == UINT8_C(0xfe));

    d2e_x86_port_out8(cpu, UINT16_C(0x0061), UINT8_C(0x03));
    CHECK(capture.control.gate == 1U);
    CHECK(capture.control.speaker_data == 1U);
    first = d2e_x86_port_in8(cpu, UINT16_C(0x0061));
    second = d2e_x86_port_in8(cpu, UINT16_C(0x0061));
    CHECK(first == UINT8_C(0x13));
    CHECK(second == UINT8_C(0x03));

    calls = capture.calls;
    d2e_pc_at_reset(machine);
    CHECK(capture.calls == calls + 1U);
    CHECK(capture.control.gate == 0U);
    CHECK(capture.control.speaker_data == 0U);
    CHECK(machine->speaker_callback == capture_speaker);
    CHECK(machine->speaker_context == &capture);
    CHECK(machine->attached_cpu == cpu);
    CHECK(cpu->port_context == machine);
}

static void test_dos_memory(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    d2e_pc_at_prepare_dos(machine, UINT16_C(0x1000));
    CHECK(machine->dos_dta_segment == UINT16_C(0x1000));
    CHECK(machine->dos_dta_offset == UINT16_C(0x0080));

    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3000));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x0005));
    CHECK(cpu->regs[D2E_X86_BX] == UINT16_C(0xff00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);

    cpu->segments[D2E_X86_DS] = UINT16_C(0x1234);
    cpu->regs[D2E_X86_DX] = UINT16_C(0x5678);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x1a00));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x2f00));
    CHECK(cpu->segments[D2E_X86_ES] == UINT16_C(0x1234));
    CHECK(cpu->regs[D2E_X86_BX] == UINT16_C(0x5678));

    cpu->segments[D2E_X86_ES] = UINT16_C(0x1000);
    cpu->regs[D2E_X86_BX] = UINT16_C(0x1291);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4a00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK(machine->dos_block_paragraphs == UINT16_C(0x1291));
    CHECK(machine->dos_allocation_cursor == UINT16_C(0x2291));

    cpu->regs[D2E_X86_BX] = UINT16_C(0x0010);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4800));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x2291));

    cpu->segments[D2E_X86_ES] = UINT16_C(0x2291);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4900));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);

    cpu->segments[D2E_X86_ES] = UINT16_C(0x1000);
    cpu->regs[D2E_X86_BX] = UINT16_C(0xffff);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4a00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(8));

    cpu->regs[D2E_X86_BX] = UINT16_C(1);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x5801));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x5800));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(1));

    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3300));
    CHECK((cpu->regs[D2E_X86_DX] & UINT16_C(0x00ff)) == 0U);
    cpu->regs[D2E_X86_DX] = UINT16_C(1);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3301));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3300));
    CHECK((cpu->regs[D2E_X86_DX] & UINT16_C(0x00ff)) == 1U);

    cpu->segments[D2E_X86_DS] = UINT16_C(0x1234);
    cpu->regs[D2E_X86_DX] = UINT16_C(0x5678);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x2523));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3523));
    CHECK(cpu->segments[D2E_X86_ES] == UINT16_C(0x1234));
    CHECK(cpu->regs[D2E_X86_BX] == UINT16_C(0x5678));

    cpu->segments[D2E_X86_DS] = UINT16_C(0x0100);
    cpu->regs[D2E_X86_DX] = UINT16_C(0x0200);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3800));
    CHECK(cpu->regs[D2E_X86_BX] == UINT16_C(1));
    CHECK(cpu->memory[UINT16_C(0x1202)] == (uint8_t)'$');
    CHECK(cpu->memory[UINT16_C(0x120b)] == (uint8_t)'/');

    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x2a00));
    CHECK(cpu->regs[D2E_X86_CX] >= UINT16_C(1980));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x2b01));
    CHECK(d2e_x86_get_reg8(cpu, 0U) == UINT8_C(0xff));
}

static void test_dos_console(d2e_pc_at *machine, d2e_x86_cpu *cpu,
                             uint8_t *vram) {
    machine->key_count = 0U;
    interrupt(cpu, UINT8_C(0x10), UINT16_C(0x0003));
    cpu->segments[D2E_X86_DS] = UINT16_C(0x0100);
    cpu->regs[D2E_X86_DX] = UINT16_C(0x0020);
    memcpy(cpu->memory + UINT16_C(0x1020), "DOS$", 4U);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x0900));
    CHECK(vram[0] == (uint8_t)'D');
    CHECK(vram[2] == (uint8_t)'O');
    CHECK(vram[4] == (uint8_t)'S');
    CHECK(d2e_x86_get_reg8(cpu, 0U) == (uint8_t)'$');

    cpu->regs[D2E_X86_DX] = (uint8_t)'!';
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x0200));
    CHECK(vram[6] == (uint8_t)'!');
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x0b00));
    CHECK(d2e_x86_get_reg8(cpu, 0U) == 0U);
}

static void test_dos_files(d2e_pc_at *machine, d2e_x86_cpu *cpu) {
    static const char filename[] = "d2e_pc_at_test.bin";
    FILE *file = fopen(filename, "wb");
    uint16_t handle;
    if (file == NULL) {
        CHECK(0);
        return;
    }
    CHECK(fwrite("file-data", 1U, 9U, file) == 9U);
    CHECK(fclose(file) == 0);

    d2e_pc_at_set_dos_drive_root(machine, 'C', ".");
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x1900));
    CHECK(d2e_x86_get_reg8(cpu, 0U) == UINT8_C(2));
    cpu->segments[D2E_X86_DS] = UINT16_C(0x0100);
    cpu->regs[D2E_X86_DX] = UINT16_C(3);
    cpu->regs[D2E_X86_SI] = UINT16_C(0x0300);
    cpu->memory[UINT16_C(0x1300)] = UINT8_C(0xaa);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4700));
    CHECK(cpu->memory[UINT16_C(0x1300)] == 0U);

    cpu->regs[D2E_X86_DX] = UINT16_C(0x0400);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x1a00));
    cpu->regs[D2E_X86_DX] = UINT16_C(0x0020);
    cpu->regs[D2E_X86_CX] = 0U;
    memcpy(cpu->memory + UINT16_C(0x1020), filename, sizeof(filename));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4e00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK(cpu->memory[UINT16_C(0x1415)] == UINT8_C(0x20));
    CHECK(d2e_x86_read16(cpu, UINT16_C(0x141a)) == UINT16_C(9));
    CHECK(memcmp(cpu->memory + UINT16_C(0x141e),
                 "D2E_PC_AT_TE", 12U) == 0);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4f00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(18));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x5912));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(18));
    CHECK(cpu->regs[D2E_X86_BX] == UINT16_C(0x0803));

    cpu->segments[D2E_X86_DS] = UINT16_C(0x0100);
    cpu->regs[D2E_X86_DX] = UINT16_C(0x0020);
    memcpy(cpu->memory + UINT16_C(0x1020), filename, sizeof(filename));
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3d00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    handle = cpu->regs[D2E_X86_AX];
    CHECK(handle == UINT16_C(5));

    cpu->regs[D2E_X86_BX] = handle;
    cpu->regs[D2E_X86_CX] = UINT16_C(4);
    cpu->regs[D2E_X86_DX] = UINT16_C(0x0100);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3f00));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(4));
    CHECK(memcmp(cpu->memory + UINT16_C(0x1100), "file", 4U) == 0);

    cpu->regs[D2E_X86_BX] = handle;
    cpu->regs[D2E_X86_CX] = 0U;
    cpu->regs[D2E_X86_DX] = 0U;
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x4202));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(9));
    CHECK(cpu->regs[D2E_X86_DX] == 0U);

    cpu->regs[D2E_X86_BX] = UINT16_C(3);
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x440e));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK(d2e_x86_get_reg8(cpu, 0U) == 0U);

    cpu->regs[D2E_X86_BX] = handle;
    interrupt(cpu, UINT8_C(0x21), UINT16_C(0x3e00));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK(remove(filename) == 0);
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
    test_dos_memory(&machine, &cpu);
    test_dos_console(&machine, &cpu, vram);
    test_dos_files(&machine, &cpu);
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
