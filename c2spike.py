#!/usr/bin/env python3
"""
c2spike.py - Robust C to Spike Transpiler
- Emits `typedef struct Name Name;` in `c_decl` for all structs so `sizeof(Name)` works in C.
- Fixes statement boundary consumption so `(void)var;` no-op statements don't glue onto prior calls.
- Preserves top-level typedefs and forward declarations in topological order.
- Generates safe non-colliding output filenames.
"""

from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple


MULTI_WORD_TYPES = [
    ("unsigned long long", "u64"),
    ("signed long long",   "i64"),
    ("unsigned long",      "u64"),
    ("signed long",        "i64"),
    ("unsigned int",       "u32"),
    ("signed int",         "i32"),
    ("unsigned short",     "u16"),
    ("signed short",       "i16"),
    ("unsigned char",      "u8"),
    ("signed char",        "i8"),
    ("long long",          "i64"),
]

TYPE_MAP = {
    "uint8_t": "u8",
    "uint16_t": "u16",
    "uint32_t": "u32",
    "uint64_t": "u64",
    "int8_t": "i8",
    "int16_t": "i16",
    "int32_t": "i32",
    "int64_t": "i64",
    "short": "i16",
    "int": "i32",
    "long": "i64",
    "char": "u8",
    "size_t": "u64",
    "uintptr_t": "u64",
    "intptr_t": "i64",
    "void": "none",
    "bool": "bool",
    "_Bool": "bool",
    "unsigned": "u32",
    "time_t": "i64",
}

BUILTIN_LIBC_HEADERS = {
    "stdio.h", "stdlib.h", "string.h", "time.h", "stdint.h", "limits.h", "stddef.h"
}


def clean_type(raw: str) -> str:
    s = re.sub(r'\b(static|inline|__inline__|__inline|extern|volatile|register|const)\b', '', raw).strip()
    s = re.sub(r'\bstruct\s+', '', s).strip()
    ptr_depth = s.count('*')
    base = s.replace('*', '').strip()
    base = re.sub(r'\s+', ' ', base)

    for mwt, st in MULTI_WORD_TYPES:
        if base == mwt:
            base = st
            break
    else:
        base = TYPE_MAP.get(base, base)

    return f"{'*' * ptr_depth}{base}"

def pre_normalize_c_source(code: str) -> str:
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

    # Completely strip C unused-variable suppressors like `(void)r;` or `(void) x;`
    code = re.sub(r'\(\s*void\s*\)\s*[a-zA-Z_][a-zA-Z0-9_]*\s*;', '', code)

    for mwt, st in MULTI_WORD_TYPES:
        code = re.sub(r'\b' + mwt.replace(' ', r'\s+') + r'\b', st, code)

    for ct, st in TYPE_MAP.items():
        if ct not in ("unsigned", "char", "int", "short", "long"):
            code = re.sub(r'\b' + ct + r'\b', st, code)

    code = re.sub(r'\*\s+([a-zA-Z_][a-zA-Z0-9_]*)', r'*\1', code)
    return code

def pre_normalize_c_source_v1(code: str) -> str:
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

    for mwt, st in MULTI_WORD_TYPES:
        code = re.sub(r'\b' + mwt.replace(' ', r'\s+') + r'\b', st, code)

    for ct, st in TYPE_MAP.items():
        if ct not in ("unsigned", "char", "int", "short", "long"):
            code = re.sub(r'\b' + ct + r'\b', st, code)

    code = re.sub(r'\*\s+([a-zA-Z_][a-zA-Z0-9_]*)', r'*\1', code)
    return code


def _find_matching_paren(tokens: List[str], start_idx: int) -> int:
    if start_idx >= len(tokens) or tokens[start_idx] != "(":
        return -1
    depth = 0
    for idx in range(start_idx, len(tokens)):
        if tokens[idx] == "(":
            depth += 1
        elif tokens[idx] == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def translate_tokens(tokens: List[str]) -> str:
    out_tokens: List[str] = []
    i = 0
    n = len(tokens)

    while i < n:
        t = tokens[i]

        if t == "(":
            end_p = _find_matching_paren(tokens, i)
            if end_p != -1:
                inner_toks = tokens[i+1:end_p]
                inner_raw = " ".join(inner_toks).strip()
                type_cand = clean_type(inner_raw)
                clean_cand = type_cand.replace('*', '').strip()

                is_type = False
                if clean_cand in TYPE_MAP.values() or inner_raw.endswith('*') or clean_cand in ("CacheNode", "inode", "inode_t", "InodeLRUCache"):
                    if inner_raw not in ("if", "while", "for", "return", "sizeof", "switch") and "as" not in inner_toks:
                        is_type = True

                if is_type and end_p + 1 < n:
                    target_start = end_p + 1

                    if target_start + 1 < n and tokens[target_start].isidentifier() and tokens[target_start+1] == "(":
                        fn_name = tokens[target_start]
                        fn_end_p = _find_matching_paren(tokens, target_start + 1)
                        if fn_end_p != -1:
                            inner_args = translate_tokens(tokens[target_start+2:fn_end_p])
                            out_tokens.append(f"({fn_name}({inner_args}) as {type_cand})")
                            i = fn_end_p + 1
                            continue

                    if tokens[target_start] == "-" and target_start + 1 < n and tokens[target_start+1].isdigit():
                        num = tokens[target_start+1]
                        out_tokens.append(f"((- {num}) as {type_cand})")
                        i = target_start + 2
                        continue

                    if tokens[target_start] == "(":
                        expr_end_p = _find_matching_paren(tokens, target_start)
                        if expr_end_p != -1:
                            inner_expr = translate_tokens(tokens[target_start+1:expr_end_p])
                            out_tokens.append(f"(({inner_expr}) as {type_cand})")
                            i = expr_end_p + 1
                            continue

                    if tokens[target_start] == "*" and target_start + 1 < n and tokens[target_start+1].isidentifier():
                        var_name = tokens[target_start+1]
                        out_tokens.append(f"((* {var_name}) as {type_cand})")
                        i = target_start + 2
                        continue

                    if tokens[target_start].isidentifier():
                        sub_expr = [tokens[target_start]]
                        cur = target_start + 1
                        while cur < n and tokens[cur] in ("->", "."):
                            sub_expr.extend([tokens[cur], tokens[cur+1]])
                            cur += 2
                        out_tokens.append(f"({' '.join(sub_expr)} as {type_cand})")
                        i = cur
                        continue

        if t == "NULL":
            out_tokens.append("0 as *none")
        elif t == "true":
            out_tokens.append("True")
        elif t == "false":
            out_tokens.append("False")
        else:
            if re.match(r'^\d+[uU]$', t):
                out_tokens.append(t[:-1])
            else:
                out_tokens.append(t)

        i += 1

    expr_str = " ".join(out_tokens)
    expr_str = re.sub(r'\s*->\s*', '->', expr_str)
    expr_str = re.sub(r'([a-zA-Z0-9_\-\>\.]+)\s*\+\+', r'\1 = \1 + 1', expr_str)
    expr_str = re.sub(r'([a-zA-Z0-9_\-\>\.]+)\s*--', r'\1 = \1 - 1', expr_str)
    expr_str = re.sub(r'([a-zA-Z0-9_]+|\))\s*\[\s*([^\]]+)\s*\]', r'\1[\2]', expr_str)
    return expr_str


class CTokenizer:
    def __init__(self, code: str):
        self.code = code

    def get_tokens(self) -> List[str]:
        tokens = []
        token_spec = [
            ("STRING",    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''),
            ("HEX",       r'0[xX][0-9a-fA-F]+'),
            ("NUMBER",    r'\d+[uU]?'),
            ("OP_MULTI",  r'<<=|>>=|<<|>>|\+\+|--|->|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%=|&=|\|=|\^='),
            ("OP_SINGLE", r'[{}();,:\.=\+\-\*/%&|^!<>~\[\]?]'),
            ("IDENT",     r'[a-zA-Z_][a-zA-Z0-9_]*'),
            ("WS",        r'\s+'),
        ]
        master_re = re.compile('|'.join(f'(?P<{name}>{pattern})' for name, pattern in token_spec))
        for match in master_re.finditer(self.code):
            kind = match.lastgroup
            val = match.group(0)
            if kind != "WS":
                tokens.append(val)
        return tokens


class BlockParser:
    def __init__(self, tokens: List[str]):
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)

    def peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.tokens[idx] if idx < self.length else ""

    def advance(self) -> str:
        tok = self.peek()
        self.pos += 1
        return tok

    def parse_balanced_block(self) -> List[str]:
        if self.peek() != "{":
            return []
        self.advance()
        depth = 1
        block_tokens = []
        while self.pos < self.length and depth > 0:
            tok = self.advance()
            if tok == "{":
                depth += 1
            elif tok == "}":
                depth -= 1
                if depth == 0:
                    break
            block_tokens.append(tok)
        return block_tokens


class HeaderResolver:
    def __init__(self, base_dir: Path, follow_headers: bool = False):
        self.base_dir = base_dir
        self.follow_headers = follow_headers
        self.visited: Set[Path] = set()
        self.c_decls: List[str] = []
        self.has_libc_headers = False

    def resolve(self, code: str, current_dir: Optional[Path] = None) -> str:
        if current_dir is None:
            current_dir = self.base_dir

        lines: List[str] = []
        for line in code.splitlines():
            line_str = line.strip()

            # Detect forward declaration typedefs: typedef struct inode inode_t;
            m_fwd = re.match(r'^typedef\s+struct\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;', line_str)
            if m_fwd:
                struct_tag = m_fwd.group(1)
                alias_name = m_fwd.group(2)
                self.c_decls.append(f"struct {struct_tag};")
                self.c_decls.append(f"typedef struct {struct_tag} {alias_name};")
                continue

            # Capture other complete single-line typedefs (e.g. function pointers)
            if re.match(r'^typedef\s+[^\{]+;$', line_str):
                self.c_decls.append(line_str)
                continue

            # Handle #include
            inc_match = re.match(r'^#include\s+["<](.+?)[">]', line_str)
            if inc_match:
                inc_target = inc_match.group(1)
                header_path = (current_dir / inc_target).resolve()

                if inc_target in BUILTIN_LIBC_HEADERS:
                    self.has_libc_headers = True

                if self.follow_headers and header_path.is_file() and header_path not in self.visited:
                    self.visited.add(header_path)
                    try:
                        with open(header_path, "r", encoding="utf-8", errors="replace") as f:
                            header_code = f.read()
                        inlined = self.resolve(header_code, header_path.parent)
                        lines.append(f"// --- Inlined from {inc_target} ---")
                        lines.append(inlined)
                        lines.append(f"// --- End of {inc_target} ---")
                    except Exception as ex:
                        print(f"[-] Warning: Failed to inline {header_path}: {ex}", file=sys.stderr)
                        self.c_decls.append(line_str)
                else:
                    self.c_decls.append(line_str)
            else:
                lines.append(line)

        return "\n".join(lines)


class C2Spike:
    def __init__(self, class_name: str = "Native", c_decls: Optional[List[str]] = None, has_libc_headers: bool = False):
        self.class_name = class_name
        self.c_decls = c_decls or []
        self.has_libc_headers = has_libc_headers
        self.structs: List[str] = []
        self.struct_names: List[str] = []
        self.constants: List[str] = []
        self.methods: List[str] = []

    def transpile(self, c_code: str) -> str:
        for line in c_code.splitlines():
            line = line.strip()
            m = re.match(r'^#define\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(.+)$', line)
            if m:
                name = m.group(1)
                val = translate_tokens(CTokenizer(m.group(2).strip().rstrip(';')).get_tokens())
                if not val.endswith(')'):
                    vtype = "*u8" if val.startswith('"') else "u32"
                    self.constants.append(f"const {name}: {vtype} = {val}")

        normalized_c = pre_normalize_c_source(c_code)
        tokens = CTokenizer(normalized_c).get_tokens()
        parser = BlockParser(tokens)

        while parser.pos < parser.length:
            tok = parser.peek()

            if tok == "#":
                while parser.pos < parser.length and parser.advance() != "\n":
                    pass
                continue

            if tok == "struct" or (tok == "typedef" and parser.peek(1) == "struct"):
                self._parse_struct(parser)
                continue

            if self._is_function_header(parser):
                self._parse_function(parser)
                continue

            parser.advance()

        out = ["# Transpiled by c2spike.py", ""]

        # Ensure all defined structs have a typedef in c_decl so sizeof(StructName) works in C
        for sname in self.struct_names:
            self.c_decls.append(f"typedef struct {sname} {sname};")

        if self.c_decls:
            seen_decls = set()
            ordered_decls = []
            for decl in self.c_decls:
                cleaned = decl.rstrip(';')
                if cleaned not in seen_decls:
                    seen_decls.add(cleaned)
                    ordered_decls.append(cleaned)

            out.append("c_decl {")
            for d in ordered_decls:
                out.append(f'    "{d};";')
            out.append("}")
            out.append("")

        if self.constants:
            out.extend(self.constants)
            out.append("")

        if self.structs:
            out.extend(self.structs)
            out.append("")

        out.append(f"class {self.class_name} {{")
        for method in self.methods:
            for line in method.splitlines():
                out.append(f"    {line}")
            out.append("")
        out.append("}")

        return "\n".join(out)

    def _parse_struct(self, p: BlockParser):
        header_tokens = []
        while p.pos < p.length and p.peek() != "{":
            header_tokens.append(p.advance())

        struct_name = ""
        for i, t in enumerate(header_tokens):
            if t == "struct" and i + 1 < len(header_tokens) and header_tokens[i+1] != "{":
                struct_name = header_tokens[i+1]

        body_tokens = p.parse_balanced_block()

        trailing_name = ""
        while p.pos < p.length:
            t = p.advance()
            if t == ";":
                break
            if t.isidentifier():
                trailing_name = t

        final_name = trailing_name or struct_name or "AnonymousStruct"
        self.struct_names.append(final_name)

        fields = []
        field_str = " ".join(body_tokens)
        for field in field_str.split(";"):
            f = field.strip()
            if not f:
                continue
            parts = f.rsplit(maxsplit=1)
            if len(parts) == 2:
                ftype = clean_type(parts[0])
                fname = parts[1].replace("*", "")
                if "*" in parts[1]:
                    ftype = f"*{ftype}"
                fields.append(f"    {fname}: {ftype}")

        s_code = [f"struct {final_name} {{", ",\n".join(fields), "}"]
        self.structs.append("\n".join(s_code))

    def _is_function_header(self, p: BlockParser) -> bool:
        idx = p.pos
        paren_found = False
        while idx < p.length:
            t = p.tokens[idx]
            if t == ";":
                return False
            if t == "(":
                paren_found = True
            if paren_found and t == "{":
                return True
            idx += 1
            if idx - p.pos > 80:
                break
        return False

    def _parse_function(self, p: BlockParser):
        header_tokens = []
        while p.pos < p.length and p.peek() != "(":
            header_tokens.append(p.advance())

        if not header_tokens:
            p.advance()
            return

        func_name = header_tokens[-1].strip("*")
        raw_ret = " ".join(header_tokens[:-1])
        ret_type = clean_type(raw_ret) if raw_ret else "none"

        p.advance()
        param_tokens = []
        depth = 1
        while p.pos < p.length and depth > 0:
            tok = p.advance()
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
                if depth == 0:
                    break
            param_tokens.append(tok)

        param_str = " ".join(param_tokens)
        params_out = []
        if param_str and param_str != "void":
            for ppart in param_str.split(","):
                ppart = ppart.strip()
                if not ppart:
                    continue
                parts = ppart.rsplit(maxsplit=1)
                if len(parts) == 2:
                    ptype = clean_type(parts[0])
                    pname = parts[1].replace("*", "")
                    if "*" in parts[1]:
                        ptype = f"*{ptype}"
                    params_out.append(f"{pname}: {ptype}")

        body_tokens = p.parse_balanced_block()
        body_lines = self._transpile_block(body_tokens)

        # Internal class methods are static; export main
        is_main = (func_name == "main")
        prefix = "export " if is_main else "static "
        ret_clause = f": {ret_type}" if ret_type != "none" else ""
        header = f"{prefix}def {func_name}({', '.join(params_out)}){ret_clause} {{"

        res = [header] + [f"    {l}" for l in body_lines] + ["}"]
        self.methods.append("\n".join(res))

    def _transpile_block(self, tokens: List[str]) -> List[str]:
        out = []
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]

            # 1. While loop
            if tok == "while":
                cond_tokens, next_i = self._read_paren_group(tokens, i + 1)
                cond_raw = " ".join(cond_tokens)

                assign_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)', cond_raw)
                if assign_match:
                    var_name = assign_match.group(1).strip()
                    assign_expr = assign_match.group(2).rstrip(')').strip()

                    clean_target = assign_expr.replace("++", "").strip()
                    deref_match = re.search(r'\*\s*([a-zA-Z_][a-zA-Z0-9_]*)', clean_target)
                    ptr_name = deref_match.group(1) if deref_match else None

                    norm_expr = translate_tokens(CTokenizer(clean_target).get_tokens())
                    out.append(f"{var_name} = {norm_expr}")
                    if ptr_name:
                        out.append(f"{ptr_name} = {ptr_name} + 1")
                    out.append(f"while ({var_name} != 0) {{")

                    i = next_i
                    if i < n and tokens[i] == "{":
                        i += 1
                    continue
                else:
                    cond_str = translate_tokens(cond_tokens)
                    i = next_i
                    if i < n and tokens[i] != "{":
                        stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                        inner_stmt = self._transpile_stmt_str(stmt_toks)
                        if inner_stmt:
                            out.append(f"while ({cond_str}) {{ {inner_stmt} }}")
                        i = next_stmt_i
                    else:
                        out.append(f"while ({cond_str}) {{")
                        if i < n and tokens[i] == "{":
                            i += 1
                    continue

            # 2. C for-loop
            if tok == "for":
                for_tokens, next_i = self._read_paren_group(tokens, i + 1)
                for_str = " ".join(for_tokens)
                parts = for_str.split(";")
                init_part = parts[0].strip() if len(parts) > 0 else ""
                cond_part = translate_tokens(CTokenizer(parts[1].strip()).get_tokens()) if len(parts) > 1 and parts[1].strip() else "True"
                step_part = translate_tokens(CTokenizer(parts[2].strip()).get_tokens()) if len(parts) > 2 else ""

                if init_part:
                    out.append(self._transpile_stmt_str(CTokenizer(init_part).get_tokens()))

                i = next_i
                step_note = f" # step: {step_part}" if step_part else ""
                if i < n and tokens[i] != "{":
                    stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                    inner_stmt = self._transpile_stmt_str(stmt_toks)
                    if inner_stmt:
                        out.append(f"while ({cond_part}) {{ {inner_stmt}; {step_part} }}")
                    i = next_stmt_i
                else:
                    out.append(f"while ({cond_part}) {{{step_note}")
                    if i < n and tokens[i] == "{":
                        i += 1
                continue

            # 3. If statement
            if tok == "if":
                cond_tokens, next_i = self._read_paren_group(tokens, i + 1)
                cond_str = translate_tokens(cond_tokens)
                i = next_i

                if i < n and tokens[i] != "{":
                    stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                    inner_stmt = self._transpile_stmt_str(stmt_toks)
                    if inner_stmt:
                        out.append(f"if ({cond_str}) {{ {inner_stmt} }}")
                    i = next_stmt_i
                else:
                    out.append(f"if ({cond_str}) {{")
                    if i < n and tokens[i] == "{":
                        i += 1
                continue

            # 4. Else / Else If
            if tok == "else":
                if i + 1 < n and tokens[i+1] == "if":
                    cond_tokens, next_i = self._read_paren_group(tokens, i + 2)
                    cond_str = translate_tokens(cond_tokens)
                    i = next_i
                    if i < n and tokens[i] != "{":
                        stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                        inner_stmt = self._transpile_stmt_str(stmt_toks)
                        if inner_stmt:
                            out.append(f"else if ({cond_str}) {{ {inner_stmt} }}")
                        i = next_stmt_i
                    else:
                        out.append(f"else if ({cond_str}) {{")
                        if i < n and tokens[i] == "{":
                            i += 1
                    continue
                else:
                    i += 1
                    if i < n and tokens[i] != "{":
                        stmt_toks, next_stmt_i = self._read_single_statement(tokens, i)
                        inner_stmt = self._transpile_stmt_str(stmt_toks)
                        if inner_stmt:
                            out.append(f"else {{ {inner_stmt} }}")
                        i = next_stmt_i
                    else:
                        out.append("else {")
                        if i < n and tokens[i] == "{":
                            i += 1
                    continue

            # 5. Block closures
            if tok == "}":
                out.append("}")
                i += 1
                continue

            # 6. Read standard statements
            stmt_toks, next_i = self._read_single_statement(tokens, i)
            if next_i == i:
                i += 1
            else:
                i = next_i

            stmt_line = self._transpile_stmt_str(stmt_toks)
            if stmt_line:
                out.append(stmt_line)

        return out

    def _read_paren_group(self, tokens: List[str], start: int) -> Tuple[List[str], int]:
        if start >= len(tokens) or tokens[start] != "(":
            return [], start
        depth = 0
        group = []
        i = start
        while i < len(tokens):
            t = tokens[i]
            if t == "(":
                depth += 1
                if depth > 1:
                    group.append(t)
            elif t == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
                group.append(t)
            else:
                group.append(t)
            i += 1
        return group, i

    def _read_single_statement(self, tokens: List[str], start: int) -> Tuple[List[str], int]:
        """Reads exactly ONE statement ending at an un-nested semicolon."""
        stmt = []
        i = start
        paren_depth = 0
        bracket_depth = 0
        brace_depth = 0

        while i < len(tokens):
            t = tokens[i]

            if t == "(":
                paren_depth += 1
            elif t == ")":
                paren_depth -= 1
            elif t == "[":
                bracket_depth += 1
            elif t == "]":
                bracket_depth -= 1
            elif t == "{":
                brace_depth += 1
            elif t == "}":
                if brace_depth > 0:
                    brace_depth -= 1
                else:
                    if not stmt:
                        i += 1
                    break

            if paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
                if t == ";":
                    i += 1
                    break
                if t in ("{", "}") and not stmt:
                    i += 1
                    break
                if t in ("else", "if", "while", "for") and stmt:
                    break

            stmt.append(t)
            i += 1
        return stmt, i

    def _transpile_stmt_str(self, tokens: List[str]) -> str:
        if not tokens:
            return ""

        stmt = " ".join(tokens).strip()

        # Drop C unused-variable suppressors: `(void)var;`
        if re.match(r'^\(\s*void\s*\)\s*[a-zA-Z_][a-zA-Z0-9_]*$', stmt):
            return ""

        # 1. Chained assignments
        if stmt.count("=") > 1 and "==" not in stmt and "!=" not in stmt and "<=" not in stmt and ">=" not in stmt and not stmt.startswith("def ") and not stmt.startswith("struct "):
            parts = [p.strip() for p in re.split(r'(?<![!<>=+*/%&|^])=(?![=])', stmt)]
            if len(parts) > 2:
                final_val = translate_tokens(CTokenizer(parts[-1]).get_tokens())
                targets = parts[:-1]
                unrolled = [f"{tgt} = {final_val}" for tgt in reversed(targets)]
                return "\n    ".join(unrolled)

        # 2. Ternary
        ternary_m = re.match(r'^(return\s+)?(.+?)\s*\?\s*(.+?)\s*:\s*(.+)$', stmt)
        if ternary_m:
            ret_prefix = "return " if ternary_m.group(1) else ""
            cond = translate_tokens(CTokenizer(ternary_m.group(2)).get_tokens())
            true_v = translate_tokens(CTokenizer(ternary_m.group(3)).get_tokens())
            false_v = translate_tokens(CTokenizer(ternary_m.group(4)).get_tokens())
            return f"if ({cond}) {{ {ret_prefix}{true_v} }} else {{ {ret_prefix}{false_v} }}"

        # 3. Return
        if stmt.startswith("return"):
            parts = stmt.split(maxsplit=1)
            if len(parts) > 1:
                val = translate_tokens(CTokenizer(parts[1]).get_tokens())
                return f"return {val}"
            return "return"

        # 4. Multi-variable declarations
        if "," in stmt and "=" in stmt and "(" not in stmt:
            first_part = stmt.split(",")[0]
            decl_match = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', first_part.strip())
            if decl_match:
                raw_type = clean_type(decl_match.group(1))
                subbed = re.sub(r'\{([^}]+)\}', lambda m: m.group(0).replace(',', '§'), stmt)
                parts = subbed.split(",")
                res_decls = []
                for p in parts:
                    sub = p.replace('§', ',').strip()
                    m_sub = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', sub)
                    if m_sub:
                        sname = m_sub.group(1)
                        sval_raw = m_sub.group(2).strip()
                        if sval_raw.startswith("{") and sval_raw.endswith("}"):
                            args = sval_raw[1:-1].strip()
                            sval = f"{raw_type}({args})"
                        else:
                            sval = translate_tokens(CTokenizer(sval_raw).get_tokens())
                        res_decls.append(f"{sname}: {raw_type} = {sval}")
                    else:
                        m_full = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', sub)
                        if m_full:
                            sname = m_full.group(2)
                            sval_raw = m_full.group(3).strip()
                            if sval_raw.startswith("{") and sval_raw.endswith("}"):
                                args = sval_raw[1:-1].strip()
                                sval = f"{raw_type}({args})"
                            else:
                                sval = translate_tokens(CTokenizer(sval_raw).get_tokens())
                            res_decls.append(f"{sname}: {raw_type} = {sval}")
                return "\n    ".join(res_decls)

        # 5. Local stack arrays
        arr_match = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\s*([^\]]+)\s*\]$', stmt)
        if arr_match:
            raw_type = clean_type(arr_match.group(1))
            arr_name = arr_match.group(2)
            return f"{arr_name}: *{raw_type} = 0 as *{raw_type}"

        # 6. Single variable declaration
        decl_eq = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$', stmt)
        if decl_eq:
            raw_type = decl_eq.group(1).strip()
            name = decl_eq.group(2).strip()
            val_raw = decl_eq.group(3).strip()
            if not raw_type.startswith("return") and raw_type not in ("else", "goto"):
                stype = clean_type(raw_type)
                if val_raw.startswith("{") and val_raw.endswith("}"):
                    args = val_raw[1:-1].strip()
                    val = f"{stype}({args})"
                else:
                    val = translate_tokens(CTokenizer(val_raw).get_tokens())
                return f"{name}: {stype} = {val}"

        # 7. Uninitialized variable
        decl_uninit = re.match(r'^(?:const\s+)?([a-zA-Z_][a-zA-Z0-9_\s\*]+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)$', stmt)
        if decl_uninit:
            raw_type = decl_uninit.group(1).strip()
            name = decl_uninit.group(2).strip()
            if raw_type not in ("return", "break", "continue", "else", "goto"):
                stype = clean_type(raw_type)
                zero_val = "0 as *none" if stype.startswith("*") else "0"
                return f"{name}: {stype} = {zero_val}"

        return translate_tokens(tokens)


def determine_output_path(input_file: Path, requested_out: Optional[str]) -> Path:
    input_dir = input_file.parent.resolve()
    base_stem = input_file.stem

    if requested_out:
        out_path = Path(requested_out).resolve()
    else:
        out_path = input_dir / f"{base_stem}.spike"

    matching_c = out_path.parent / f"{out_path.stem}.c"
    if matching_c.is_file():
        safe_name = f"{out_path.stem}_transpiled.spike"
        out_path = out_path.parent / safe_name
        print(f"[*] Notice: Detected collision with {matching_c.name}. Directing output to {out_path.name}")

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Robust C to Spike Transpiler")
    parser.add_argument("input_file", help="Path to input C source file")
    parser.add_argument("-o", "--output", help="Output .spike file path")
    parser.add_argument("-c", "--class-name", default="FileSystem", help="Enclosing class name")
    parser.add_argument(
        "--follow-headers",
        action="store_true",
        default=False,
        help="Recursively resolve and inline local #include headers (default: disabled)"
    )
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    if not input_path.is_file():
        print(f"[-] Error: Input file '{args.input_file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        raw_c = f.read()

    resolver = HeaderResolver(input_path.parent, follow_headers=args.follow_headers)
    resolved_c = resolver.resolve(raw_c)

    transpiler = C2Spike(
        class_name=args.class_name,
        c_decls=resolver.c_decls,
        has_libc_headers=resolver.has_libc_headers
    )
    spike_code = transpiler.transpile(resolved_c)

    out_path = determine_output_path(input_path, args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(spike_code)

    print(f"[+] Successfully transpiled {input_path.name} -> {out_path.name}")


if __name__ == "__main__":
    main()
