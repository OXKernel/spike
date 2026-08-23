#include "spike_rt.h"

SPIKE_TLS __SpikeExceptionFrame* __spike_current_exc_frame = NULL;

void* spike_alloc(size_t size, void* vtable) {
    Object* obj = (Object*)calloc(1, size);
    if (!obj) {
        fprintf(stderr, "[Spike RT Fatal] Out of memory\n");
        exit(1);
    }
#if defined(__STDC_NO_ATOMICS__) || defined(_BAREMETAL)
    obj->__refcount = 1;
#else
    atomic_init(&obj->__refcount, 1);
#endif
    obj->__managed_flag = 1;
    obj->__vtable = vtable;
    return (void*)obj;
}

void spike_retain(void* ptr) {
    if (!ptr) return;
    Object* obj = (Object*)ptr;
    if (obj->__managed_flag) {
        ATOMIC_INC(&obj->__refcount);
    }
}

void spike_release(void* ptr) {
    if (!ptr) return;
    Object* obj = (Object*)ptr;
    if (obj->__managed_flag) {
        if (ATOMIC_DEC(&obj->__refcount) <= 0) {
            if (obj->__vtable) {
                Object_VTable* vt = (Object_VTable*)obj->__vtable;
                if (vt->destructor) vt->destructor(obj);
            }
            free(obj);
        }
    }
}

void spike_disown(void* ptr) {
    if (ptr) ((Object*)ptr)->__managed_flag = 0;
}

void spike_own(void* ptr) {
    if (!ptr) return;
    Object* obj = (Object*)ptr;
    obj->__managed_flag = 1;
#if defined(__STDC_NO_ATOMICS__) || defined(_BAREMETAL)
    obj->__refcount = 1;
#else
    atomic_init(&obj->__refcount, 1);
#endif
}

static void boxed_destructor(Object* obj) { (void)obj; }
static Object_VTable __vt_Boxed = { NULL, NULL, boxed_destructor };

BoxedInt* spike_box_int(int64_t val) {
    BoxedInt* b = (BoxedInt*)spike_alloc(sizeof(BoxedInt), &__vt_Boxed);
    b->value = val;
    return b;
}

int64_t spike_unbox_int(Object* obj) {
    return obj ? ((BoxedInt*)obj)->value : 0;
}

static void string_destructor(Object* obj) {
    String* s = (String*)obj;
    if (s->data) free(s->data);
}
static Object_VTable __vt_String = { NULL, NULL, string_destructor };

String* spike_string_new(const char* cstr) {
    String* s = (String*)spike_alloc(sizeof(String), &__vt_String);
    s->length = cstr ? strlen(cstr) : 0;
    s->capacity = s->length + 1;
    s->data = (char*)malloc(s->capacity);
    if (cstr) strcpy(s->data, cstr);
    else s->data[0] = '\0';
    return s;
}

static void list_destructor(Object* obj) {
    List* l = (List*)obj;
    for (size_t i = 0; i < l->length; i++) spike_release(l->items[i]);
    if (l->items) free(l->items);
}
static Object_VTable __vt_List = { NULL, NULL, list_destructor };

List* spike_list_new(size_t initial_cap) {
    List* l = (List*)spike_alloc(sizeof(List), &__vt_List);
    l->length = 0;
    l->capacity = initial_cap > 4 ? initial_cap : 4;
    l->items = (Object**)calloc(l->capacity, sizeof(Object*));
    return l;
}

void spike_list_append(List* list, Object* item) {
    if (!list) return;
    if (list->length >= list->capacity) {
        list->capacity *= 2;
        list->items = (Object**)realloc(list->items, list->capacity * sizeof(Object*));
    }
    spike_retain(item);
    list->items[list->length++] = item;
}

Object* spike_list_get(List* list, size_t index) {
    if (!list || index >= list->length) {
        fprintf(stderr, "[Spike List Panic] Index out of range: %zu >= %zu\n", index, list ? list->length : 0);
        abort();
    }
    return list->items[index];
}

static void closure_destructor(Object* obj) {
    Closure* c = (Closure*)obj;
    if (c->env_ctx && c->env_destructor) c->env_destructor(c->env_ctx);
}
static Object_VTable __vt_Closure = { NULL, NULL, closure_destructor };

Closure* spike_closure_new(void* fn_ptr, void* env_ctx, void (*env_destructor)(void*)) {
    Closure* c = (Closure*)spike_alloc(sizeof(Closure), &__vt_Closure);
    c->function_ptr = fn_ptr;
    c->env_ctx = env_ctx;
    c->env_destructor = env_destructor;
    return c;
}
