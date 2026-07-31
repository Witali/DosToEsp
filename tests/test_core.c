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

    d2e_x86_cpu_init(&cpu, memory, generations);
    test_register_bytes(&cpu);
    test_address_wrap(&cpu);
    test_fetch_wrap(&cpu);
    test_stack(&cpu);
    test_alu_flags(&cpu);

    free(generations);
    free(memory);
    if (failures != 0U) {
        fprintf(stderr, "%u test(s) failed\n", failures);
        return 1;
    }
    puts("d2e core tests passed");
    return 0;
}
