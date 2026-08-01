#ifndef D2E_SUPERVISOR_H
#define D2E_SUPERVISOR_H

#include "d2e/package.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum d2e_supervisor_state {
    D2E_SUPERVISOR_IDLE = 0,
    D2E_SUPERVISOR_ACTIVE,
    D2E_SUPERVISOR_EXITED,
    D2E_SUPERVISOR_FAULTED
} d2e_supervisor_state;

typedef struct d2e_supervisor {
    d2e_x86_cpu *cpu;
    const d2e_package *package;
    d2e_supervisor_state state;
    d2e_x86_stop_reason last_stop_reason;
    uint8_t exit_code;
} d2e_supervisor;

void d2e_supervisor_init(d2e_supervisor *supervisor, d2e_x86_cpu *cpu);
int d2e_supervisor_launch(d2e_supervisor *supervisor,
                          const d2e_package *package);
d2e_supervisor_state d2e_supervisor_step(d2e_supervisor *supervisor,
                                         uint32_t block_budget);
void d2e_supervisor_return_to_shell(d2e_supervisor *supervisor);

#ifdef __cplusplus
}
#endif

#endif
