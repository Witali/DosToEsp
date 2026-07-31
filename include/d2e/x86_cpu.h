#ifndef D2E_X86_CPU_H
#define D2E_X86_CPU_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define D2E_X86_MEMORY_SIZE (UINT32_C(1) << 20)
#define D2E_X86_ADDRESS_MASK (D2E_X86_MEMORY_SIZE - UINT32_C(1))
#define D2E_X86_PAGE_SHIFT 8U
#define D2E_X86_PAGE_SIZE (UINT32_C(1) << D2E_X86_PAGE_SHIFT)
#define D2E_X86_PAGE_COUNT (D2E_X86_MEMORY_SIZE / D2E_X86_PAGE_SIZE)

typedef enum d2e_x86_reg16 {
    D2E_X86_AX = 0,
    D2E_X86_CX,
    D2E_X86_DX,
    D2E_X86_BX,
    D2E_X86_SP,
    D2E_X86_BP,
    D2E_X86_SI,
    D2E_X86_DI,
    D2E_X86_REG16_COUNT
} d2e_x86_reg16;

typedef enum d2e_x86_segment {
    D2E_X86_ES = 0,
    D2E_X86_CS,
    D2E_X86_SS,
    D2E_X86_DS,
    D2E_X86_SEGMENT_COUNT
} d2e_x86_segment;

enum {
    D2E_X86_FLAG_CF = 1U << 0,
    D2E_X86_FLAG_FIXED = 1U << 1,
    D2E_X86_FLAG_PF = 1U << 2,
    D2E_X86_FLAG_AF = 1U << 4,
    D2E_X86_FLAG_ZF = 1U << 6,
    D2E_X86_FLAG_SF = 1U << 7,
    D2E_X86_FLAG_TF = 1U << 8,
    D2E_X86_FLAG_IF = 1U << 9,
    D2E_X86_FLAG_DF = 1U << 10,
    D2E_X86_FLAG_OF = 1U << 11
};

typedef enum d2e_x86_stop_reason {
    D2E_X86_RUNNING = 0,
    D2E_X86_EXITED,
    D2E_X86_UNTRANSLATED_TARGET,
    D2E_X86_CODE_MODIFIED,
    D2E_X86_UNMAPPED_MEMORY,
    D2E_X86_DIVIDE_ERROR,
    D2E_X86_UNHANDLED_INTERRUPT,
    D2E_X86_UNHANDLED_PORT,
    D2E_X86_BUDGET_EXHAUSTED,
    D2E_X86_WAITING_INPUT
} d2e_x86_stop_reason;

typedef int (*d2e_x86_port_in8_fn)(void *context, uint16_t port,
                                   uint8_t *value);
typedef int (*d2e_x86_port_out8_fn)(void *context, uint16_t port,
                                    uint8_t value);
struct d2e_x86_cpu;
typedef int (*d2e_x86_interrupt_fn)(void *context,
                                    struct d2e_x86_cpu *cpu,
                                    uint8_t interrupt_number);

typedef struct d2e_x86_cpu {
    uint16_t regs[D2E_X86_REG16_COUNT];
    uint16_t segments[D2E_X86_SEGMENT_COUNT];
    uint16_t ip;
    uint16_t flags;
    uint8_t *memory;
    size_t memory_size;
    uint8_t *cga_vram;
    uint32_t *page_generations;
    void *port_context;
    d2e_x86_port_in8_fn port_in8;
    d2e_x86_port_out8_fn port_out8;
    void *interrupt_context;
    d2e_x86_interrupt_fn interrupt;
    d2e_x86_stop_reason stop_reason;
    uint16_t fault_cs;
    uint16_t fault_ip;
    uint32_t fault_address;
    uint8_t exit_code;
    uint64_t instructions_retired;
} d2e_x86_cpu;

void d2e_x86_cpu_init(d2e_x86_cpu *cpu, uint8_t *memory, size_t memory_size,
                      uint32_t *page_generations);
void d2e_x86_cpu_reset(d2e_x86_cpu *cpu);
void d2e_x86_map_cga_vram(d2e_x86_cpu *cpu, uint8_t *cga_vram);
void d2e_x86_configure_ports(d2e_x86_cpu *cpu, void *context,
                             d2e_x86_port_in8_fn input,
                             d2e_x86_port_out8_fn output);
void d2e_x86_configure_interrupts(d2e_x86_cpu *cpu, void *context,
                                  d2e_x86_interrupt_fn interrupt);
uint8_t d2e_x86_port_in8(d2e_x86_cpu *cpu, uint16_t port);
void d2e_x86_port_out8(d2e_x86_cpu *cpu, uint16_t port, uint8_t value);

uint8_t d2e_x86_get_reg8(const d2e_x86_cpu *cpu, unsigned encoded_reg);
void d2e_x86_set_reg8(d2e_x86_cpu *cpu, unsigned encoded_reg, uint8_t value);

uint32_t d2e_x86_linear(uint16_t segment, uint16_t offset);
uint8_t d2e_x86_read8(const d2e_x86_cpu *cpu, uint32_t address);
uint16_t d2e_x86_read16(const d2e_x86_cpu *cpu, uint32_t address);
void d2e_x86_write8(d2e_x86_cpu *cpu, uint32_t address, uint8_t value);
void d2e_x86_write16(d2e_x86_cpu *cpu, uint32_t address, uint16_t value);
uint16_t d2e_x86_read16_seg(const d2e_x86_cpu *cpu, uint16_t segment,
                            uint16_t offset);
void d2e_x86_write16_seg(d2e_x86_cpu *cpu, uint16_t segment, uint16_t offset,
                         uint16_t value);

uint8_t d2e_x86_fetch8(const d2e_x86_cpu *cpu, uint16_t relative_ip);
uint16_t d2e_x86_fetch16(const d2e_x86_cpu *cpu, uint16_t relative_ip);

void d2e_x86_push16(d2e_x86_cpu *cpu, uint16_t value);
uint16_t d2e_x86_pop16(d2e_x86_cpu *cpu);

#ifdef __cplusplus
}
#endif

#endif
