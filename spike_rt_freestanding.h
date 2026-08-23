/* ================= SPIKE FREESTANDING RUNTIME ================= */
#define _BAREMETAL 1
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Minimal freestanding memory stubs & built-in abort */
static inline void abort(void) {
    __asm__ __volatile__("cli; hlt");
    while (1) {}
}

/* Static bump allocator for kernel-mode class allocations */
static uint8_t __k_heap[65536];
static size_t __k_heap_idx = 0;

static inline void* spike_alloc(size_t size, void* vtable) {
    size_t aligned_sz = (size + 7) & ~7;
    if (__k_heap_idx + aligned_sz > sizeof(__k_heap)) abort();
    void* ptr = &__k_heap[__k_heap_idx];
    __k_heap_idx += aligned_sz;
    return ptr;
}

static inline void spike_retain(void* ptr) { (void)ptr; }
static inline void spike_release(void* ptr) { (void)ptr; }
