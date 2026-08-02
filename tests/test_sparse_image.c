#include "d2e/native_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    static const uint8_t fragment_data[] = {UINT8_C(0x42), UINT8_C(0x43)};
    static const d2e_native_image_fragment fragments[] = {
        {UINT32_C(2), fragment_data, sizeof(fragment_data)},
    };
    static const d2e_native_program program = {
        .name = "sparse-image",
        .format = D2E_NATIVE_IMAGE_COM,
        .load_segment = UINT16_C(0x0100),
        .entry_cs = 0,
        .entry_ip = UINT16_C(0x0100),
        .initial_ss = 0,
        .initial_sp = UINT16_C(0xfffe),
        .image = NULL,
        .image_size = 6,
        .relocations = NULL,
        .relocation_count = 0,
        .blocks = NULL,
        .block_count = 0,
        .region = NULL,
        .image_fragments = fragments,
        .image_fragment_count = 1,
    };
    const size_t memory_size = UINT32_C(128) * 1024U;
    uint8_t *const memory = malloc(memory_size);
    d2e_x86_cpu cpu;
    const uint32_t image_address =
        d2e_x86_linear(program.load_segment, UINT16_C(0x0100));
    static const uint8_t expected[] = {0, 0, UINT8_C(0x42), UINT8_C(0x43), 0, 0};

    if (memory == NULL) {
        return 2;
    }
    memset(memory, UINT8_C(0xa5), memory_size);
    d2e_x86_cpu_init(&cpu, memory, memory_size, NULL);
    if (!d2e_native_load(&cpu, &program)) {
        fputs("sparse COM load failed\n", stderr);
        free(memory);
        return 1;
    }
    if (memcmp(memory + image_address, expected, sizeof(expected)) != 0) {
        fputs("sparse COM data or omitted ranges are incorrect\n", stderr);
        free(memory);
        return 1;
    }
    free(memory);
    puts("sparse native image test passed");
    return 0;
}
