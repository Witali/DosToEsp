#include "d2e/native_patterns.h"

#include <stdio.h>
#include <stdlib.h>

static unsigned failures;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__,  \
                    #expression);                                               \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

int main(void) {
    const size_t memory_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(memory_size, 1U);
    d2e_x86_cpu cpu;
    uint16_t source;
    uint16_t destination;
    uint16_t count;
    uint32_t base;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, memory_size, NULL);

    base = d2e_x86_linear(UINT16_C(0x0100), UINT16_C(0x0100));
    memory[base] = 1U;
    memory[base + 1U] = 2U;
    memory[base + 2U] = 3U;
    source = UINT16_C(0x0100);
    destination = UINT16_C(0x0101);
    count = 3U;
    d2e_pattern_copy8(&cpu, UINT16_C(0x0100), UINT16_C(0x0100),
                      &source, &destination, &count);
    CHECK(memory[base] == 1U);
    CHECK(memory[base + 1U] == 1U);
    CHECK(memory[base + 2U] == 1U);
    CHECK(memory[base + 3U] == 1U);
    CHECK(source == UINT16_C(0x0103));
    CHECK(destination == UINT16_C(0x0104));
    CHECK(count == 0U);

    cpu.flags |= D2E_X86_FLAG_DF;
    destination = UINT16_C(0x0010);
    count = 2U;
    d2e_pattern_fill16(&cpu, UINT16_C(0x0200), &destination, &count,
                       UINT16_C(0xbeef));
    base = d2e_x86_linear(UINT16_C(0x0200), UINT16_C(0x000e));
    CHECK(memory[base] == UINT8_C(0xef));
    CHECK(memory[base + 1U] == UINT8_C(0xbe));
    CHECK(memory[base + 2U] == UINT8_C(0xef));
    CHECK(memory[base + 3U] == UINT8_C(0xbe));
    CHECK(destination == UINT16_C(0x000c));
    CHECK(count == 0U);

    cpu.flags &= (uint16_t)~D2E_X86_FLAG_DF;
    memory[d2e_x86_linear(UINT16_C(0x0300), UINT16_C(0xffff))] =
        UINT8_C(0x34);
    memory[d2e_x86_linear(UINT16_C(0x0300), UINT16_C(0x0000))] =
        UINT8_C(0x12);
    source = UINT16_C(0xffff);
    destination = UINT16_C(0xffff);
    count = 1U;
    d2e_pattern_copy16(&cpu, UINT16_C(0x0300), UINT16_C(0x0400),
                       &source, &destination, &count);
    CHECK(d2e_x86_read16_seg(&cpu, UINT16_C(0x0400), UINT16_C(0xffff)) ==
          UINT16_C(0x1234));
    CHECK(source == UINT16_C(0x0001));
    CHECK(destination == UINT16_C(0x0001));
    CHECK(count == 0U);

    free(memory);
    if (failures != 0U) {
        fprintf(stderr, "%u native pattern test(s) failed\n", failures);
        return 1;
    }
    puts("native copy/fill pattern tests passed");
    return 0;
}
