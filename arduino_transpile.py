import argparse, os, ast, re
from clang.cindex import Index, Config, CursorKind

# -------------------- Helpers --------------------
def cpp_type_to_py(cpp_type):
    if cpp_type in ["int", "long", "short", "unsigned int", "uint8_t"]:
        return "int"
    elif cpp_type in ["float", "double"]:
        return "float"
    elif cpp_type == "bool":
        return "bool"
    elif cpp_type == "char*":
        return "str"
    else:
        return "Any"

# -------------------- Header -> Python --------------------
def parse_header(header_file):
    index = Index.create()
    tu = index.parse(header_file, args=['-x', 'c++', '-std=c++11'])
    return tu

def extract_classes(tu):
    classes = []
    for c in tu.cursor.get_children():
        if c.kind == CursorKind.CLASS_DECL and c.is_definition():
            cls = {"name": c.spelling, "methods": []}
            for m in c.get_children():
                if m.kind in [CursorKind.CXX_METHOD, CursorKind.CONSTRUCTOR]:
                    method = {"name": m.spelling, "args": []}
                    for arg in m.get_arguments():
                        method["args"].append((arg.spelling, cpp_type_to_py(arg.type.spelling)))
                    cls["methods"].append(method)
            classes.append(cls)
    return classes

def generate_python_stub(classes, out_file):
    with open(out_file, "w") as f:
        f.write("from typing import Any\n\n")
        for cls in classes:
            f.write(f"class {cls['name']}:\n")
            method_names = {}
            for method in cls['methods']:
                method_names.setdefault(method['name'], []).append(method)
            for name, overloads in method_names.items():
                if name == cls['name']:  # constructor (__init__)
                    chosen = next((m for m in overloads if m["args"]), overloads[0])
                    args = ", ".join(f"{n}: {t}" for n, t in chosen["args"])
                    f.write(f"    def __init__(self, {args}):\n        ...\n")
                else:
                    if len(overloads) > 1:
                        f.write(f"    def {name}(self, *args: Any):\n        ...\n")
                    else:
                        method = overloads[0]
                        args = ", ".join(f"{n}: {t}" for n, t in method["args"])
                        f.write(f"    def {name}(self, {args}):\n        ...\n")
            if not cls['methods']:
                f.write("    pass\n")
            f.write("\n")
    print(f"✅ Python stub written to {out_file}")

def convert_header(header_file):
    py_file = os.path.splitext(os.path.basename(header_file))[0] + ".py"
    tu = parse_header(header_file)
    classes = extract_classes(tu)
    generate_python_stub(classes, py_file)

# -------------------- Python -> .ino --------------------
BIN_OPS = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/',
           ast.FloorDiv: '/', ast.Mod: '%', ast.Pow: '**'}
CMP_OPS = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=',
           ast.Gt: '>', ast.GtE: '>='}
BOOL_OPS = {ast.And: '&&', ast.Or: '||'}
UNARY_OPS = {ast.Not: '!'}

def py_expr_to_cpp(node):
    if isinstance(node, ast.BinOp):
        return f"({py_expr_to_cpp(node.left)} {BIN_OPS[type(node.op)]} {py_expr_to_cpp(node.right)})"
    elif isinstance(node, ast.UnaryOp):
        return f"({UNARY_OPS[type(node.op)]}{py_expr_to_cpp(node.operand)})"
    elif isinstance(node, ast.BoolOp):
        return "(" + f" {BOOL_OPS[type(node.op)]} ".join(py_expr_to_cpp(v) for v in node.values) + ")"
    elif isinstance(node, ast.Compare):
        left = py_expr_to_cpp(node.left)
        op = CMP_OPS[type(node.ops[0])]
        comp = py_expr_to_cpp(node.comparators[0])
        return f"({left} {op} {comp})"
    elif isinstance(node, ast.Call):
        func = node.func
        args = ", ".join(py_expr_to_cpp(a) for a in node.args)
        if isinstance(func, ast.Attribute):
            return f"{func.value.id}.{func.attr}({args})"
        elif isinstance(func, ast.Name):
            return f"{func.id}({args})"
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return repr(node.value)
    return "/* unsupported */"

def py_stmt_to_cpp(node, indent=0):
    ind = "    " * indent
    lines = []
    if isinstance(node, ast.Assign):
        targets = ", ".join(t.id for t in node.targets)
        val = py_expr_to_cpp(node.value)
        # add #define for constant numbers
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
            lines.append(f"#define {targets} {val}")
        else:
            lines.append(f"{ind}{targets} = {val};")
    elif isinstance(node, ast.AugAssign):
        lines.append(f"{ind}{node.target.id} {BIN_OPS[type(node.op)]}= {py_expr_to_cpp(node.value)};")
    elif isinstance(node, ast.Expr):
        lines.append(f"{ind}{py_expr_to_cpp(node.value)};")
    elif isinstance(node, ast.If):
        lines.append(f"{ind}if {py_expr_to_cpp(node.test)} {{")
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1))
        if node.orelse:
            lines.append(f"{ind}}} else {{")
            for n in node.orelse:
                lines.extend(py_stmt_to_cpp(n, indent+1))
        lines.append(f"{ind}}}")
    elif isinstance(node, ast.While):
        lines.append(f"{ind}while {py_expr_to_cpp(node.test)} {{")
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1))
        lines.append(f"{ind}}}")
    elif isinstance(node, ast.For):
        if isinstance(node.iter, ast.Call) and node.iter.func.id=="range":
            args = node.iter.args
            start, end = ("0", py_expr_to_cpp(args[0])) if len(args)==1 else (py_expr_to_cpp(args[0]), py_expr_to_cpp(args[1]))
            var = node.target.id
            lines.append(f"{ind}for (int {var}={start}; {var}<{end}; {var}++) {{")
            for n in node.body:
                lines.extend(py_stmt_to_cpp(n, indent+1))
            lines.append(f"{ind}}}")
    elif isinstance(node, ast.FunctionDef):
        args = ", ".join(f"auto {a.arg}" for a in node.args.args)
        lines.append(f"{ind}void {node.name}({args}) {{")
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1))
        lines.append(f"{ind}}}")
    elif isinstance(node, ast.Break):
        lines.append(f"{ind}break;")
    elif isinstance(node, ast.Continue):
        lines.append(f"{ind}continue;")
    else:
        lines.append(f"{ind}/* unsupported: {type(node)} */")
    return lines

def detect_headers(py_file):
    headers = set()
    with open(py_file) as f:
        content = f.read()
    for line in content.splitlines():
        m = re.match(r'from (\w+) import', line)
        if m and m.group(1) != "Arduino":
            headers.add(f"{m.group(1)}.h")
    return list(headers)

def to_ino(py_file):
    headers = detect_headers(py_file)
    with open(py_file) as f:
        tree = ast.parse(f.read())

    defines = []
    lines = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            # Only handle single-target constants for #define
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and
                isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float))):
                defines.append(f"#define {node.targets[0].id} {node.value.value}")
            else:
                var = ", ".join(t.id for t in node.targets)
                val = py_expr_to_cpp(node.value)
                lines.append(f"{var} = {val};")

        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            var = node.targets[0].id
            cls = node.value.func.id
            args = ", ".join(py_expr_to_cpp(a) for a in node.value.args)
            lines.append(f"{cls} {var}({args});")

    # Add function bodies
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            lines.extend(py_stmt_to_cpp(node))

    out_file = os.path.splitext(py_file)[0]+".ino"
    with open(out_file, "w") as f:
        # Headers first
        for h in headers:
            f.write(f'#include "{h}"\n')
        f.write("\n")
        # Defines
        for d in defines:
            f.write(d + "\n")
        f.write("\n")
        # Rest of code
        f.write("\n".join(lines))

    print(f"✅ Transpiled {py_file} → {out_file} with headers {headers} and #defines")
    
# -------------------- CLI --------------------
def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    parser_header = subparsers.add_parser("convert-header")
    parser_header.add_argument("header", help=".h Arduino header to convert")
    parser_header.add_argument("--libclang", help="Path to libclang.so")

    parser_ino = subparsers.add_parser("to-ino")
    parser_ino.add_argument("pyfile", help="Python sketch")

    args = parser.parse_args()

    if args.command == "convert-header":
        if args.libclang:
            Config.set_library_file(args.libclang)
        convert_header(args.header)
    elif args.command == "to-ino":
        to_ino(args.pyfile)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
    