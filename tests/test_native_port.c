#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>

typedef struct port_state {
    uint16_t ports[2];
    uint8_t values[2];
    unsigned output_count;
    uint16_t word_port;
    uint16_t word_value;
} port_state;

extern const d2e_native_program d2e_generated_program;

static int input(void *context, uint16_t port, uint8_t *value) {
    (void)context;
    if (port != UINT16_C(0x0060)) {
        return 0;
    }
    *value = UINT8_C(0xa5);
    return 1;
}

static int output(void *context, uint16_t port, uint8_t value) {
    port_state *const state = context;
    if (state->output_count >= 2U) {
        return 0;
    }
    state->ports[state->output_count] = port;
    state->values[state->output_count] = value;
    ++state->output_count;
    return 1;
}

static int input16(void *context, uint16_t port, uint16_t *value) {
    port_state *const state = context;
    state->word_port = port;
    *value = UINT16_C(0x1234);
    return 1;
}

static int output16(void *context, uint16_t port, uint16_t value) {
    port_state *const state = context;
    state->word_port = port;
    state->word_value = value;
    return 1;
}

int main(void) {
    const size_t conventional_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = calloc(conventional_size, 1);
    port_state state = {{0}, {0}, 0, 0, 0};
    d2e_x86_cpu cpu;
    int failed = 0;

    if (memory == NULL) {
        return 2;
    }
    d2e_x86_cpu_init(&cpu, memory, conventional_size, NULL);
    d2e_x86_configure_ports(&cpu, &state, input, output);
    d2e_x86_configure_ports16(&cpu, input16, output16);
    if (!d2e_native_load(&cpu, &d2e_generated_program) ||
        d2e_native_run(&cpu, &d2e_generated_program, 100U) !=
            D2E_X86_EXITED) {
        fprintf(stderr, "port fixture failed: reason=%u port=%04x\n",
                (unsigned)cpu.stop_reason, (unsigned)cpu.fault_address);
        failed = 1;
    } else if (state.output_count != 2U ||
               state.ports[0] != UINT16_C(0x1234) ||
               state.values[0] != UINT8_C(0xa5) ||
               state.ports[1] != UINT16_C(0x0061) ||
               state.values[1] != UINT8_C(0x55) ||
               cpu.instructions_retired != UINT64_C(6)) {
        fprintf(stderr,
                "unexpected port state: count=%u first=%04x/%02x "
                "second=%04x/%02x instructions=%llu\n",
                state.output_count, state.ports[0], state.values[0],
                state.ports[1], state.values[1],
                (unsigned long long)cpu.instructions_retired);
        failed = 1;
    }
    if (!failed) {
        cpu.stop_reason = D2E_X86_RUNNING;
        if (d2e_x86_port_in16(&cpu, UINT16_C(0x01f0)) != UINT16_C(0x1234) ||
            state.word_port != UINT16_C(0x01f0)) {
            fprintf(stderr, "word input did not preserve width and port\n");
            failed = 1;
        }
        d2e_x86_port_out16(&cpu, UINT16_C(0x01f0), UINT16_C(0xabcd));
        if (cpu.stop_reason != D2E_X86_RUNNING ||
            state.word_port != UINT16_C(0x01f0) ||
            state.word_value != UINT16_C(0xabcd)) {
            fprintf(stderr, "word output did not preserve width and port\n");
            failed = 1;
        }
    }
    if (!failed) {
        d2e_x86_configure_ports(&cpu, NULL, NULL, NULL);
        d2e_x86_configure_ports16(&cpu, NULL, NULL);
        cpu.stop_reason = D2E_X86_RUNNING;
        (void)d2e_x86_port_in8(&cpu, UINT16_C(0x0099));
        if (cpu.stop_reason != D2E_X86_UNHANDLED_PORT ||
            cpu.fault_address != UINT16_C(0x0099)) {
            fprintf(stderr, "unknown port was not diagnosed\n");
            failed = 1;
        }
    }

    free(memory);
    if (failed) {
        return 1;
    }
    puts("native port boundary test passed");
    return 0;
}
