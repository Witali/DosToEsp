#include "d2e/supervisor.h"

#include <string.h>

void d2e_supervisor_init(d2e_supervisor *supervisor, d2e_x86_cpu *cpu) {
    memset(supervisor, 0, sizeof(*supervisor));
    supervisor->cpu = cpu;
    supervisor->state = D2E_SUPERVISOR_IDLE;
    supervisor->last_stop_reason = D2E_X86_RUNNING;
}

int d2e_supervisor_launch(d2e_supervisor *supervisor,
                          const d2e_package *package) {
    if (supervisor == NULL || supervisor->cpu == NULL ||
        supervisor->state != D2E_SUPERVISOR_IDLE ||
        !d2e_package_validate(package)) {
        return 0;
    }
    d2e_x86_clear_memory(supervisor->cpu);
    supervisor->package = package;
    supervisor->exit_code = 0U;
    if (!d2e_native_load(supervisor->cpu, package->program)) {
        supervisor->last_stop_reason = supervisor->cpu->stop_reason;
        supervisor->state = D2E_SUPERVISOR_FAULTED;
        return 0;
    }
    supervisor->last_stop_reason = D2E_X86_RUNNING;
    supervisor->state = D2E_SUPERVISOR_ACTIVE;
    return 1;
}

d2e_supervisor_state d2e_supervisor_step(d2e_supervisor *supervisor,
                                         uint32_t block_budget) {
    d2e_x86_stop_reason reason;
    if (supervisor == NULL || supervisor->state != D2E_SUPERVISOR_ACTIVE ||
        supervisor->package == NULL || block_budget == 0U) {
        return supervisor != NULL ? supervisor->state
                                  : D2E_SUPERVISOR_FAULTED;
    }
    reason = d2e_native_run(supervisor->cpu, supervisor->package->program,
                            block_budget);
    supervisor->last_stop_reason = reason;
    if (reason == D2E_X86_BUDGET_EXHAUSTED ||
        reason == D2E_X86_WAITING_INPUT) {
        return supervisor->state;
    }
    if (reason == D2E_X86_EXITED) {
        supervisor->exit_code = supervisor->cpu->exit_code;
        supervisor->state = D2E_SUPERVISOR_EXITED;
    } else {
        supervisor->state = D2E_SUPERVISOR_FAULTED;
    }
    return supervisor->state;
}

void d2e_supervisor_return_to_shell(d2e_supervisor *supervisor) {
    if (supervisor == NULL || supervisor->cpu == NULL) {
        return;
    }
    d2e_x86_clear_memory(supervisor->cpu);
    d2e_x86_cpu_reset(supervisor->cpu);
    supervisor->package = NULL;
    supervisor->state = D2E_SUPERVISOR_IDLE;
    supervisor->last_stop_reason = D2E_X86_RUNNING;
    supervisor->exit_code = 0U;
}
