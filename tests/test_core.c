#include "d2e/x86_cpu.h"
#include "d2e/x86_alu.h"

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

static void test_register_bytes(d2e_x86_cpu *cpu) {
    cpu->regs[D2E_X86_AX] = UINT16_C(0x1234);
    cpu->regs[D2E_X86_BX] = UINT16_C(0xabcd);
    CHECK(d2e_x86_get_reg8(cpu, 0) == UINT8_C(0x34));
    CHECK(d2e_x86_get_reg8(cpu, 3) == UINT8_C(0xcd));
    CHECK(d2e_x86_get_reg8(cpu, 4) == UINT8_C(0x12));
    CHECK(d2e_x86_get_reg8(cpu, 7) == UINT8_C(0xab));

    d2e_x86_set_reg8(cpu, 0, UINT8_C(0xfe));
    d2e_x86_set_reg8(cpu, 7, UINT8_C(0x55));
    CHECK(cpu->regs[D2E_X86_AX] == UINT16_C(0x12fe));
    CHECK(cpu->regs[D2E_X86_BX] == UINT16_C(0x55cd));
}

static void test_address_wrap(d2e_x86_cpu *cpu) {
    CHECK(d2e_x86_linear(UINT16_C(0xffff), UINT16_C(0xffff)) ==
          UINT32_C(0x0ffef));

    d2e_x86_write16(cpu, D2E_X86_ADDRESS_MASK, UINT16_C(0x3412));
    CHECK(d2e_x86_read8(cpu, D2E_X86_ADDRESS_MASK) == UINT8_C(0x12));
    CHECK(d2e_x86_read8(cpu, 0) == UINT8_C(0x34));
    CHECK(d2e_x86_read16(cpu, D2E_X86_ADDRESS_MASK) == UINT16_C(0x3412));
    CHECK(cpu->page_generations[D2E_X86_PAGE_COUNT - 1U] == 1U);
    CHECK(cpu->page_generations[0] == 1U);

    d2e_x86_write16_seg(cpu, UINT16_C(0x3000), UINT16_C(0xffff),
                        UINT16_C(0x7856));
    CHECK(d2e_x86_read8(
              cpu, d2e_x86_linear(UINT16_C(0x3000), UINT16_C(0xffff))) ==
          UINT8_C(0x56));
    CHECK(d2e_x86_read8(cpu, d2e_x86_linear(UINT16_C(0x3000), 0)) ==
          UINT8_C(0x78));
    CHECK(d2e_x86_read16_seg(cpu, UINT16_C(0x3000), UINT16_C(0xffff)) ==
          UINT16_C(0x7856));
}

static void test_fetch_wrap(d2e_x86_cpu *cpu) {
    cpu->segments[D2E_X86_CS] = UINT16_C(0x1000);
    cpu->ip = UINT16_C(0xffff);
    cpu->memory[d2e_x86_linear(UINT16_C(0x1000), UINT16_C(0xffff))] =
        UINT8_C(0xaa);
    cpu->memory[d2e_x86_linear(UINT16_C(0x1000), 0)] = UINT8_C(0xbb);
    CHECK(d2e_x86_fetch8(cpu, 0) == UINT8_C(0xaa));
    CHECK(d2e_x86_fetch8(cpu, 1) == UINT8_C(0xbb));
    CHECK(d2e_x86_fetch16(cpu, 0) == UINT16_C(0xbbaa));
}

static void test_stack(d2e_x86_cpu *cpu) {
    cpu->segments[D2E_X86_SS] = UINT16_C(0x2000);
    cpu->regs[D2E_X86_SP] = 1;
    d2e_x86_push16(cpu, UINT16_C(0xbeef));
    CHECK(cpu->regs[D2E_X86_SP] == UINT16_C(0xffff));
    CHECK(d2e_x86_read16_seg(cpu, UINT16_C(0x2000), UINT16_C(0xffff)) ==
          UINT16_C(0xbeef));
    CHECK(d2e_x86_pop16(cpu) == UINT16_C(0xbeef));
    CHECK(cpu->regs[D2E_X86_SP] == 1U);
}

static void test_alu_flags(d2e_x86_cpu *cpu) {
    uint16_t result16;
    uint8_t result8;

    cpu->flags = D2E_X86_FLAG_FIXED;
    result8 = d2e_x86_add8(cpu, UINT8_C(0x7f), 1U);
    CHECK(result8 == UINT8_C(0x80));
    CHECK((cpu->flags & D2E_X86_FLAG_OF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_SF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_AF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);

    result8 = d2e_x86_add8(cpu, UINT8_C(0xff), 1U);
    CHECK(result8 == 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_ZF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_PF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_OF) == 0U);

    result16 = d2e_x86_sub16(cpu, UINT16_C(0x8000), 1U);
    CHECK(result16 == UINT16_C(0x7fff));
    CHECK((cpu->flags & D2E_X86_FLAG_OF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);

    result16 = d2e_x86_sub16(cpu, 0U, 1U);
    CHECK(result16 == UINT16_C(0xffff));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_SF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_PF) != 0U);

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    result16 = d2e_x86_inc16(cpu, UINT16_C(0x7fff));
    CHECK(result16 == UINT16_C(0x8000));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_OF) != 0U);

    cpu->flags = D2E_X86_FLAG_FIXED;
    result8 = d2e_x86_dec8(cpu, UINT8_C(0x80));
    CHECK(result8 == UINT8_C(0x7f));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_OF) != 0U);

    result16 = d2e_x86_logic16(cpu, UINT16_C(0x0003));
    CHECK(result16 == UINT16_C(0x0003));
    CHECK((cpu->flags & D2E_X86_FLAG_PF) != 0U);
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF |
                         D2E_X86_FLAG_AF | D2E_X86_FLAG_ZF |
                         D2E_X86_FLAG_SF)) == 0U);
}

static void test_shift_flags(d2e_x86_cpu *cpu) {
    uint16_t flags;

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_DF;
    CHECK(d2e_x86_shl8(cpu, UINT8_C(0x81), 1U) == UINT8_C(0x02));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));
    CHECK((cpu->flags & D2E_X86_FLAG_DF) != 0U);

    CHECK(d2e_x86_shr16(cpu, UINT16_C(0x8001), 1U) == UINT16_C(0x4000));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));

    flags = cpu->flags;
    CHECK(d2e_x86_shl16(cpu, UINT16_C(0x1234), 0U) == UINT16_C(0x1234));
    CHECK(cpu->flags == flags);

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_rcl8(cpu, UINT8_C(0x80), 1U) == UINT8_C(0x01));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_rcr8(cpu, UINT8_C(0x01), 1U) == UINT8_C(0x80));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));

    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_sar8(cpu, UINT8_C(0x81), 1U) == UINT8_C(0xc0));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_OF) == 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_SF) != 0U);

    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_rol8(cpu, UINT8_C(0x81), 1U) == UINT8_C(0x03));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));

    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_ror16(cpu, UINT16_C(0x0001), 1U) == UINT16_C(0x8000));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));
}

static void test_multiply_and_adjust(d2e_x86_cpu *cpu) {
    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_mul8(cpu, UINT8_C(3), UINT8_C(2)) == UINT16_C(6));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) == 0U);
    CHECK(d2e_x86_mul8(cpu, UINT8_C(0xff), UINT8_C(2)) == UINT16_C(0x01fe));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));
    CHECK(d2e_x86_mul16(cpu, UINT16_C(0xffff), UINT16_C(2)) ==
          UINT32_C(0x0001fffe));

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_ZF;
    CHECK(d2e_x86_imul8(cpu, UINT8_C(0xfe), UINT8_C(3)) ==
          UINT16_C(0xfffa));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) == 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_ZF) != 0U);
    CHECK(d2e_x86_imul8(cpu, UINT8_C(0x80), UINT8_C(2)) ==
          UINT16_C(0xff00));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));
    CHECK(d2e_x86_imul16(cpu, UINT16_C(0x8000), UINT16_C(0xffff)) ==
          UINT32_C(0x00008000));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_OF));

    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_aaa(cpu, UINT16_C(0x090a)) == UINT16_C(0x0a00));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF));
    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_aaa(cpu, UINT16_C(0x0203)) == UINT16_C(0x0203));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF)) == 0U);

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_AF;
    CHECK(d2e_x86_aas(cpu, UINT16_C(0x0303)) == UINT16_C(0x010d));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF));

    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_daa(cpu, UINT16_C(0x009b)) == UINT16_C(0x0001));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF));

    cpu->flags = D2E_X86_FLAG_FIXED;
    CHECK(d2e_x86_das(cpu, UINT16_C(0x009b)) == UINT16_C(0x0035));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF));

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_aam(cpu, UINT16_C(0x002a)) == UINT16_C(0x0402));
    CHECK((cpu->flags & D2E_X86_FLAG_CF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_PF) == 0U);

    CHECK(d2e_x86_aad(cpu, UINT16_C(0x0402)) == UINT16_C(0x002a));
    CHECK((cpu->flags & D2E_X86_FLAG_PF) == 0U);
}

static void test_divide(d2e_x86_cpu *cpu) {
    uint16_t flags;

    cpu->stop_reason = D2E_X86_RUNNING;
    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_DF | D2E_X86_FLAG_ZF;
    flags = cpu->flags;
    CHECK(d2e_x86_div8(cpu, UINT16_C(0x1234), UINT8_C(0x34)) ==
          UINT16_C(0x2059));
    CHECK(cpu->stop_reason == D2E_X86_RUNNING);
    CHECK(cpu->flags == flags);
    CHECK(d2e_x86_div16(cpu, UINT32_C(0x00010000), UINT16_C(2)) ==
          UINT32_C(0x00008000));
    CHECK(d2e_x86_idiv8(cpu, UINT16_C(0xff9c), UINT8_C(7)) ==
          UINT16_C(0xfef2));
    CHECK(d2e_x86_idiv16(cpu, UINT32_C(0xfffe7960), UINT16_C(300)) ==
          UINT32_C(0xff9cfeb3));

    CHECK(d2e_x86_div8(cpu, UINT16_C(0x0100), UINT8_C(1)) ==
          UINT16_C(0x0100));
    CHECK(cpu->stop_reason == D2E_X86_DIVIDE_ERROR);
    cpu->stop_reason = D2E_X86_RUNNING;
    CHECK(d2e_x86_div16(cpu, UINT32_C(1), UINT16_C(0)) == UINT32_C(1));
    CHECK(cpu->stop_reason == D2E_X86_DIVIDE_ERROR);
    cpu->stop_reason = D2E_X86_RUNNING;
    CHECK(d2e_x86_idiv16(cpu, UINT32_C(0x80000000), UINT16_C(0xffff)) ==
          UINT32_C(0x80000000));
    CHECK(cpu->stop_reason == D2E_X86_DIVIDE_ERROR);
    cpu->stop_reason = D2E_X86_RUNNING;
}

static void test_add_with_carry(d2e_x86_cpu *cpu) {
    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_adc8(cpu, UINT8_C(0xff), UINT8_C(0)) == UINT8_C(0));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
                         D2E_X86_FLAG_AF | D2E_X86_FLAG_ZF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_PF |
           D2E_X86_FLAG_AF | D2E_X86_FLAG_ZF));
    CHECK((cpu->flags & (D2E_X86_FLAG_SF | D2E_X86_FLAG_OF)) == 0U);

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_adc16(cpu, UINT16_C(0x7fff), UINT16_C(0)) ==
          UINT16_C(0x8000));
    CHECK((cpu->flags & D2E_X86_FLAG_OF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_sbb8(cpu, UINT8_C(0), UINT8_C(0)) == UINT8_C(0xff));
    CHECK((cpu->flags & (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF |
                         D2E_X86_FLAG_SF | D2E_X86_FLAG_PF)) ==
          (D2E_X86_FLAG_CF | D2E_X86_FLAG_AF |
           D2E_X86_FLAG_SF | D2E_X86_FLAG_PF));

    cpu->flags = D2E_X86_FLAG_FIXED | D2E_X86_FLAG_CF;
    CHECK(d2e_x86_sbb16(cpu, UINT16_C(0x8000), UINT16_C(0x7fff)) == 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_OF) != 0U);
    CHECK((cpu->flags & D2E_X86_FLAG_CF) == 0U);
}

static void test_sparse_video_mapping(void) {
    uint8_t conventional[UINT16_C(0x1000)];
    uint8_t cga_vram[UINT16_C(0x4000)];
    d2e_x86_cpu cpu;

    memset(conventional, 0, sizeof(conventional));
    memset(cga_vram, 0, sizeof(cga_vram));
    d2e_x86_cpu_init(&cpu, conventional, sizeof(conventional), NULL);
    d2e_x86_map_cga_vram(&cpu, cga_vram);
    d2e_x86_write8(&cpu, UINT32_C(0xb8123), UINT8_C(0x5a));
    CHECK(cga_vram[UINT16_C(0x0123)] == UINT8_C(0x5a));
    CHECK(d2e_x86_read8(&cpu, UINT32_C(0xb8123)) == UINT8_C(0x5a));
    CHECK(d2e_x86_read8(&cpu, UINT32_C(0xa0000)) == UINT8_C(0xff));
    d2e_x86_write8(&cpu, UINT32_C(0xa0000), 0);
    CHECK(cpu.stop_reason == D2E_X86_UNMAPPED_MEMORY);
    CHECK(cpu.fault_address == UINT32_C(0xa0000));
}

int main(void) {
    uint8_t *const memory = calloc(D2E_X86_MEMORY_SIZE, 1);
    uint32_t *const generations = calloc(D2E_X86_PAGE_COUNT, sizeof(uint32_t));
    d2e_x86_cpu cpu;

    if (memory == NULL || generations == NULL) {
        fprintf(stderr, "allocation failed\n");
        free(generations);
        free(memory);
        return 2;
    }

    d2e_x86_cpu_init(&cpu, memory, D2E_X86_MEMORY_SIZE, generations);
    test_register_bytes(&cpu);
    test_address_wrap(&cpu);
    test_fetch_wrap(&cpu);
    test_stack(&cpu);
    test_alu_flags(&cpu);
    test_shift_flags(&cpu);
    test_multiply_and_adjust(&cpu);
    test_divide(&cpu);
    test_add_with_carry(&cpu);
    test_sparse_video_mapping();

    free(generations);
    free(memory);
    if (failures != 0U) {
        fprintf(stderr, "%u test(s) failed\n", failures);
        return 1;
    }
    puts("d2e core tests passed");
    return 0;
}
