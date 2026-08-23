#!/usr/bin/env python3
import re
import sys
from pathlib import Path

TYPE_MAP = {
    "int": "int",
    "long": "int",
    "long long": "int",
    "short": "i16",
    "char": "u8",
    "unsigned int": "u32",
    "unsigned long": "u64",
    "unsigned long long": "u64",
    "unsigned short": "u16",
    "unsigned char": "u8",
    "uint8_t": "u8",
    "uint16_t": "u16",
    "uint32_t": "u32",
    "uint64_t": "u64",
    "int8_t": "i8",
    "int16_t": "i16",
    "int32_t": "i32",
    "int64_t": "int",
    "size_t": "usize",
    "uintptr_t": "usize",
    "float": "float",
    "double": "float",
    "bool": "bool",
    "void": "void"
}

class CToSpikeTranspiler:
    def __init__(self, c_code: str, module_class_name: str = "CFileSystem"):
        self.c_code = c_code
        self.module_class_name = module_class_name

    def map_type(self, c_type_str: str) -> str:
        c_type_str = c_type_str.strip()
        pointer_depth = c_type_str.count("*")
        clean_t = c_type_str.replace("*", "").strip()
        clean_t = re.sub(r"\bstruct\b", "", clean_t).strip()
        clean_t = re.sub(r"\bconst\b", "", clean_t).strip()

        mapped = TYPE_MAP.get(clean_t, clean_t)
        return ("*" * pointer_depth) + mapped

    def transpile(self) -> str:
        out = []
        # Strip C comments
        clean_c = re.sub(r"/\*.*?\*/", "", self.c_code, flags=re.DOTALL)
        clean_c = re.sub(r"//.*", "", clean_c)

        # 1. Extract Structs -> Pure Data Spike Structs
        struct_pattern = re.compile(r"struct\s+([A-Za-z0-9_]+)\s*\{([^}]+)\};", re.DOTALL)
        for match in struct_pattern.finditer(clean_c):
            s_name = match.group(1)
            body = match.group(2)
            out.append(f"struct {s_name} {{")
            for line in body.split(";"):
                line = line.strip()
                if not line: continue
                # Handle arrays: type name[size]
                arr_match = re.search(r"([A-Za-z0-9_\s\*]+)\s+([A-Za-z0-9_]+)\[([0-9]+)\]", line)
                if arr_match:
                    ftype = self.map_type(arr_match.group(1))
                    fname = arr_match.group(2)
                    sz = arr_match.group(3)
                    out.append(f"    {fname}: [{ftype}; {sz}]")
                else:
                    parts = line.rsplit(maxsplit=1)
                    if len(parts) == 2:
                        ftype = self.map_type(parts[0])
                        fname = parts[1]
                        out.append(f"    {fname}: {ftype}")
            out.append("}\n")

        # 2. Extract Functions -> Static Methods in Class
        out.append(f"class {self.module_class_name} {{")
        
        fn_pattern = re.compile(r"([A-Za-z0-9_\*\s]+)\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*\{([^}]+)\}", re.DOTALL)
        for match in fn_pattern.finditer(clean_c):
            ret_type = self.map_type(match.group(1))
            fn_name = match.group(2)
            params_raw = match.group(3).strip()
            body = match.group(4)

            # Skip struct definitions caught by pattern
            if fn_name == "struct": continue

            spike_params = []
            if params_raw and params_raw != "void":
                for p in params_raw.split(","):
                    p = p.strip()
                    if not p: continue
                    parts = p.rsplit(maxsplit=1)
                    if len(parts) == 2:
                        ptype = self.map_type(parts[0])
                        pname = parts[1]
                        spike_params.append(f"{pname}: {ptype}")

            params_str = ", ".join(spike_params)
            out.append(f"    static def {fn_name}({params_str}): {ret_type} {{")
            
            # Translate Body Statements
            for b_line in body.split(";"):
                b_line = b_line.strip()
                if not b_line: continue
                
                # Pointer assignment / dereference translation
                b_line = re.sub(r"->", ".", b_line)
                
                # Convert C variable declarations: 'int x = 5' -> 'x: int = 5'
                decl_match = re.match(r"^([A-Za-z0-9_\*]+)\s+([A-Za-z0-9_]+)\s*=\s*(.*)", b_line)
                if decl_match:
                    t = self.map_type(decl_match.group(1))
                    v = decl_match.group(2)
                    init = decl_match.group(3)
                    out.append(f"        {v}: {t} = {init}")
                elif b_line.startswith("return "):
                    out.append(f"        {b_line}")
                else:
                    out.append(f"        {b_line}")

            out.append("    }\n")

        out.append("}")
        return "\n".join(out)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 c2spike.py <source.c> [OutputClass]")
        sys.exit(1)

    c_file = sys.argv[1]
    cls_name = sys.argv[2] if len(sys.argv) > 2 else Path(c_file).stem.capitalize()
    
    with open(c_file, "r", encoding="utf-8") as f:
        content = f.read()

    transpiler = CToSpikeTranspiler(content, module_class_name=cls_name)
    spike_code = transpiler.transpile()

    out_file = Path(c_file).with_suffix(".spike")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(spike_code)

    print(f"[✓] Converted '{c_file}' -> '{out_file}' (Encapsulated in class '{cls_name}')")
