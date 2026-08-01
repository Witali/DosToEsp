#ifndef D2E_SHELL_H
#define D2E_SHELL_H

#include <stddef.h>
#include <stdint.h>

#include "d2e/package.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    D2E_SHELL_COLUMNS = 40,
    D2E_SHELL_ROWS = 25,
    D2E_SHELL_INPUT_CAPACITY = 31,
};

typedef struct d2e_shell {
    const d2e_package *packages;
    size_t package_count;
    char input[D2E_SHELL_INPUT_CAPACITY + 1U];
    size_t input_length;
    char message[D2E_SHELL_COLUMNS + 1U];
    uint8_t dirty;
    uint8_t ignore_line_feed;
} d2e_shell;

void d2e_shell_init(d2e_shell *shell, const d2e_package *packages,
                    size_t package_count);
const d2e_package *d2e_shell_feed(d2e_shell *shell, uint8_t byte);
void d2e_shell_set_message(d2e_shell *shell, const char *message);
void d2e_shell_render(d2e_shell *shell, uint8_t *text_vram,
                      size_t vram_size);

#ifdef __cplusplus
}
#endif

#endif
