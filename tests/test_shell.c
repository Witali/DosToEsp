#include "d2e/shell.h"

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

static const uint8_t image[] = {UINT8_C(0)};
static const d2e_native_program program = {
    .name = "shell_test",
    .format = D2E_NATIVE_IMAGE_COM,
    .load_segment = UINT16_C(0x1000),
    .entry_ip = UINT16_C(0x0100),
    .image = image,
    .image_size = sizeof(image),
};
static const d2e_package packages[] = {
    {D2E_PACKAGE_ABI_VERSION, "ALLEY", "Alley Cat",
     D2E_PACKAGE_BUILTIN_FLASH, &program},
};

static const d2e_package *feed_text(d2e_shell *shell, const char *text) {
    const d2e_package *selected = NULL;
    while (*text != '\0') {
        const d2e_package *const next =
            d2e_shell_feed(shell, (uint8_t)*text++);
        if (next != NULL) {
            selected = next;
        }
    }
    return selected;
}

static void test_commands(void) {
    d2e_shell shell;
    d2e_shell_init(&shell, packages, 1U);
    CHECK(feed_text(&shell, "run alley\r\n") == &packages[0]);
    CHECK(shell.input_length == 0U);
    CHECK(feed_text(&shell, "ALLEY\n") == &packages[0]);
    CHECK(feed_text(&shell, "HELP\r") == NULL);
    CHECK(strcmp(shell.message, "Commands: DIR, RUN <name>, HELP") == 0);
    CHECK(feed_text(&shell, "DIR\r") == NULL);
    CHECK(strcmp(shell.message, "1 translated package(s)") == 0);
    CHECK(feed_text(&shell, "RUN MISSING\r") == NULL);
    CHECK(strcmp(shell.message, "Bad command or package name") == 0);
    CHECK(feed_text(&shell, "RUN\r") == NULL);
    CHECK(strcmp(shell.message, "Usage: RUN <name>") == 0);
    CHECK(feed_text(&shell, "ALLEZ\bY\r") == &packages[0]);
}

static void test_render(void) {
    uint8_t vram[D2E_SHELL_COLUMNS * D2E_SHELL_ROWS * 2U];
    d2e_shell shell;
    d2e_shell_init(&shell, packages, 1U);
    CHECK(feed_text(&shell, "RUN ") == NULL);
    d2e_shell_render(&shell, vram, sizeof(vram));
    CHECK(memcmp(vram, "D\x0f" "2\x0f" "E\x0f", 6U) == 0);
    CHECK(vram[(4U * D2E_SHELL_COLUMNS) * 2U] == (uint8_t)'A');
    CHECK(vram[(22U * D2E_SHELL_COLUMNS) * 2U] == (uint8_t)'A');
    CHECK(vram[(22U * D2E_SHELL_COLUMNS + 3U) * 2U] == (uint8_t)'>');
    CHECK(vram[(22U * D2E_SHELL_COLUMNS + 4U) * 2U] == (uint8_t)'R');
    CHECK(shell.dirty == 0U);
}

int main(void) {
    test_commands();
    test_render();
    if (failures != 0U) {
        fprintf(stderr, "%u shell test(s) failed\n", failures);
        return 1;
    }
    puts("D2E shell command tests passed");
    return 0;
}
