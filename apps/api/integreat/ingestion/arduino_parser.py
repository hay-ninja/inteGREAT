"""Conservative Arduino C/C++ extraction (PRD FR-01).

Extracts functions, call relationships, pin constants, pin-configuring API calls, servo objects,
Serial.print literals (for D-007 log matching) and command literals. Every item carries file:line.
Anything that cannot be resolved statically is kept and marked `unresolved`, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from .repository import RepoFile

_LANG = Language(tree_sitter_cpp.language())

SERVO_TYPES = {"Servo", "ESP32Servo"}
# function name -> index of the pin argument
PIN_FUNCS = {
    "pinMode": 0,
    "digitalWrite": 0,
    "digitalRead": 0,
    "analogWrite": 0,
    "analogRead": 0,
    "ledcAttachPin": 0,
    "ledcAttach": 0,
}
SERVO_PIN_METHODS = {"attach": 0}
SERVO_ACTUATE_METHODS = {"write", "writeMicroseconds"}
SERIAL_PRINT = {"print", "println", "printf"}
COMMAND_MATCH_METHODS = {"startsWith", "equals", "equalsIgnoreCase"}
GPIO_NUM = re.compile(r"^(?:GPIO_NUM_)?(\d+)$")


@dataclass
class FunctionDef:
    id: str  # function:<file>::<name>
    name: str
    file: str
    line_start: int
    line_end: int


@dataclass
class Symbol:
    name: str
    raw_value: str
    file: str
    line: int
    kind: str  # "define" | "const"


@dataclass
class PinUse:
    function_id: str | None
    file: str
    line: int
    api: str  # "servo_attach" | "pinMode" | ...
    call_text: str
    object_name: str | None
    object_type: str | None
    raw_arg: str
    gpio: int | None
    resolution: str  # "literal" | "define" | "const" | "unresolved"
    symbol: Symbol | None = None


@dataclass
class ActuatorCall:
    function_id: str | None
    file: str
    line: int
    object_name: str
    object_type: str
    method: str
    call_text: str


@dataclass
class Call:
    caller_id: str
    callee_name: str
    file: str
    line: int


@dataclass
class Literal:
    function_id: str | None
    text: str
    file: str
    line: int


@dataclass
class ParsedProject:
    functions: list[FunctionDef] = field(default_factory=list)
    symbols: dict[str, Symbol] = field(default_factory=dict)
    objects: dict[str, tuple[str, str, int]] = field(default_factory=dict)  # name -> (type, file, line)
    pin_uses: list[PinUse] = field(default_factory=list)
    actuator_calls: list[ActuatorCall] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    log_literals: list[Literal] = field(default_factory=list)
    command_literals: list[Literal] = field(default_factory=list)
    warnings: list[tuple[str, str, int | None]] = field(default_factory=list)  # (msg, file, line)


def _text(n: Node) -> str:
    return n.text.decode("utf-8", "replace")


def _line(n: Node) -> int:
    return n.start_point[0] + 1


def _string_value(n: Node) -> str | None:
    if n.type != "string_literal":
        return None
    return "".join(_text(c) for c in n.children if c.type in ("string_content", "escape_sequence"))


def _function_name(fn: Node) -> str | None:
    stack = [fn.child_by_field_name("declarator")]
    while stack:
        d = stack.pop()
        if d is None:
            continue
        if d.type == "function_declarator":
            inner = d.child_by_field_name("declarator")
            return _text(inner) if inner is not None else None
        stack.extend(d.children)
    return None


def _walk(n: Node):
    yield n
    for c in n.children:
        yield from _walk(c)


def parse_project(files: list[RepoFile]) -> ParsedProject:
    parser = Parser(_LANG)
    out = ParsedProject()
    trees = [(f, parser.parse(f.text.encode("utf-8"))) for f in files]

    # Pass 1: global symbols, objects, function definitions.
    for f, tree in trees:
        for child in tree.root_node.children:
            if child.type == "preproc_def":
                name, val = child.child_by_field_name("name"), child.child_by_field_name("value")
                if name is not None and val is not None:
                    out.symbols[_text(name)] = Symbol(_text(name), _text(val).strip(), f.rel, _line(child), "define")
            elif child.type == "declaration":
                typ = child.child_by_field_name("type")
                tname = _text(typ) if typ is not None else ""
                is_const = any(c.type == "type_qualifier" and _text(c) in ("const", "constexpr") for c in child.children)
                for d in child.children_by_field_name("declarator"):
                    if d.type == "identifier" and tname in SERVO_TYPES:
                        out.objects[_text(d)] = (tname, f.rel, _line(child))
                    elif d.type == "init_declarator" and is_const:
                        ident, val = d.child_by_field_name("declarator"), d.child_by_field_name("value")
                        if ident is not None and val is not None:
                            out.symbols[_text(ident)] = Symbol(_text(ident), _text(val), f.rel, _line(child), "const")
            elif child.type == "function_definition":
                name = _function_name(child)
                if name:
                    out.functions.append(FunctionDef(
                        id=f"function:{f.rel}::{name}", name=name, file=f.rel,
                        line_start=_line(child), line_end=child.end_point[0] + 1,
                    ))

    known_functions = {fn.name for fn in out.functions}

    # Pass 2: calls inside each function body (and at file scope, rarely).
    for f, tree in trees:
        fn_by_range = [fn for fn in out.functions if fn.file == f.rel]

        def owner(line: int) -> str | None:
            for fn in fn_by_range:
                if fn.line_start <= line <= fn.line_end:
                    return fn.id
            return None

        for node in _walk(tree.root_node):
            if node.type != "call_expression":
                continue
            fn_node = node.child_by_field_name("function")
            args_node = node.child_by_field_name("arguments")
            args = [a for a in (args_node.named_children if args_node else []) if a.type != "comment"]
            line = _line(node)
            fid = owner(line)
            call_text = _text(node)

            if fn_node is not None and fn_node.type == "identifier":
                name = _text(fn_node)
                if name in PIN_FUNCS and len(args) > PIN_FUNCS[name]:
                    out.pin_uses.append(_pin_use(out, fid, f.rel, line, name, call_text, None, None, args[PIN_FUNCS[name]]))
                elif name in known_functions and fid is not None:
                    out.calls.append(Call(fid, name, f.rel, line))

            elif fn_node is not None and fn_node.type == "field_expression":
                obj = fn_node.child_by_field_name("argument")
                field_ = fn_node.child_by_field_name("field")
                if obj is None or field_ is None:
                    continue
                obj_name, method = _text(obj), _text(field_)
                obj_type = out.objects.get(obj_name, (None,))[0]
                if obj_name == "Serial" and method in SERIAL_PRINT and args:
                    s = _string_value(args[0])
                    if s:
                        out.log_literals.append(Literal(fid, s, f.rel, line))
                elif method in COMMAND_MATCH_METHODS and args:
                    s = _string_value(args[0])
                    if s:
                        out.command_literals.append(Literal(fid, s, f.rel, line))
                elif obj_type in SERVO_TYPES and method in SERVO_PIN_METHODS and args:
                    out.pin_uses.append(_pin_use(out, fid, f.rel, line, "servo_attach", call_text, obj_name, obj_type, args[0]))
                elif obj_type in SERVO_TYPES and method in SERVO_ACTUATE_METHODS:
                    out.actuator_calls.append(ActuatorCall(fid, f.rel, line, obj_name, obj_type, method, call_text))
                elif method == "attach" and obj_type is None:
                    out.warnings.append((f"'{obj_name}.attach(...)' on an object of unknown type; not mapped", f.rel, line))
    return out


def _pin_use(out: ParsedProject, fid, file, line, api, call_text, obj_name, obj_type, arg: Node) -> PinUse:
    raw = _text(arg).strip()
    gpio, resolution, sym = _resolve(out, raw)
    if gpio is None:
        out.warnings.append((f"could not statically resolve pin argument '{raw}' in {api}", file, line))
    return PinUse(fid, file, line, api, call_text, obj_name, obj_type, raw, gpio, resolution, sym)


def _resolve(out: ParsedProject, raw: str, depth: int = 0) -> tuple[int | None, str, Symbol | None]:
    m = GPIO_NUM.match(raw)
    if m:
        return int(m.group(1)), "literal", None
    sym = out.symbols.get(raw)
    if sym is None or depth > 3:
        return None, "unresolved", None
    gpio, _, _ = _resolve(out, sym.raw_value, depth + 1)
    if gpio is None:
        return None, "unresolved", sym
    # Report the outermost symbol: that's what the engineer wrote and what they'd edit.
    return gpio, sym.kind, sym
