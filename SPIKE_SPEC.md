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

