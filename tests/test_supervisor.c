#include "d2e/supervisor.h"

#include <stdio.h>
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

static void exit_42(d2e_x86_cpu *cpu) {
    ++cpu->instructions_retired;
    d2e_x86_set_reg8(cpu, 4U, UINT8_C(0x4c));
    d2e_x86_set_reg8(cpu, 0U, UINT8_C(42));
    d2e_native_interrupt(cpu, UINT8_C(0x21));
}

static const uint8_t test_image[] = {UINT8_C(0xcd), UINT8_C(0x21)};
static const d2e_native_block test_blocks[] = {
    {UINT16_C(0x0100), exit_42},
};
static const d2e_native_program test_program = {
    .name = "supervisor_test",
    .format = D2E_NATIVE_IMAGE_COM,
    .load_segment = UINT16_C(0x1000),
    .entry_ip = UINT16_C(0x0100),
    .image = test_image,
    .image_size = sizeof(test_image),
    .blocks = test_blocks,
    .block_count = sizeof(test_blocks) / sizeof(test_blocks[0]),
};

static void test_catalog(void) {
    static const d2e_package packages[] = {
        {D2E_PACKAGE_ABI_VERSION, "TEST", "Supervisor test",
         D2E_PACKAGE_BUILTIN_FLASH, &test_program},
    };
    d2e_package invalid = packages[0];

    CHECK(d2e_package_validate(&packages[0]));
    CHECK(d2e_package_find(packages, 1U, "test") == &packages[0]);
    CHECK(d2e_package_find(packages, 1U, "missing") == NULL);
    invalid.command = "TOO-LONG!";
    CHECK(!d2e_package_validate(&invalid));
    invalid = packages[0];
    invalid.storage = D2E_PACKAGE_EXTERNAL_MODULE;
    CHECK(!d2e_package_validate(&invalid));
}

static void test_lifecycle(void) {
    uint8_t memory[UINT32_C(0x20000)];
    d2e_x86_cpu cpu;
    d2e_supervisor supervisor;
    const d2e_package package = {
        D2E_PACKAGE_ABI_VERSION, "TEST", "Supervisor test",
        D2E_PACKAGE_BUILTIN_FLASH, &test_program,
    };

    memset(memory, UINT8_C(0xa5), sizeof(memory));
    d2e_x86_cpu_init(&cpu, memory, sizeof(memory), NULL);
    d2e_supervisor_init(&supervisor, &cpu);
    CHECK(supervisor.state == D2E_SUPERVISOR_IDLE);
    CHECK(d2e_supervisor_launch(&supervisor, &package));
    CHECK(supervisor.state == D2E_SUPERVISOR_ACTIVE);
    CHECK(memory[0] == 0U);
    CHECK(memory[UINT32_C(0x10100)] == UINT8_C(0xcd));
    CHECK(!d2e_supervisor_launch(&supervisor, &package));

    CHECK(d2e_supervisor_step(&supervisor, 1U) == D2E_SUPERVISOR_EXITED);
    CHECK(supervisor.last_stop_reason == D2E_X86_EXITED);
    CHECK(supervisor.exit_code == 42U);
    CHECK(cpu.instructions_retired == UINT64_C(1));

    d2e_supervisor_return_to_shell(&supervisor);
    CHECK(supervisor.state == D2E_SUPERVISOR_IDLE);
    CHECK(supervisor.package == NULL);
    CHECK(memory[UINT32_C(0x10100)] == 0U);
    CHECK(cpu.instructions_retired == 0U);
    CHECK(d2e_supervisor_launch(&supervisor, &package));
}

int main(void) {
    test_catalog();
    test_lifecycle();
    if (failures != 0U) {
        fprintf(stderr, "%u supervisor test(s) failed\n", failures);
        return 1;
    }
    puts("D2E package supervisor tests passed");
    return 0;
}
