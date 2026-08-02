#include "d2e/package.h"

#include <ctype.h>
#include <string.h>

static int valid_command(const char *command) {
    size_t length;
    if (command == NULL) {
        return 0;
    }
    length = strlen(command);
    if (length == 0U || length > D2E_PACKAGE_COMMAND_MAX) {
        return 0;
    }
    while (*command != '\0') {
        const unsigned char character = (unsigned char)*command++;
        if (!isalnum(character) && character != '_') {
            return 0;
        }
    }
    return 1;
}

static int command_equal(const char *left, const char *right) {
    while (*left != '\0' && *right != '\0') {
        if (toupper((unsigned char)*left) != toupper((unsigned char)*right)) {
            return 0;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

int d2e_package_validate(const d2e_package *package) {
    if (package == NULL || package->abi_version != D2E_PACKAGE_ABI_VERSION ||
        !valid_command(package->command) || package->title == NULL ||
        package->title[0] == '\0' || package->program == NULL) {
        return 0;
    }
    return package->storage == D2E_PACKAGE_BUILTIN_FLASH ||
           package->storage == D2E_PACKAGE_EXTERNAL_MODULE;
}

const d2e_package *d2e_package_find(const d2e_package *packages,
                                    size_t package_count,
                                    const char *command) {
    size_t index;
    if (packages == NULL || command == NULL) {
        return NULL;
    }
    for (index = 0U; index < package_count; ++index) {
        if (d2e_package_validate(&packages[index]) &&
            command_equal(packages[index].command, command)) {
            return &packages[index];
        }
    }
    return NULL;
}
