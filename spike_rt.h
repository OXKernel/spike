#ifndef SPIKE_RT_H
#define SPIKE_RT_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <setjmp.h>

#if defined(__STDC_NO_ATOMICS__) || defined(_BAREMETAL)
    #define ATOMIC_INC(ptr) __sync_add_and_fetch(ptr, 1)
    #define ATOMIC_DEC(ptr) __sync_sub_and_fetch(ptr, 1)
    #define ATOMIC_INT int32_t
#else
    #include <stdatomic.h>
    #define ATOMIC_INC(ptr) (atomic_fetch_add(ptr, 1) + 1)
    #define ATOMIC_DEC(ptr) (atomic_fetch_sub(ptr, 1) - 1)
    #define ATOMIC_INT atomic_int
#endif

#if defined(_MSC_VER)
    #define SPIKE_TLS __declspec(thread)
#else
    #define SPIKE_TLS _Thread_local
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* -------------------------------------------------------------------------
 * Core Object & Polymorphic ABI Layout
 * ------------------------------------------------------------------------- */
typedef struct Object {
    ATOMIC_INT __refcount;
    uint8_t __managed_flag;    /* 1 = ARC managed, 0 = manual/static/disowned */
    uint32_t __type_id;
    void* __vtable;
} Object;

typedef struct Object_VTable {
    struct String* (*to_string)(Object* self);
    bool (*equals)(Object* self, Object* other);
    void (*destructor)(Object* self);
} Object_VTable;

/* -------------------------------------------------------------------------
 * Slice Fat-Pointer
 * ------------------------------------------------------------------------- */
typedef struct Slice {
    void* data;
    size_t length;
    size_t elem_size;
} Slice;

/* -------------------------------------------------------------------------
 * Thread-Local Exception Hierarchy
 * ------------------------------------------------------------------------- */
typedef struct __SpikeExceptionFrame {
    jmp_buf jmp;
    struct __SpikeExceptionFrame* prev;
    Object* active_exception;
} __SpikeExceptionFrame;

extern SPIKE_TLS __SpikeExceptionFrame* __spike_current_exc_frame;

static inline void __spike_push_exc_frame(__SpikeExceptionFrame* frame) {
    frame->active_exception = NULL;
    frame->prev = __spike_current_exc_frame;
    __spike_current_exc_frame = frame;
}

static inline void __spike_pop_exc_frame(void) {
    if (__spike_current_exc_frame) {
        __spike_current_exc_frame = __spike_current_exc_frame->prev;
    }
}

static inline void __spike_raise(Object* exc) {
    if (!__spike_current_exc_frame) {
        fprintf(stderr, "[Spike Fatal Panic] Unhandled Exception\n");
        abort();
    }
    __spike_current_exc_frame->active_exception = exc;
    longjmp(__spike_current_exc_frame->jmp, 1);
}

/* -------------------------------------------------------------------------
 * Bounds Checking Runtime Guard
 * ------------------------------------------------------------------------- */
static inline void* __spike_bounds_check(void* base, size_t index, size_t length, size_t elem_size) {
    if (index >= length) {
        fprintf(stderr, "[Spike Bounds Panic] Index out of range: %zu >= %zu\n", index, length);
        abort();
    }
    return (void*)((uintptr_t)base + (index * elem_size));
}

static inline Slice __spike_slice_create(void* base, size_t start, size_t end, size_t orig_len, size_t elem_size) {
    if (start > end || end > orig_len) {
        fprintf(stderr, "[Spike Slice Panic] Invalid bounds: [%zu:%zu] on length %zu\n", start, end, orig_len);
        abort();
    }
    Slice s;
    s.data = (void*)((uintptr_t)base + (start * elem_size));
    s.length = end - start;
    s.elem_size = elem_size;
    return s;
}

/* -------------------------------------------------------------------------
 * Built-in Managed Collections
 * ------------------------------------------------------------------------- */
typedef struct BoxedInt { Object __hdr; int64_t value; } BoxedInt;
typedef struct String { Object __hdr; size_t length; size_t capacity; char* data; } String;
typedef struct List { Object __hdr; size_t length; size_t capacity; Object** items; } List;
typedef struct Closure { Object __hdr; void* function_ptr; void* env_ctx; void (*env_destructor)(void*); } Closure;

/* -------------------------------------------------------------------------
 * Memory & Collection Lifecycle APIs
 * ------------------------------------------------------------------------- */
void* spike_alloc(size_t size, void* vtable);
void spike_retain(void* ptr);
void spike_release(void* ptr);
void spike_disown(void* ptr);
void spike_own(void* ptr);

BoxedInt* spike_box_int(int64_t val);
int64_t spike_unbox_int(Object* obj);
String* spike_string_new(const char* cstr);
List* spike_list_new(size_t initial_cap);
void spike_list_append(List* list, Object* item);
Object* spike_list_get(List* list, size_t index);
Closure* spike_closure_new(void* fn_ptr, void* env_ctx, void (*env_destructor)(void*));

#ifdef __cplusplus
}
#endif

#endif /* SPIKE_RT_H */
