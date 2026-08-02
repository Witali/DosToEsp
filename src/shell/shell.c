#include "d2e/shell.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

enum {
    k_default_attribute = 0x07,
    k_heading_attribute = 0x0f,
    k_package_attribute = 0x0b,
    k_prompt_attribute = 0x0a,
};

static void write_text(uint8_t *vram, size_t vram_size, unsigned row,
                       unsigned column, const char *text, uint8_t attribute) {
    while (*text != '\0' && column < D2E_SHELL_COLUMNS) {
        const size_t offset =
            ((size_t)row * D2E_SHELL_COLUMNS + column) * 2U;
        if (offset + 1U >= vram_size) {
            return;
        }
        vram[offset] = (uint8_t)*text++;
        vram[offset + 1U] = attribute;
        ++column;
    }
}

static char *trim(char *text) {
    char *end;
    while (isspace((unsigned char)*text)) {
        ++text;
    }
    end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1])) {
        --end;
    }
    *end = '\0';
    return text;
}

static uint8_t drive_bit(char drive) {
    const unsigned char upper =
        (unsigned char)toupper((unsigned char)drive);
    if (upper < (unsigned char)'A' || upper > (unsigned char)'H') {
        return 0U;
    }
    return (uint8_t)(1U << (upper - (unsigned char)'A'));
}

static int drive_available(const d2e_shell *shell, char drive) {
    const uint8_t bit = drive_bit(drive);
    return bit != 0U && (shell->drive_mask & bit) != 0U;
}

static const d2e_package *execute_line(d2e_shell *shell) {
    char command[D2E_SHELL_INPUT_CAPACITY + 1U];
    char *argument;
    char *text;
    const d2e_package *package;
    size_t index;

    memcpy(command, shell->input, shell->input_length + 1U);
    text = trim(command);
    for (index = 0U; text[index] != '\0'; ++index) {
        text[index] = (char)toupper((unsigned char)text[index]);
    }
    if (*text == '\0') {
        d2e_shell_set_message(shell, "");
        return NULL;
    }
    argument = strchr(text, ' ');
    if (argument != NULL) {
        *argument++ = '\0';
        argument = trim(argument);
    }
    if (text[0] != '\0' && text[1] == ':' && text[2] == '\0' &&
        argument == NULL) {
        if (!drive_available(shell, text[0])) {
            (void)snprintf(shell->message, sizeof(shell->message),
                           "%c: drive not ready", text[0]);
            shell->dirty = 1U;
            return NULL;
        }
        shell->current_drive = text[0];
        (void)snprintf(shell->message, sizeof(shell->message),
                       "Current drive is %c:", shell->current_drive);
        shell->dirty = 1U;
        return NULL;
    }
    if (strcmp(text, "HELP") == 0) {
        d2e_shell_set_message(shell, "DIR  A:  C:  RUN <name>  HELP");
        return NULL;
    }
    if (strcmp(text, "DIR") == 0) {
        (void)snprintf(shell->message, sizeof(shell->message),
                       "%u translated package(s)",
                       (unsigned)shell->package_count);
        shell->dirty = 1U;
        return NULL;
    }
    if (strcmp(text, "RUN") == 0) {
        if (argument == NULL || *argument == '\0') {
            d2e_shell_set_message(shell, "Usage: RUN <name>");
            return NULL;
        }
        package = d2e_package_find(shell->packages, shell->package_count,
                                   argument);
    } else {
        package = d2e_package_find(shell->packages, shell->package_count,
                                   text);
    }
    if (package == NULL) {
        d2e_shell_set_message(shell, "Bad command or package name");
    }
    return package;
}

void d2e_shell_init(d2e_shell *shell, const d2e_package *packages,
                    size_t package_count) {
    memset(shell, 0, sizeof(*shell));
    shell->packages = packages;
    shell->package_count = package_count;
    shell->current_drive = 'A';
    d2e_shell_set_message(shell, "Type HELP for commands");
}

const d2e_package *d2e_shell_feed(d2e_shell *shell, uint8_t byte) {
    const d2e_package *package;
    if (byte == (uint8_t)'\n' && shell->ignore_line_feed != 0U) {
        shell->ignore_line_feed = 0U;
        return NULL;
    }
    shell->ignore_line_feed = 0U;
    if (byte == (uint8_t)'\r' || byte == (uint8_t)'\n') {
        shell->ignore_line_feed = byte == (uint8_t)'\r' ? 1U : 0U;
        shell->input[shell->input_length] = '\0';
        package = execute_line(shell);
        shell->input_length = 0U;
        shell->input[0] = '\0';
        shell->dirty = 1U;
        return package;
    }
    if (byte == UINT8_C(8) || byte == UINT8_C(127)) {
        if (shell->input_length != 0U) {
            --shell->input_length;
            shell->input[shell->input_length] = '\0';
            shell->dirty = 1U;
        }
        return NULL;
    }
    if (byte >= UINT8_C(32) && byte <= UINT8_C(126) &&
        shell->input_length < D2E_SHELL_INPUT_CAPACITY) {
        shell->input[shell->input_length++] = (char)byte;
        shell->input[shell->input_length] = '\0';
        shell->dirty = 1U;
    }
    return NULL;
}

void d2e_shell_set_message(d2e_shell *shell, const char *message) {
    (void)snprintf(shell->message, sizeof(shell->message), "%s", message);
    shell->dirty = 1U;
}

void d2e_shell_set_drive_available(d2e_shell *shell, char drive,
                                   int available) {
    const uint8_t bit = drive_bit(drive);
    if (bit == 0U) {
        return;
    }
    if (available) {
        shell->drive_mask = (uint8_t)(shell->drive_mask | bit);
    } else {
        shell->drive_mask = (uint8_t)(shell->drive_mask & (uint8_t)~bit);
    }
    shell->dirty = 1U;
}

void d2e_shell_render(d2e_shell *shell, uint8_t *vram, size_t vram_size) {
    size_t index;
    char package_line[D2E_SHELL_COLUMNS + 1U];
    char prompt[D2E_SHELL_COLUMNS + 1U];
    const size_t cells = vram_size / 2U;

    for (index = 0U; index < cells; ++index) {
        vram[index * 2U] = (uint8_t)' ';
        vram[index * 2U + 1U] = k_default_attribute;
    }
    write_text(vram, vram_size, 0U, 0U, "D2E DOS 0.1", k_heading_attribute);
    write_text(vram, vram_size, 1U, 0U,
               "Ahead-of-time translated programs", k_default_attribute);
    write_text(vram, vram_size, 2U, 0U, "A: LittleFS",
               drive_available(shell, 'A') ? k_package_attribute
                                           : k_default_attribute);
    write_text(vram, vram_size, 2U, 16U, "C: SD card",
               drive_available(shell, 'C') ? k_package_attribute
                                           : k_default_attribute);
    write_text(vram, vram_size, 3U, 0U, "Resident programs:",
               k_heading_attribute);
    for (index = 0U; index < shell->package_count && index < 14U; ++index) {
        (void)snprintf(package_line, sizeof(package_line), "%-8s %s",
                       shell->packages[index].command,
                       shell->packages[index].title);
        write_text(vram, vram_size, (unsigned)(4U + index), 0U,
                   package_line, k_package_attribute);
    }
    write_text(vram, vram_size, 20U, 0U, shell->message,
               k_default_attribute);
    (void)snprintf(prompt, sizeof(prompt), "%c:\\>%s",
                   shell->current_drive, shell->input);
    write_text(vram, vram_size, 22U, 0U, prompt, k_prompt_attribute);
    shell->dirty = 0U;
}
