import enum
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple as PyTuple

# =============================================================================
# 1. LEXER (LET REMOVED)
# =============================================================================

class TokenType(enum.Enum):
    LBRACE       = "{"
    RBRACE       = "}"
    LPAREN       = "("
    RPAREN       = ")"
    LBRACKET     = "["
    RBRACKET     = "]"
    COLON        = ":"
    COMMA        = ","
    DOT          = "."
    SEMICOLON    = ";"
    NEWLINE      = "NEWLINE"
    INDENT       = "INDENT"
    DEDENT       = "DEDENT"
    ARROW        = "=>"
    
    IDENT        = "IDENT"
    INT_LIT      = "INT_LIT"
    FLOAT_LIT    = "FLOAT_LIT"
    STRING_LIT   = "STRING_LIT"
    BOOL_LIT     = "BOOL_LIT"
    
    CLASS        = "class"
    STRUCT       = "struct"
    ENUM         = "enum"
    DEF          = "def"
    STATIC       = "static"
    EXTERN       = "extern"
    EXPORT       = "export"
    RETURN       = "return"
    IF           = "if"
    ELSE         = "else"
    WHILE        = "while"
    FOR          = "for"
    IN           = "in"
    BREAK        = "break"
    CONTINUE     = "continue"
    ASM          = "asm"
    DISOWN       = "disown"
    OWN          = "own"
    MANUAL     = "manual"
    TRY          = "try"
    EXCEPT       = "except"
    FINALLY      = "finally"
    RAISE        = "raise"
    IMPORT       = "import"
    FROM         = "from"
    SIZEOF       = "sizeof"
    TYPEOF       = "type_of"
    LEN          = "len"
    AS           = "as"
    IS           = "is"
    
    ASSIGN       = "="
    PLUS_ASSIGN  = "+="
    MINUS_ASSIGN = "-="
    STAR_ASSIGN  = "*="
    SLASH_ASSIGN = "/="
    PLUS         = "+"
    MINUS        = "-"
    STAR         = "*"
    SLASH        = "/"
    PERCENT      = "%"
    AMPERSAND    = "&"
    PIPE         = "|"
    CARET        = "^"
    TILDE        = "~"
    SHL          = "<<"
    SHR          = ">>"
    EQ           = "=="
    NEQ          = "!="
    LT           = "<"
    GT           = ">"
    LTE          = "<="
    GTE          = ">="
    AND          = "and"
    OR           = "or"
    NOT          = "not"
    
    EOF          = "EOF"

class Token:
    def __init__(self, type_: TokenType, value: any, line: int):
        self.type = type_
        self.value = value
        self.line = line

class IndentedBraceLexer:
    # Strictly pure OOP keywords - no 'let' keyword
    KEYWORDS = {
        "class": TokenType.CLASS, "struct": TokenType.STRUCT, "enum": TokenType.ENUM,
        "def": TokenType.DEF, "static": TokenType.STATIC, "extern": TokenType.EXTERN,
        "export": TokenType.EXPORT, "return": TokenType.RETURN, "if": TokenType.IF,
        "else": TokenType.ELSE, "while": TokenType.WHILE, "for": TokenType.FOR,
        "in": TokenType.IN, "break": TokenType.BREAK, "continue": TokenType.CONTINUE,
        "asm": TokenType.ASM, "disown": TokenType.DISOWN, "own": TokenType.OWN,
        "manual": TokenType.MANUAL, "try": TokenType.TRY, "except": TokenType.EXCEPT,
        "finally": TokenType.FINALLY, "raise": TokenType.RAISE, "import": TokenType.IMPORT,
        "from": TokenType.FROM, "sizeof": TokenType.SIZEOF, "type_of": TokenType.TYPEOF,
        "len": TokenType.LEN, "as": TokenType.AS, "is": TokenType.IS,
        "and": TokenType.AND, "or": TokenType.OR, "not": TokenType.NOT,
        "True": TokenType.BOOL_LIT, "False": TokenType.BOOL_LIT
    }

    def __init__(self, source: str):
        clean_src = source.replace('\r\n', '\n')
        # Replace multiline triple quotes with equivalent blank lines
        self.source = re.sub(
            r'(""".*?"""|\'\'\'.*?\'\'\')',
            lambda m: '\n' * m.group(0).count('\n'),
            clean_src,
            flags=re.DOTALL
        )
        self.indent_stack = [0]
        self.brace_depth = 0
        self.expecting_indent = False

    def tokenize(self) -> List[Token]:
        tokens = []
        for line_num, raw_line in enumerate(self.source.splitlines(keepends=True), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"): continue

            indent = 0
            i = 0
            while i < len(raw_line) and raw_line[i] in " \t":
                indent += (4 if raw_line[i] == "\t" else 1)
                i += 1

            if self.expecting_indent:
                if indent <= self.indent_stack[-1]:
                    raise SyntaxError(f"Line {line_num}: Expected indented block after '{{'")
                self.indent_stack.append(indent)
                tokens.append(Token(TokenType.INDENT, indent, line_num))
                self.expecting_indent = False
            elif indent < self.indent_stack[-1]:
                while self.indent_stack and self.indent_stack[-1] > indent:
                    self.indent_stack.pop()
                    tokens.append(Token(TokenType.DEDENT, None, line_num))
                if self.indent_stack[-1] != indent:
                    raise SyntaxError(f"Line {line_num}: Unaligned dedent depth ({indent})")

            while i < len(raw_line):
                ch = raw_line[i]
                if ch in " \t\r": i += 1; continue
                if ch == "\n": tokens.append(Token(TokenType.NEWLINE, "\n", line_num)); break
                if ch == "#": break

                two = raw_line[i:i+2]
                if two == "=>": tokens.append(Token(TokenType.ARROW, "=>", line_num)); i += 2; continue
                if two == "==": tokens.append(Token(TokenType.EQ, "==", line_num)); i += 2; continue
                if two == "!=": tokens.append(Token(TokenType.NEQ, "!=", line_num)); i += 2; continue
                if two == "<=": tokens.append(Token(TokenType.LTE, "<=", line_num)); i += 2; continue
                if two == ">=": tokens.append(Token(TokenType.GTE, ">=", line_num)); i += 2; continue
                if two == "<<": tokens.append(Token(TokenType.SHL, "<<", line_num)); i += 2; continue
                if two == ">>": tokens.append(Token(TokenType.SHR, ">>", line_num)); i += 2; continue
                if two == "+=": tokens.append(Token(TokenType.PLUS_ASSIGN, "+=", line_num)); i += 2; continue
                if two == "-=": tokens.append(Token(TokenType.MINUS_ASSIGN, "-=", line_num)); i += 2; continue
                if two == "*=": tokens.append(Token(TokenType.STAR_ASSIGN, "*=", line_num)); i += 2; continue
                if two == "/=": tokens.append(Token(TokenType.SLASH_ASSIGN, "/=", line_num)); i += 2; continue

                if ch == "{": self.brace_depth += 1; self.expecting_indent = True; tokens.append(Token(TokenType.LBRACE, "{", line_num)); i += 1; continue
                if ch == "}": self.brace_depth -= 1; tokens.append(Token(TokenType.RBRACE, "}", line_num)); i += 1; continue
                if ch == "(": tokens.append(Token(TokenType.LPAREN, "(", line_num)); i += 1; continue
                if ch == ")": tokens.append(Token(TokenType.RPAREN, ")", line_num)); i += 1; continue
                if ch == "[": tokens.append(Token(TokenType.LBRACKET, "[", line_num)); i += 1; continue
                if ch == "]": tokens.append(Token(TokenType.RBRACKET, "]", line_num)); i += 1; continue
                if ch == ":": tokens.append(Token(TokenType.COLON, ":", line_num)); i += 1; continue
                if ch == ",": tokens.append(Token(TokenType.COMMA, ",", line_num)); i += 1; continue
                if ch == ".": tokens.append(Token(TokenType.DOT, ".", line_num)); i += 1; continue
                if ch == ";": tokens.append(Token(TokenType.SEMICOLON, ";", line_num)); i += 1; continue
                if ch == "=": tokens.append(Token(TokenType.ASSIGN, "=", line_num)); i += 1; continue
                if ch == "+": tokens.append(Token(TokenType.PLUS, "+", line_num)); i += 1; continue
                if ch == "-": tokens.append(Token(TokenType.MINUS, "-", line_num)); i += 1; continue
                if ch == "*": tokens.append(Token(TokenType.STAR, "*", line_num)); i += 1; continue
                if ch == "/": tokens.append(Token(TokenType.SLASH, "/", line_num)); i += 1; continue
                if ch == "%": tokens.append(Token(TokenType.PERCENT, "%", line_num)); i += 1; continue
                if ch == "&": tokens.append(Token(TokenType.AMPERSAND, "&", line_num)); i += 1; continue
                if ch == "|": tokens.append(Token(TokenType.PIPE, "|", line_num)); i += 1; continue
                if ch == "^": tokens.append(Token(TokenType.CARET, "^", line_num)); i += 1; continue
                if ch == "~": tokens.append(Token(TokenType.TILDE, "~", line_num)); i += 1; continue
                if ch == "<": tokens.append(Token(TokenType.LT, "<", line_num)); i += 1; continue
                if ch == ">": tokens.append(Token(TokenType.GT, ">", line_num)); i += 1; continue

                if ch in ('"', "'"):
                    q = ch; val = []; i += 1
                    while i < len(raw_line) and raw_line[i] != q:
                        if raw_line[i] == "\\" and i + 1 < len(raw_line):
                            val.append(raw_line[i:i+2]); i += 2
                        else:
                            val.append(raw_line[i]); i += 1
                    i += 1
                    tokens.append(Token(TokenType.STRING_LIT, "".join(val), line_num))
                    continue

                if ch.isdigit() or (ch == '0' and i + 1 < len(raw_line) and raw_line[i+1] in 'xX'):
                    val = []
                    if raw_line.startswith(("0x", "0X"), i):
                        val.extend([raw_line[i], raw_line[i+1]]); i += 2
                        while i < len(raw_line) and (raw_line[i].isdigit() or raw_line[i] in 'abcdefABCDEF'):
                            val.append(raw_line[i]); i += 1
                        tokens.append(Token(TokenType.INT_LIT, int("".join(val), 16), line_num))
                        continue
                    is_float = False
                    while i < len(raw_line) and (raw_line[i].isdigit() or raw_line[i] == '.'):
                        if raw_line[i] == '.':
                            if is_float: break
                            is_float = True
                        val.append(raw_line[i]); i += 1
                    s_num = "".join(val)
                    tokens.append(Token(TokenType.FLOAT_LIT if is_float else TokenType.INT_LIT, float(s_num) if is_float else int(s_num), line_num))
                    continue

                if ch.isalpha() or ch == "_":
                    val = []
                    while i < len(raw_line) and (raw_line[i].isalnum() or raw_line[i] == "_"):
                        val.append(raw_line[i]); i += 1
                    ident = "".join(val)
                    ttype = self.KEYWORDS.get(ident, TokenType.IDENT)
                    b_val = True if ident == "True" else (False if ident == "False" else ident)
                    tokens.append(Token(ttype, b_val, line_num))
                    continue

                raise SyntaxError(f"Line {line_num}: Unexpected character '{ch}'")

        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            tokens.append(Token(TokenType.DEDENT, None, 0))
        tokens.append(Token(TokenType.EOF, None, 0))
        return tokens

# =============================================================================
# 2. AST DEFINITIONS
# =============================================================================

class ASTNode: pass
class Expr(ASTNode): pass

@dataclass
class IntLiteral(Expr): value: int
@dataclass
class FloatLiteral(Expr): value: float
@dataclass
class StringLiteral(Expr): value: str
@dataclass
class BoolLiteral(Expr): value: bool
@dataclass
class Identifier(Expr): name: str
@dataclass
class UnaryExpr(Expr): op: str; right: Expr
@dataclass
class BinaryExpr(Expr): left: Expr; op: str; right: Expr
@dataclass
class MemberAccessExpr(Expr): target: Expr; member: str
@dataclass
class IndexAccessExpr(Expr): target: Expr; index: Expr
@dataclass
class SliceExpr(Expr): target: Expr; start: Expr; end: Expr
@dataclass
class CastExpr(Expr): target: Expr; to_type: str
@dataclass
class TypeCheckExpr(Expr): target: Expr; type_name: str
@dataclass
class SizeofExpr(Expr): type_name: str
@dataclass
class LenExpr(Expr): target: Expr
@dataclass
class NamedArg: name: str; value: Expr
@dataclass
class CallExpr(Expr):
    callee: Expr
    args: List[Expr]
    named_args: List[NamedArg] = field(default_factory=list)
@dataclass
class ListLiteral(Expr): elements: List[Expr]
@dataclass
class TupleLiteral(Expr): elements: List[Expr]
@dataclass
class ManualAllocExpr(Expr): class_name: str; args: List[Expr]
@dataclass
class Param:
    name: str
    type_name: str
    default_value: Optional[Expr] = None
@dataclass
class LambdaExpr(Expr):
    params: List[Param]
    return_type: Optional[str]
    body: List['Stmt']
    lambda_id: int = 0
    captured_vars: List[str] = field(default_factory=list)

class Stmt(ASTNode): pass

@dataclass
class ImportStmt(Stmt): module_path: List[str]; symbols: Optional[List[str]] = None
@dataclass
class VarDeclStmt(Stmt): name: str; type_name: str; initializer: Optional[Expr] = None
@dataclass
class UnpackVarDeclStmt(Stmt): names: List[str]; type_names: List[str]; initializer: Expr
@dataclass
class AssignStmt(Stmt): target: Expr; op: str; value: Expr
@dataclass
class ReturnStmt(Stmt): value: Optional[Expr] = None
@dataclass
class BreakStmt(Stmt): pass
@dataclass
class ContinueStmt(Stmt): pass
@dataclass
class IfStmt(Stmt): condition: Expr; then_body: List[Stmt]; else_body: Optional[List[Stmt]] = None
@dataclass
class WhileStmt(Stmt): condition: Expr; body: List[Stmt]
@dataclass
class ForRangeStmt(Stmt):
    var_name: str
    start: Expr
    stop: Expr
    step: Expr
    body: List[Stmt]
@dataclass
class ExprStmt(Stmt): expr: Expr
@dataclass
class DisownStmt(Stmt): target: Expr
@dataclass
class OwnStmt(Stmt): target: Expr
@dataclass
class RaiseStmt(Stmt): exception: Expr
@dataclass
class ExceptHandler: var_name: Optional[str]; exc_type: str; body: List[Stmt]
@dataclass
class TryStmt(Stmt): body: List[Stmt]; handlers: List[ExceptHandler]; finally_body: Optional[List[Stmt]] = None
@dataclass
class AsmConstraint: constraint: str; variable: Expr
@dataclass
class AsmStmt(Stmt): template: str; outputs: List[AsmConstraint]; inputs: List[AsmConstraint]; clobbers: List[str]

@dataclass
class FieldDecl(ASTNode): name: str; type_name: str; default_value: Optional[Expr] = None
@dataclass
class MethodDecl(ASTNode):
    name: str
    params: List[Param]
    return_type: Optional[str]
    body: Optional[List[Stmt]] = None
    is_static: bool = False
    is_extern: bool = False
    is_export: bool = False

@dataclass
class ClassDecl(ASTNode): name: str; parent_name: Optional[str]; fields: List[FieldDecl]; methods: List[MethodDecl]
@dataclass
class StructDecl(ASTNode): name: str; fields: List[FieldDecl]  # Pure data: no methods list
@dataclass
class EnumMember: name: str; value: int
@dataclass
class EnumDecl(ASTNode): name: str; members: List[EnumMember]

@dataclass
class Program(ASTNode):
    imports: List[ImportStmt]
    enums: List[EnumDecl]
    structs: List[StructDecl]
    classes: List[ClassDecl]

# =============================================================================
# 3. PARSER (PURE OOP & PURE DATA STRUCTS)
# =============================================================================

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.lambda_id = 0

    def peek(self) -> Token: return self.tokens[self.pos]
    def advance(self) -> Token:
        tok = self.peek()
        if tok.type != TokenType.EOF: self.pos += 1
        return tok
    def match(self, *types: TokenType) -> bool:
        if self.peek().type in types: self.advance(); return True
        return False
    def consume(self, t: TokenType, msg: str) -> Token:
        if self.peek().type == t: return self.advance()
        raise SyntaxError(f"Line {self.peek().line}: {msg}. Got '{self.peek().value}'")
    def skip_newlines(self):
        while self.match(TokenType.NEWLINE): pass

    def parse(self) -> Program:
        imports, enums, structs, classes = [], [], [], []
        self.skip_newlines()
        while self.peek().type != TokenType.EOF:
            if self.peek().type in (TokenType.IMPORT, TokenType.FROM):
                imports.append(self.parse_import())
            elif self.peek().type == TokenType.ENUM:
                enums.append(self.parse_enum())
            elif self.peek().type == TokenType.STRUCT:
                structs.append(self.parse_struct())
            elif self.peek().type == TokenType.CLASS:
                classes.append(self.parse_class())
            elif self.peek().type in (TokenType.DEF, TokenType.STATIC):
                fn_token = self.peek()
                next_val = self.tokens[self.pos + 1].value if self.pos + 1 < len(self.tokens) else "method"
                raise SyntaxError(
                    f"Line {fn_token.line}: Standalone functions are forbidden in Spike. "
                    f"Spike is purely object-oriented; encapsulate '{next_val}' inside a class."
                )
            else:
                tok = self.peek()
                raise SyntaxError(f"Line {tok.line}: Expected class, struct, enum, or import; got '{tok.value}'")
            self.skip_newlines()
        return Program(imports=imports, enums=enums, structs=structs, classes=classes)

    def parse_import(self) -> ImportStmt:
        if self.match(TokenType.FROM):
            mod_path = [self.consume(TokenType.IDENT, "Expected module name").value]
            while self.match(TokenType.DOT): mod_path.append(self.consume(TokenType.IDENT, "Expected module part").value)
            self.consume(TokenType.IMPORT, "Expected 'import'")
            syms = [self.consume(TokenType.IDENT, "Expected symbol").value]
            while self.match(TokenType.COMMA): syms.append(self.consume(TokenType.IDENT, "Expected symbol").value)
            return ImportStmt(module_path=mod_path, symbols=syms)
        else:
            self.consume(TokenType.IMPORT, "Expected 'import'")
            mod_path = [self.consume(TokenType.IDENT, "Expected module name").value]
            while self.match(TokenType.DOT): mod_path.append(self.consume(TokenType.IDENT, "Expected module part").value)
            return ImportStmt(module_path=mod_path, symbols=None)

    def parse_enum(self) -> EnumDecl:
        self.consume(TokenType.ENUM, "Expected 'enum'")
        name = self.consume(TokenType.IDENT, "Expected enum name").value
        self.consume(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines(); self.consume(TokenType.INDENT, "Expected indent"); self.skip_newlines()
        members = []
        cur_val = 0
        while self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            mname = self.consume(TokenType.IDENT, "Expected enum member name").value
            if self.match(TokenType.ASSIGN):
                cur_val = self.consume(TokenType.INT_LIT, "Expected integer enum value").value
            members.append(EnumMember(name=mname, value=cur_val))
            cur_val += 1
            self.skip_newlines()
        self.consume(TokenType.DEDENT, "Expected dedent")
        self.skip_newlines(); self.consume(TokenType.RBRACE, "Expected '}'")
        return EnumDecl(name=name, members=members)

    # Structs are strictly pure data - methods are rejected
    def parse_struct(self) -> StructDecl:
        self.consume(TokenType.STRUCT, "Expected 'struct'")
        name = self.consume(TokenType.IDENT, "Expected struct name").value
        self.consume(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines(); self.consume(TokenType.INDENT, "Expected indent"); self.skip_newlines()
        fields = []
        while self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            if self.peek().type in (TokenType.DEF, TokenType.STATIC):
                raise SyntaxError(
                    f"Line {self.peek().line}: Struct '{name}' cannot contain methods. "
                    f"Structs are strictly pure-data value types. Use a class for methods and behaviors."
                )
            fn = self.consume(TokenType.IDENT, "Expected field name").value
            self.consume(TokenType.COLON, "Expected ':'")
            ft = self.parse_type_annotation()
            dflt = self.parse_expression() if self.match(TokenType.ASSIGN) else None
            fields.append(FieldDecl(name=fn, type_name=ft, default_value=dflt))
            self.skip_newlines()
        self.consume(TokenType.DEDENT, "Expected dedent")
        self.skip_newlines(); self.consume(TokenType.RBRACE, "Expected '}'")
        return StructDecl(name=name, fields=fields)

    def parse_class(self) -> ClassDecl:
        self.consume(TokenType.CLASS, "Expected 'class'")
        name = self.consume(TokenType.IDENT, "Expected class name").value
        parent = None
        if self.match(TokenType.LPAREN):
            parent = self.consume(TokenType.IDENT, "Expected parent class").value
            self.consume(TokenType.RPAREN, "Expected ')'")
        self.consume(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines(); self.consume(TokenType.INDENT, "Expected indent"); self.skip_newlines()
        fields, methods = [], []
        while self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            if self.peek().type in (TokenType.DEF, TokenType.STATIC, TokenType.EXTERN, TokenType.EXPORT):
                methods.append(self.parse_method())
            else:
                fn = self.consume(TokenType.IDENT, "Expected field name").value
                self.consume(TokenType.COLON, "Expected ':'")
                ft = self.parse_type_annotation()
                dflt = self.parse_expression() if self.match(TokenType.ASSIGN) else None
                fields.append(FieldDecl(name=fn, type_name=ft, default_value=dflt))
            self.skip_newlines()
        self.consume(TokenType.DEDENT, "Expected dedent")
        self.skip_newlines(); self.consume(TokenType.RBRACE, "Expected '}'")
        return ClassDecl(name=name, parent_name=parent, fields=fields, methods=methods)

    def parse_type_annotation(self) -> str:
        if self.match(TokenType.STAR):
            return f"*{self.parse_type_annotation()}"
        if self.match(TokenType.LBRACKET):
            inner = self.parse_type_annotation()
            if self.match(TokenType.SEMICOLON):
                size = self.consume(TokenType.INT_LIT, "Expected array size").value
                self.consume(TokenType.RBRACKET, "Expected ']'")
                return f"array<{inner},{size}>"
            self.consume(TokenType.RBRACKET, "Expected ']'")
            return f"slice<{inner}>"
        if self.match(TokenType.LPAREN):
            types = [self.parse_type_annotation()]
            while self.match(TokenType.COMMA): types.append(self.parse_type_annotation())
            self.consume(TokenType.RPAREN, "Expected ')'")
            return f"tuple<{','.join(types)}>"
        return self.consume(TokenType.IDENT, "Expected type name").value

    def parse_method(self) -> MethodDecl:
        is_static = self.match(TokenType.STATIC)
        is_ext = self.match(TokenType.EXTERN)
        is_exp = self.match(TokenType.EXPORT)
        self.consume(TokenType.DEF, "Expected 'def'")
        name = self.consume(TokenType.IDENT, "Expected method name").value
        self.consume(TokenType.LPAREN, "Expected '('")
        params = []
        if self.peek().type != TokenType.RPAREN:
            while True:
                pn = self.consume(TokenType.IDENT, "Expected param name").value
                self.consume(TokenType.COLON, "Expected ':'")
                pt = self.parse_type_annotation()
                dflt = self.parse_expression() if self.match(TokenType.ASSIGN) else None
                params.append(Param(name=pn, type_name=pt, default_value=dflt))
                if not self.match(TokenType.COMMA): break
        self.consume(TokenType.RPAREN, "Expected ')'")
        ret_t = self.parse_type_annotation() if self.match(TokenType.COLON) else None
        body = self.parse_block() if not is_ext else None
        return MethodDecl(name=name, params=params, return_type=ret_t, body=body, is_static=is_static, is_extern=is_ext, is_export=is_exp)

    def parse_block(self) -> List[Stmt]:
        self.consume(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines(); self.consume(TokenType.INDENT, "Expected indent"); self.skip_newlines()
        stmts = []
        while self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            stmts.append(self.parse_statement())
            self.skip_newlines()
        self.consume(TokenType.DEDENT, "Expected dedent")
        self.skip_newlines(); self.consume(TokenType.RBRACE, "Expected '}'")
        return stmts

    def parse_statement(self) -> Stmt:
        if self.match(TokenType.RETURN):
            val = None if self.peek().type in (TokenType.NEWLINE, TokenType.RBRACE, TokenType.DEDENT) else self.parse_expression()
            return ReturnStmt(value=val)
        if self.match(TokenType.BREAK): return BreakStmt()
        if self.match(TokenType.CONTINUE): return ContinueStmt()
        if self.match(TokenType.IF): return self.parse_if()
        if self.match(TokenType.WHILE): return self.parse_while()
        if self.match(TokenType.FOR): return self.parse_for()
        if self.match(TokenType.ASM): return self.parse_asm_stmt()
        if self.match(TokenType.TRY): return self.parse_try()
        if self.match(TokenType.RAISE): return RaiseStmt(exception=self.parse_expression())
        if self.match(TokenType.DISOWN): return DisownStmt(target=self.parse_expression())
        if self.match(TokenType.OWN): return OwnStmt(target=self.parse_expression())

        # Unpack / Colon-based Declaration / Assignment
        if self.check_unpack_decl(): return self.parse_unpack_decl()
        if self.check_var_decl(): return self.parse_var_decl()

        expr = self.parse_expression()
        for assign_op in (TokenType.ASSIGN, TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN, TokenType.STAR_ASSIGN, TokenType.SLASH_ASSIGN):
            if self.match(assign_op):
                val = self.parse_expression()
                return AssignStmt(target=expr, op=assign_op.value, value=val)
        return ExprStmt(expr=expr)

    def check_unpack_decl(self) -> bool:
        if self.peek().type != TokenType.LPAREN: return False
        i = self.pos + 1
        while i < len(self.tokens) and self.tokens[i].type != TokenType.RPAREN:
            if self.tokens[i].type == TokenType.COLON: return True
            i += 1
        return False

    def parse_unpack_decl(self) -> UnpackVarDeclStmt:
        self.consume(TokenType.LPAREN, "Expected '('")
        names, types = [], []
        while True:
            names.append(self.consume(TokenType.IDENT, "Expected name").value)
            self.consume(TokenType.COLON, "Expected ':'")
            types.append(self.parse_type_annotation())
            if not self.match(TokenType.COMMA): break
        self.consume(TokenType.RPAREN, "Expected ')'")
        self.consume(TokenType.ASSIGN, "Expected '='")
        init = self.parse_expression()
        return UnpackVarDeclStmt(names=names, type_names=types, initializer=init)

    def check_var_decl(self) -> bool:
        if self.peek().type == TokenType.IDENT:
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == TokenType.COLON:
                return True
        return False

    def parse_var_decl(self) -> VarDeclStmt:
        name = self.consume(TokenType.IDENT, "Expected variable name").value
        self.consume(TokenType.COLON, "Expected ':'")
        tname = self.parse_type_annotation()
        init = self.parse_expression() if self.match(TokenType.ASSIGN) else None
        return VarDeclStmt(name=name, type_name=tname, initializer=init)

    def parse_if(self) -> IfStmt:
        cond = self.parse_expression()
        then_b = self.parse_block()
        else_b = None
        self.skip_newlines()
        if self.match(TokenType.ELSE): else_b = self.parse_block()
        return IfStmt(condition=cond, then_body=then_b, else_body=else_b)

    def parse_while(self) -> WhileStmt:
        cond = self.parse_expression()
        body = self.parse_block()
        return WhileStmt(condition=cond, body=body)

    def parse_for(self) -> ForRangeStmt:
        vname = self.consume(TokenType.IDENT, "Expected loop variable").value
        self.consume(TokenType.IN, "Expected 'in'")
        self.consume(TokenType.IDENT, "Expected 'range'")
        self.consume(TokenType.LPAREN, "Expected '('")
        start = self.parse_expression()
        self.consume(TokenType.COMMA, "Expected ','")
        stop = self.parse_expression()
        step = self.parse_expression() if self.match(TokenType.COMMA) else IntLiteral(1)
        self.consume(TokenType.RPAREN, "Expected ')'")
        body = self.parse_block()
        return ForRangeStmt(var_name=vname, start=start, stop=stop, step=step, body=body)

    def parse_try(self) -> TryStmt:
        body = self.parse_block()
        handlers = []
        self.skip_newlines()
        while self.match(TokenType.EXCEPT):
            vname = None
            if self.peek().type == TokenType.IDENT and self.tokens[self.pos+1].type == TokenType.COLON:
                vname = self.advance().value
                self.consume(TokenType.COLON, "Expected ':'")
            exc_t = self.consume(TokenType.IDENT, "Expected exception type").value
            h_body = self.parse_block()
            handlers.append(ExceptHandler(var_name=vname, exc_type=exc_t, body=h_body))
            self.skip_newlines()
        finally_b = self.parse_block() if self.match(TokenType.FINALLY) else None
        return TryStmt(body=body, handlers=handlers, finally_body=finally_b)

    def parse_asm_stmt(self) -> AsmStmt:
        self.consume(TokenType.LBRACE, "Expected '{'")
        self.skip_newlines(); self.consume(TokenType.INDENT, "Expected indent"); self.skip_newlines()
        template = self.consume(TokenType.STRING_LIT, "Expected assembly template").value
        self.skip_newlines()
        outputs, inputs, clobbers = [], [], []
        if self.match(TokenType.COLON):
            outputs = self.parse_asm_operands()
            self.skip_newlines()
            if self.match(TokenType.COLON):
                inputs = self.parse_asm_operands()
                self.skip_newlines()
                if self.match(TokenType.COLON):
                    while True:
                        clobbers.append(self.consume(TokenType.STRING_LIT, "Expected clobber").value)
                        if not self.match(TokenType.COMMA): break
                    self.skip_newlines()
        self.consume(TokenType.DEDENT, "Expected dedent")
        self.skip_newlines(); self.consume(TokenType.RBRACE, "Expected '}'")
        return AsmStmt(template=template, outputs=outputs, inputs=inputs, clobbers=clobbers)

    def parse_asm_operands(self) -> List[AsmConstraint]:
        operands = []
        if self.peek().type in (TokenType.COLON, TokenType.DEDENT, TokenType.RBRACE): return operands
        while True:
            c = self.consume(TokenType.STRING_LIT, "Expected constraint string").value
            self.consume(TokenType.LPAREN, "Expected '('")
            v = self.parse_expression()
            self.consume(TokenType.RPAREN, "Expected ')'")
            operands.append(AsmConstraint(constraint=c, variable=v))
            if not self.match(TokenType.COMMA): break
        return operands

    def parse_expression(self) -> Expr: return self.parse_logical_or()

    def parse_logical_or(self) -> Expr:
        expr = self.parse_logical_and()
        while self.match(TokenType.OR): expr = BinaryExpr(left=expr, op="||", right=self.parse_logical_and())
        return expr

    def parse_logical_and(self) -> Expr:
        expr = self.parse_bitwise_or()
        while self.match(TokenType.AND): expr = BinaryExpr(left=expr, op="&&", right=self.parse_bitwise_or())
        return expr

    def parse_bitwise_or(self) -> Expr:
        expr = self.parse_bitwise_xor()
        while self.match(TokenType.PIPE): expr = BinaryExpr(left=expr, op="|", right=self.parse_bitwise_xor())
        return expr

    def parse_bitwise_xor(self) -> Expr:
        expr = self.parse_bitwise_and()
        while self.match(TokenType.CARET): expr = BinaryExpr(left=expr, op="^", right=self.parse_bitwise_and())
        return expr

    def parse_bitwise_and(self) -> Expr:
        expr = self.parse_equality()
        while self.match(TokenType.AMPERSAND): expr = BinaryExpr(left=expr, op="&", right=self.parse_equality())
        return expr

    def parse_equality(self) -> Expr:
        expr = self.parse_relational()
        while self.match(TokenType.EQ, TokenType.NEQ, TokenType.IS):
            op = self.tokens[self.pos - 1]
            if op.type == TokenType.IS:
                t_name = self.consume(TokenType.IDENT, "Expected type name after 'is'").value
                expr = TypeCheckExpr(target=expr, type_name=t_name)
            else:
                expr = BinaryExpr(left=expr, op=op.value, right=self.parse_relational())
        return expr

    def parse_relational(self) -> Expr:
        expr = self.parse_shift()
        while self.match(TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE, TokenType.AS):
            op = self.tokens[self.pos - 1]
            if op.type == TokenType.AS:
                t_name = self.parse_type_annotation()
                expr = CastExpr(target=expr, to_type=t_name)
            else:
                expr = BinaryExpr(left=expr, op=op.value, right=self.parse_shift())
        return expr

    def parse_shift(self) -> Expr:
        expr = self.parse_additive()
        while self.match(TokenType.SHL, TokenType.SHR):
            op = self.tokens[self.pos - 1].value
            expr = BinaryExpr(left=expr, op=op, right=self.parse_additive())
        return expr

    def parse_additive(self) -> Expr:
        expr = self.parse_multiplicative()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            op = self.tokens[self.pos - 1].value
            expr = BinaryExpr(left=expr, op=op, right=self.parse_multiplicative())
        return expr

    def parse_multiplicative(self) -> Expr:
        expr = self.parse_unary()
        while self.match(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self.tokens[self.pos - 1].value
            expr = BinaryExpr(left=expr, op=op, right=self.parse_unary())
        return expr

    def parse_unary(self) -> Expr:
        if self.match(TokenType.STAR, TokenType.AMPERSAND, TokenType.MINUS, TokenType.TILDE, TokenType.NOT):
            op = self.tokens[self.pos - 1].value
            c_op = "!" if op == "not" else op
            return UnaryExpr(op=c_op, right=self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> Expr:
        expr = self.parse_primary()
        while True:
            if self.match(TokenType.DOT):
                m = self.consume(TokenType.IDENT, "Expected member name").value
                expr = MemberAccessExpr(target=expr, member=m)
            elif self.match(TokenType.LBRACKET):
                first = self.parse_expression()
                if self.match(TokenType.COLON):
                    end = self.parse_expression()
                    self.consume(TokenType.RBRACKET, "Expected ']'")
                    expr = SliceExpr(target=expr, start=first, end=end)
                else:
                    self.consume(TokenType.RBRACKET, "Expected ']'")
                    expr = IndexAccessExpr(target=expr, index=first)
            elif self.match(TokenType.LPAREN):
                pos_args, named_args = [], []
                if self.peek().type != TokenType.RPAREN:
                    while True:
                        if self.peek().type == TokenType.IDENT and self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == TokenType.ASSIGN:
                            aname = self.advance().value
                            self.advance()
                            named_args.append(NamedArg(name=aname, value=self.parse_expression()))
                        else:
                            pos_args.append(self.parse_expression())
                        if not self.match(TokenType.COMMA): break
                self.consume(TokenType.RPAREN, "Expected ')'")
                expr = CallExpr(callee=expr, args=pos_args, named_args=named_args)
            else:
                break
        return expr

    def parse_primary(self) -> Expr:
        if self._is_lambda(): return self._parse_lambda()
        if self.match(TokenType.SIZEOF):
            self.consume(TokenType.LPAREN, "Expected '('")
            tname = self.parse_type_annotation()
            self.consume(TokenType.RPAREN, "Expected ')'")
            return SizeofExpr(type_name=tname)
        if self.match(TokenType.LEN):
            self.consume(TokenType.LPAREN, "Expected '('")
            target = self.parse_expression()
            self.consume(TokenType.RPAREN, "Expected ')'")
            return LenExpr(target=target)
        if self.match(TokenType.LBRACKET):
            elems = []
            if self.peek().type != TokenType.RBRACKET:
                while True:
                    elems.append(self.parse_expression())
                    if not self.match(TokenType.COMMA): break
            self.consume(TokenType.RBRACKET, "Expected ']'")
            return ListLiteral(elements=elems)
        if self.match(TokenType.MANUAL):
            cls = self.consume(TokenType.IDENT, "Expected class name").value
            self.consume(TokenType.LPAREN, "Expected '('")
            args = []
            if self.peek().type != TokenType.RPAREN:
                while True:
                    args.append(self.parse_expression())
                    if not self.match(TokenType.COMMA): break
            self.consume(TokenType.RPAREN, "Expected ')'")
            return ManualAllocExpr(class_name=cls, args=args)
        if self.match(TokenType.LPAREN):
            first = self.parse_expression()
            if self.match(TokenType.COMMA):
                elems = [first]
                while True:
                    elems.append(self.parse_expression())
                    if not self.match(TokenType.COMMA): break
                self.consume(TokenType.RPAREN, "Expected ')'")
                return TupleLiteral(elements=elems)
            self.consume(TokenType.RPAREN, "Expected ')'")
            return first

        if self.match(TokenType.INT_LIT): return IntLiteral(value=self.tokens[self.pos - 1].value)
        if self.match(TokenType.FLOAT_LIT): return FloatLiteral(value=self.tokens[self.pos - 1].value)
        if self.match(TokenType.STRING_LIT): return StringLiteral(value=self.tokens[self.pos - 1].value)
        if self.match(TokenType.BOOL_LIT): return BoolLiteral(value=self.tokens[self.pos - 1].value)
        if self.match(TokenType.IDENT): return Identifier(name=self.tokens[self.pos - 1].value)

        tok = self.peek()
        raise SyntaxError(f"Line {tok.line}: Unexpected token '{tok.value}'")

    def _is_lambda(self) -> bool:
        if self.peek().type != TokenType.LPAREN: return False
        idx = self.pos + 1; depth = 1
        while idx < len(self.tokens) and depth > 0:
            if self.tokens[idx].type == TokenType.LPAREN: depth += 1
            elif self.tokens[idx].type == TokenType.RPAREN: depth -= 1
            idx += 1
        if idx < len(self.tokens) and self.tokens[idx].type == TokenType.COLON: idx += 2
        return idx < len(self.tokens) and self.tokens[idx].type == TokenType.ARROW

    def _parse_lambda(self) -> LambdaExpr:
        self.consume(TokenType.LPAREN, "Expected '('")
        params = []
        if self.peek().type != TokenType.RPAREN:
            while True:
                pn = self.consume(TokenType.IDENT, "Expected param").value
                self.consume(TokenType.COLON, "Expected ':'")
                pt = self.parse_type_annotation()
                params.append(Param(name=pn, type_name=pt))
                if not self.match(TokenType.COMMA): break
        self.consume(TokenType.RPAREN, "Expected ')'")
        ret_t = self.parse_type_annotation() if self.match(TokenType.COLON) else None
        self.consume(TokenType.ARROW, "Expected '=>'")
        body = self.parse_block()
        self.lambda_id += 1
        return LambdaExpr(params=params, return_type=ret_t, body=body, lambda_id=self.lambda_id)

# =============================================================================
# 4. C CODE GENERATOR
# =============================================================================

class CCodeGenerator:
    TYPE_MAP = {
        "int": "int64_t", "u8": "uint8_t", "u16": "uint16_t",
        "u32": "uint32_t", "u64": "uint64_t", "usize": "uintptr_t",
        "float": "double", "bool": "bool", "String": "String*",
        "List": "List*", "Tuple": "Tuple*", "Closure": "Closure*",
        "Object": "Object*", "void": "void"
    }

    def __init__(self, ast: Program, module_name: str = "main"):
        self.ast = ast
        self.module_name = module_name
        self.classes: Dict[str, ClassDecl] = {c.name: c for c in ast.classes}
        self.structs: Dict[str, StructDecl] = {s.name: s for s in ast.structs}
        self.enums: Dict[str, EnumDecl] = {e.name: e for e in ast.enums}
        self.var_types: Dict[str, str] = {}
        self.tuple_returns: Set[str] = set()
        self._scan_tuple_returns()

    def _scan_tuple_returns(self):
        for c in self.ast.classes:
            for m in c.methods:
                if m.return_type and m.return_type.startswith("tuple<"):
                    self.tuple_returns.add(m.return_type)

    def c_type(self, t: Optional[str]) -> str:
        if not t: return "void"
        if t.startswith("*"): return f"{self.c_type(t[1:])}*"
        if t.startswith("slice<"): return "Slice"
        if t.startswith("array<"):
            parts = t[6:-1].split(",")
            return f"{self.c_type(parts[0])}"
        if t.startswith("tuple<"):
            inner = t[6:-1].replace(",", "_").replace("*", "ptr_")
            return f"__SpikeTuple_{inner}"
        if t in self.TYPE_MAP: return self.TYPE_MAP[t]
        if t in self.classes: return f"{t}*"
        if t in self.structs or t in self.enums: return t
        return t

    def _format_params(self, container_name: str, m: MethodDecl) -> str:
        params_list = []
        if not m.is_static:
            params_list.append(f"{container_name}* self")
        for p in m.params:
            params_list.append(f"{self.c_type(p.type_name)} {p.name}")
        return ", ".join(params_list) or "void"

    def generate_header(self) -> str:
        guard = f"SPIKE_MOD_{self.module_name.upper().replace('.', '_')}_H"
        out = [f"#ifndef {guard}", f"#define {guard}", '#include "spike_rt.h"', "", '#ifdef __cplusplus', 'extern "C" {', '#endif', ""]

        for e in self.ast.enums:
            out.append(f"typedef enum {e.name} {{")
            for m in e.members: out.append(f"    {e.name}_{m.name} = {m.value},")
            out.append(f"}} {e.name};\n")

        for s in self.ast.structs: out.append(f"typedef struct {s.name} {s.name};")
        for c in self.ast.classes:
            out.append(f"typedef struct {c.name} {c.name};")
            out.append(f"typedef struct {c.name}_VTable {c.name}_VTable;")
        out.append("")

        # Structs are emitted as pure data PODs
        for s in self.ast.structs:
            out.append(f"struct {s.name} {{")
            for f in s.fields: out.append(f"    {self.c_type(f.type_name)} {f.name};")
            out.append("};\n")

        # Classes carry Object header and methods
        for c in self.ast.classes:
            out.append(f"struct {c.name}_VTable {{ Object_VTable __base; }};")
            out.append(f"struct {c.name} {{")
            out.append("    Object __hdr;")
            for f in c.fields: out.append(f"    {self.c_type(f.type_name)} {f.name};")
            out.append("};\n")
            for m in c.methods:
                sig = self._format_params(c.name, m)
                out.append(f"{self.c_type(m.return_type)} {c.name}_{m.name}({sig});")

        out.extend(["", "#ifdef __cplusplus", "}", "#endif", f"#endif /* {guard} */"])
        return "\n".join(out)

    def generate_source(self) -> str:
        out = [
            f"/* Auto-generated Pure OOP Spike Unit: {self.module_name} */",
            '#include "spike_rt.h"',
            f'#include "{self.module_name.replace(".", "_")}.h"',
            ""
        ]

        for tr in self.tuple_returns:
            t_name = self.c_type(tr)
            types = tr[6:-1].split(",")
            out.append(f"typedef struct {t_name} {{")
            for idx, item_t in enumerate(types): out.append(f"    {self.c_type(item_t.strip())} _{idx};")
            out.append(f"}} {t_name};\n")

        for c in self.ast.classes:
            out.append(f"static {c.name}_VTable __vt_{c.name} = {{ .__base = {{ NULL, NULL, NULL }} }};\n")

        # Emit Class Methods
        for c in self.ast.classes:
            for m in c.methods:
                if m.is_extern or not m.body: continue
                sig = self._format_params(c.name, m)
                out.append(f"{self.c_type(m.return_type)} {c.name}_{m.name}({sig}) {{")
                for st in m.body: out.append(self._gen_stmt(st, "    "))
                out.append("}\n")

        # Resolve App.main or Main.main to C entry point
        entry_call = None
        if "App" in self.classes and any(m.name == "main" and m.is_static for m in self.classes["App"].methods):
            entry_call = "App_main()"
        elif "Main" in self.classes and any(m.name == "main" and m.is_static for m in self.classes["Main"].methods):
            entry_call = "Main_main()"

        if entry_call and self.module_name == "main":
            out.append("/* Native C Entry Point connecting to Pure OOP Spike Entry */")
            out.append("int main(int argc, char** argv) {")
            out.append("    (void)argc; (void)argv;")
            out.append(f"    return (int){entry_call};")
            out.append("}\n")

        return "\n".join(out)

    def _gen_stmt(self, stmt: Stmt, indent: str) -> str:
        if isinstance(stmt, VarDeclStmt):
            self.var_types[stmt.name] = stmt.type_name
            ct = self.c_type(stmt.type_name)
            if stmt.type_name.startswith("array<"):
                parts = stmt.type_name[6:-1].split(",")
                elem_t = self.c_type(parts[0])
                sz = parts[1]
                return f"{indent}{elem_t} {stmt.name}[{sz}];"
            # Class constructor instantiation
            if stmt.type_name in self.classes and isinstance(stmt.initializer, CallExpr) and isinstance(stmt.initializer.callee, Identifier) and stmt.initializer.callee.name == stmt.type_name:
                args = [self._gen_expr(a) for a in stmt.initializer.args]
                return (
                    f"{indent}{ct} {stmt.name} = ({ct})spike_alloc(sizeof({stmt.type_name}), &__vt_{stmt.type_name});\n"
                    f"{indent}{stmt.type_name}_{stmt.type_name}({', '.join([stmt.name] + args)});"
                )
            # Struct value initialization
            if stmt.type_name in self.structs and isinstance(stmt.initializer, CallExpr) and isinstance(stmt.initializer.callee, Identifier) and stmt.initializer.callee.name == stmt.type_name:
                args = [self._gen_expr(a) for a in stmt.initializer.args]
                return f"{indent}{ct} {stmt.name} = ({ct}){{ {', '.join(args)} }};"

            init_s = f" = {self._gen_expr(stmt.initializer)}" if stmt.initializer else ""
            return f"{indent}{ct} {stmt.name}{init_s};"

        if isinstance(stmt, UnpackVarDeclStmt):
            lines = [f"{indent}{self.c_type(stmt.initializer)} __tmp_unpack = {self._gen_expr(stmt.initializer)};"]
            for idx, name in enumerate(stmt.names):
                self.var_types[name] = stmt.type_names[idx]
                lines.append(f"{indent}{self.c_type(stmt.type_names[idx])} {name} = __tmp_unpack._{idx};")
            return "\n".join(lines)

        if isinstance(stmt, AssignStmt):
            return f"{indent}{self._gen_expr(stmt.target)} {stmt.op} {self._gen_expr(stmt.value)};"
        if isinstance(stmt, ReturnStmt):
            val = f" {self._gen_expr(stmt.value)}" if stmt.value else ""
            return f"{indent}return{val};"
        if isinstance(stmt, BreakStmt): return f"{indent}break;"
        if isinstance(stmt, ContinueStmt): return f"{indent}continue;"
        if isinstance(stmt, ExprStmt): return f"{indent}{self._gen_expr(stmt.expr)};"
        if isinstance(stmt, DisownStmt): return f"{indent}spike_disown({self._gen_expr(stmt.target)});"
        if isinstance(stmt, OwnStmt): return f"{indent}spike_own({self._gen_expr(stmt.target)});"
        if isinstance(stmt, RaiseStmt): return f"{indent}__spike_raise((Object*){self._gen_expr(stmt.exception)});"

        if isinstance(stmt, ForRangeStmt):
            self.var_types[stmt.var_name] = "int"
            lines = [f"{indent}for (int64_t {stmt.var_name} = {self._gen_expr(stmt.start)}; {stmt.var_name} < {self._gen_expr(stmt.stop)}; {stmt.var_name} += {self._gen_expr(stmt.step)}) {{"]
            for s in stmt.body: lines.append(self._gen_stmt(s, indent + "    "))
            lines.append(f"{indent}}}")
            return "\n".join(lines)

        if isinstance(stmt, WhileStmt):
            lines = [f"{indent}while ({self._gen_expr(stmt.condition)}) {{"]
            for s in stmt.body: lines.append(self._gen_stmt(s, indent + "    "))
            lines.append(f"{indent}}}")
            return "\n".join(lines)

        if isinstance(stmt, IfStmt):
            lines = [f"{indent}if ({self._gen_expr(stmt.condition)}) {{"]
            for s in stmt.then_body: lines.append(self._gen_stmt(s, indent + "    "))
            if stmt.else_body:
                lines.append(f"{indent}}} else {{")
                for s in stmt.else_body: lines.append(self._gen_stmt(s, indent + "    "))
            lines.append(f"{indent}}}")
            return "\n".join(lines)

        if isinstance(stmt, TryStmt):
            lines = [
                f"{indent}{{",
                f"{indent}    __SpikeExceptionFrame __frame;",
                f"{indent}    __spike_push_exc_frame(&__frame);",
                f"{indent}    if (setjmp(__frame.jmp) == 0) {{"
            ]
            for s in stmt.body: lines.append(self._gen_stmt(s, indent + "        "))
            lines.append(f"{indent}        __spike_pop_exc_frame();")
            lines.append(f"{indent}    }} else {{")
            lines.append(f"{indent}        __spike_pop_exc_frame();")
            lines.append(f"{indent}        Object* __exc = __frame.active_exception;")
            for h in stmt.handlers:
                lines.append(f"{indent}        if (__exc != NULL) {{")
                if h.var_name: lines.append(f"{indent}            {h.exc_type}* {h.var_name} = ({h.exc_type}*)__exc;")
                for s in h.body: lines.append(self._gen_stmt(s, indent + "            "))
                lines.append(f"{indent}        }}")
            lines.append(f"{indent}    }}")
            if stmt.finally_body:
                lines.append(f"{indent}    /* finally */")
                for s in stmt.finally_body: lines.append(self._gen_stmt(s, indent + "    "))
            lines.append(f"{indent}}}")
            return "\n".join(lines)

        if isinstance(stmt, AsmStmt):
            outs = ", ".join(f'"{o.constraint}"({self._gen_expr(o.variable)})' for o in stmt.outputs)
            ins = ", ".join(f'"{i.constraint}"({self._gen_expr(i.variable)})' for i in stmt.inputs)
            clobs = ", ".join(f'"{c}"' for c in stmt.clobbers)
            return f'{indent}__asm__ __volatile__("{stmt.template}" : {outs} : {ins} : {clobs});'

        raise NotImplementedError(f"Statement {type(stmt)} not implemented")

    def _gen_expr(self, expr: Expr) -> str:
        if isinstance(expr, IntLiteral): return str(expr.value)
        if isinstance(expr, FloatLiteral): return str(expr.value)
        if isinstance(expr, StringLiteral): return f'spike_string_new("{expr.value}")'
        if isinstance(expr, BoolLiteral): return "true" if expr.value else "false"
        if isinstance(expr, Identifier): return expr.name
        if isinstance(expr, UnaryExpr): return f"({expr.op}{self._gen_expr(expr.right)})"
        if isinstance(expr, BinaryExpr): return f"({self._gen_expr(expr.left)} {expr.op} {self._gen_expr(expr.right)})"
        if isinstance(expr, CastExpr): return f"(({self.c_type(expr.to_type)})({self._gen_expr(expr.target)}))"
        if isinstance(expr, SizeofExpr): return f"sizeof({self.c_type(expr.type_name)})"
        if isinstance(expr, LenExpr):
            tgt = self._gen_expr(expr.target)
            return f"(((Object*){tgt})->__vtable == (void*)0 ? ((Slice*){tgt})->length : ((String*){tgt})->length)"
        if isinstance(expr, TypeCheckExpr):
            return f"(((Object*){self._gen_expr(expr.target)})->__type_id == 0)"
        if isinstance(expr, MemberAccessExpr):
            tgt = self._gen_expr(expr.target)
            return f"{tgt}.{expr.member}" if self.var_types.get(tgt) in self.structs else f"{tgt}->{expr.member}"
        if isinstance(expr, IndexAccessExpr):
            tgt = self._gen_expr(expr.target)
            idx = self._gen_expr(expr.index)
            return f"(*({self.c_type(self.var_types.get(tgt, 'int'))}*)__spike_bounds_check({tgt}, {idx}, sizeof({tgt})/sizeof({tgt}[0]), sizeof({tgt}[0])))"
        if isinstance(expr, SliceExpr):
            tgt = self._gen_expr(expr.target)
            st = self._gen_expr(expr.start)
            en = self._gen_expr(expr.end)
            return f"__spike_slice_create({tgt}, {st}, {en}, sizeof({tgt})/sizeof({tgt}[0]), sizeof({tgt}[0]))"
        if isinstance(expr, TupleLiteral):
            args = [f"._{idx} = {self._gen_expr(e)}" for idx, e in enumerate(expr.elements)]
            return f"{{ {', '.join(args)} }}"
        if isinstance(expr, CallExpr):
            # Static Method Call Resolution: ClassName.static_method(...)
            if isinstance(expr.callee, MemberAccessExpr) and isinstance(expr.callee.target, Identifier):
                container = expr.callee.target.name
                method_name = expr.callee.member
                if container in self.classes:
                    args = [self._gen_expr(a) for a in expr.args]
                    return f"{container}_{method_name}({', '.join(args)})"

            # Instance Method Call Resolution: instance.method(...)
            if isinstance(expr.callee, MemberAccessExpr):
                obj_str = self._gen_expr(expr.callee.target)
                method_name = expr.callee.member
                args = [obj_str] + [self._gen_expr(a) for a in expr.args]
                obj_type = self.var_types.get(obj_str, "Object")
                return f"{obj_type}_{method_name}({', '.join(args)})"

            # Struct Value Instantiation: Point(10, 20) -> (Point){ .x = 10, .y = 20 }
            if isinstance(expr.callee, Identifier) and expr.callee.name in self.structs:
                st_name = expr.callee.name
                args = [self._gen_expr(a) for a in expr.args]
                return f"(({st_name}){{ {', '.join(args)} }})"

            callee_name = self._gen_expr(expr.callee)
            args = [self._gen_expr(a) for a in expr.args]
            return f"{callee_name}({', '.join(args)})"

        raise NotImplementedError(f"Expression {type(expr)} not implemented")
