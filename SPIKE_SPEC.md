# The Spike Programming Language: Specification & Reference Manual

## 0. Designed by Roger Doss, PhD

## 1. Core Paradigm & Invariants
* **Pure Object-Oriented Architecture:** Standalone functions are strictly forbidden. All executable logic resides as instance or static methods inside a `class`.
* **Pure Data Structs (`struct`):** Structs are strictly zero-overhead, stack-allocated plain-old-data (POD) aggregates. Structs cannot contain methods, virtual tables, or inheritance.
* **No `let` Keyword:** Variable declarations strictly use colon-based mandatory type annotations (`name: Type = value` or `(a: Type, b: Type) = expr`).
* **Deterministic ARC + Ownership Escapes:** Managed `class` instances use thread-safe atomic reference counting. Hardware memory handoffs use `disown` and `own`.
* **Transparent C ABI:** Zero name mangling. Direct, bidirectional integration with assembly and C.

### 1.2 Comments and Docstrings
Spike strictly adheres to Python-style commenting conventions. C-style comments (`/* ... */` and `//`) are not supported.

* **Single-Line Comments:** Indicated by the `#` symbol. Everything following `#` on the same line is ignored by the parser.
* **Multi-Line Comments & Docstrings:** Multi-line descriptions and block comments use triple single-quotes (`'''`) or triple double-quotes (`"""`).

```python
"""
Disk Block Allocator
Manages free list bitmap allocations for raw block storage.
"""

struct Superblock {
    magic: u32 # Filesystem magic header (0xEF53)
    block_size: u32
}

---

## 2. Syntax Overview

### A. Pure Data Structs vs. Classes
```python
# Pure-data value struct (Stack-allocated, 0 bytes vtable overhead)
struct Inode {
    inode_num: u32
    size_bytes: u32
    flags: u16
    direct_blocks: [u32; 12]
}

# Behavioral Entity
class FileSystem {
    root_inode: u32

    def FileSystem(root: u32 = 1) {
        self.root_inode = root
    }

    def read_block(self, node: Inode, block_idx: int): [u8] {
        # Slice & bounds-checked read
        block_id: u32 = node.direct_blocks[block_idx]
        return StorageDriver.read_sector(block_id)
    }
}

## 3. Example spike_driver.py usage

### Emit C code
python3 spike_driver.py kernel.spike --emit-c

### User space build
python3 spike_driver.py app.spike --mode host -o myapp
./myapp

### Bare metal build
python3 spike_driver.py kernel.spike --mode kernel --format elf -o kernel.elf

### Run bare metal ELF kernel
qemu-system-x86_64 -kernel kernel.elf

### Bare metal binary (.bin)
python3 spike_driver.py kernel.spike --mode kernel --format bin -o kernel.bin

## 4. C. Integration

# 4.1 Declare external C functions and global variables
extern def memset(dest: *u8, val: u8, count: u64): *u8
extern def fs_mount(disk_id: u32, mount_point: *u8): i32
extern def uart_putc(c: u8): none

class Kernel {
    def init() {
        # Call the existing C function naturally
        buffer: *u8 = 0x100000 as *u8
        memset(buffer, 0, 4096)

        status: i32 = fs_mount(0, "/mnt" as *u8)
    }
}

# This generates:
/* Forward declarations from Spike 'extern' */
extern uint8_t* memset(uint8_t* dest, uint8_t val, uint64_t count);
extern int32_t fs_mount(uint32_t disk_id, uint8_t* mount_point);
extern void uart_putc(uint8_t c);

void Kernel_init(void) {
    uint8_t* buffer = ((uint8_t*)(0x100000));
    memset(buffer, 0, 4096);
    int32_t status = fs_mount(0, ((uint8_t*)("/mnt")));
}

# 4.2 Top-level: include existing C headers
c_decl {
    '#include "fat_fs.h"'
    '#include "rtl8139.h"'
}

class Storage {
    def read_block(lba: u32) {
        # Inline C block executing arbitrary C logic
        c_inline {
            "fat_read_sector(lba);"
        }
    }
}

# 4.3.1 Compile your existing legacy C code with GCC / Clang
gcc -m64 -ffreestanding -c legacy_fat_fs.c -o build/legacy_fat_fs.o

# 4.3.2. Compile your Spike source to an object file
python3 spike_driver.py kernel.spike -k -c -o build/kernel_spike.o

# 4.3.3. Link them together
ld -m elf_i386 -nostdlib -T linker.ld \
   build/boot64.o build/legacy_fat_fs.o build/kernel_spike.o \
   -o build/kernel.elf

Use extern def when calling existing C libraries, drivers, or standard libc functions 
(memset, memcpy, filesystem routines). It keeps the Spike codebase clean, strongly typed, and readable.

Use c_decl / c_inline when you need #include directives for complex C macro definitions or small glue snippets.

