import argparse, os, ast, re, subprocess, shutil, datetime
from clang.cindex import Index, Config, CursorKind
from rich.console import Console
from rich.panel import Panel

console = Console()

BIN_OPS = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.Mod: '%'}
CMP_OPS = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}
BOOL_OPS = {ast.And: '&&', ast.Or: '||'}
UNARY_OPS = {ast.Not: '!'}

lib_classes = set()
comment_map = {}

def detect_lib_imports(py_file):
    with open(py_file) as f:
        for line in f:
            m = re.match(r'from lib\.(\w+) import (\w+)', line)
            if m:
                lib_classes.add(m.group(2))

def parse_header(header_file):
    index = Index.create()
    return index.parse(header_file, args=['-x', 'c++', '-std=c++11'])

def cpp_type_to_py(cpp_type):
    if cpp_type in ["int", "long", "short", "unsigned int", "uint8_t"]:
        return "int"
    if cpp_type in ["float", "double"]:
        return "float"
    if cpp_type == "bool":
        return "bool"
    if cpp_type == "char*":
        return "str"
    return "Any"

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
            used = {}
            for m in cls['methods']:
                used.setdefault(m['name'], []).append(m)
            for name, overloads in used.items():
                if name == cls['name']:
                    chosen = next((m for m in overloads if m["args"]), overloads[0])
                    args = ", ".join(f"{a}: {t}" for a, t in chosen["args"])
                    f.write(f"    def __init__(self, {args}):\n        pass\n")
                else:
                    m = overloads[0]
                    args = ", ".join(f"{a}: {t}" for a, t in m["args"])
                    f.write(f"    def {name}(self, {args}):\n        pass\n")
            f.write("\n")

def convert_header(header_file):
    out_dir = "lib"
    os.makedirs(out_dir, exist_ok=True)
    py_file = os.path.join(out_dir, os.path.splitext(os.path.basename(header_file))[0] + ".py")
    tu = parse_header(header_file)
    generate_python_stub(extract_classes(tu), py_file)

def load_comments(source):
    with open(source) as f:
        for i, line in enumerate(f.readlines()):
            if "#" in line:
                c = line.split("#",1)[1].strip()
                if c:
                    comment_map[i+1] = c

def py_expr_to_cpp(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "sleep" and node.func.value.id == "time":
            arg = py_expr_to_cpp(node.args[0])
            return f"delay({int(float(arg))*1000})" if arg.isdigit() else f"delay({arg}*1000)"
    if isinstance(node, ast.BinOp):
        return f"({py_expr_to_cpp(node.left)} {BIN_OPS[type(node.op)]} {py_expr_to_cpp(node.right)})"
    if isinstance(node, ast.UnaryOp):
        return f"({UNARY_OPS[type(node.op)]}{py_expr_to_cpp(node.operand)})"
    if isinstance(node, ast.BoolOp):
        return "(" + f" {BOOL_OPS[type(node.op)]} ".join(py_expr_to_cpp(v) for v in node.values) + ")"
    if isinstance(node, ast.Compare):
        return f"({py_expr_to_cpp(node.left)} {CMP_OPS[type(node.ops[0])]} {py_expr_to_cpp(node.comparators[0])})"
    if isinstance(node, ast.Call):
        func = node.func
        args = ", ".join(py_expr_to_cpp(a) for a in node.args)
        if isinstance(func, ast.Attribute):
            return f"{func.value.id}.{func.attr}({args})"
        return f"{func.id}({args})"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return "0"

def emit_comment(lineno, lines, indent=0):
    if lineno in comment_map:
        ind = "    " * indent
        lines.append(f"{ind}// {comment_map[lineno]}")

def py_stmt_to_cpp(node, indent=0):
    lines = []
    emit_comment(node.lineno, lines, indent)
    ind = "    " * indent
    if isinstance(node, ast.Assign):
        t = node.targets[0]
        v = node.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in lib_classes:
            args = ", ".join(py_expr_to_cpp(a) for a in v.args)
            lines.append(f"{v.func.id} {t.id}({args});")
            return lines
        lines.append(f"{ind}{t.id} = {py_expr_to_cpp(v)};")
        return lines
    if isinstance(node, ast.Expr):
        lines.append(f"{ind}{py_expr_to_cpp(node.value)};")
        return lines
    if isinstance(node, ast.If):
        lines.append(f"{ind}if {py_expr_to_cpp(node.test)} {{")
        for n in node.body: lines += py_stmt_to_cpp(n, indent+1)
        if node.orelse:
            lines.append(f"{ind}}} else {{")
            for n in node.orelse: lines += py_stmt_to_cpp(n, indent+1)
        lines.append(f"{ind}}}")
        return lines
    if isinstance(node, ast.While):
        lines.append(f"{ind}while {py_expr_to_cpp(node.test)} {{")
        for n in node.body: lines += py_stmt_to_cpp(n, indent+1)
        lines.append(f"{ind}}}")
        return lines
    if isinstance(node, ast.For):
        it = node.iter
        if isinstance(it, ast.Call) and getattr(it.func, "id", "")=="range":
            args = it.args
            start, end = ("0", py_expr_to_cpp(args[0])) if len(args)==1 else (py_expr_to_cpp(args[0]), py_expr_to_cpp(args[1]))
            var = node.target.id
            lines.append(f"{ind}for (int {var}={start}; {var}<{end}; {var}++) {{")
            for n in node.body: lines += py_stmt_to_cpp(n, indent+1)
            lines.append(f"{ind}}}")
            return lines
    if isinstance(node, ast.FunctionDef):
        emit_comment(node.lineno, lines, indent)
        lines.append(f"{ind}void {node.name}() {{")
        for n in node.body: lines += py_stmt_to_cpp(n, indent+1)
        lines.append(f"{ind}}}")
        return lines
    return lines

def detect_headers(py_file):
    headers = set()
    with open(py_file) as f:
        for line in f:
            m = re.match(r'from lib\.(\w+) import', line)
            if m: headers.add(m.group(1) + ".h")
    return list(headers)

def to_ino(py_file, auto_loop=False, for_upload=False):
    detect_lib_imports(py_file)
    load_comments(py_file)
    headers = detect_headers(py_file)
    with open(py_file) as f:
        tree = ast.parse(f.read())
    func_defs = {}
    other = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            func_defs[n.name] = py_stmt_to_cpp(n)
        elif not isinstance(n, (ast.Import, ast.ImportFrom)):
            other += py_stmt_to_cpp(n)
    if "setup" not in func_defs: func_defs["setup"] = ["void setup() {}"]
    if "loop" not in func_defs: func_defs["loop"] = ["void loop() {}"]
    out_file = os.path.splitext(py_file)[0] + ".ino"
    with open(out_file, "w") as f:
        for h in headers: f.write(f'#include "{h}"\n')
        f.write("\n")
        for s in other: f.write(s + "\n")
        f.write("\n")
        for fn in func_defs.values():
            for l in fn: f.write(l + "\n")
    console.print(Panel(f"OK: {py_file} → {out_file}"))
    return out_file, headers

def list_ports():
    cli = os.path.join(os.getcwd(), "deps", "arduino-cli.exe")
    console.print(subprocess.run([cli, "board", "list"], capture_output=True, text=True).stdout)

def setup_avr():
    cli = os.path.join(os.getcwd(), "deps", "arduino-cli.exe")
    console.print(subprocess.run([cli, "core", "install", "arduino:avr"], capture_output=True, text=True).stdout)

def log_upload(sketch, text):
    d = os.path.join(sketch, "logs")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
    with open(f, "w") as x: x.write(text)
    return f

def upload(py_file, auto_loop=False, port=None, fqbn="arduino:avr:uno"):
    ino, headers = to_ino(py_file, auto_loop=auto_loop, for_upload=True)
    ino_name = os.path.splitext(os.path.basename(ino))[0]
    base = os.path.dirname(py_file)
    sketch = os.path.join(base, ino_name)
    if os.path.exists(sketch): shutil.rmtree(sketch)
    os.makedirs(sketch, exist_ok=True)
    shutil.move(ino, os.path.join(sketch, ino_name + ".ino"))
    for h in headers:
        hh = os.path.join(base, "lib", h)
        cc = os.path.join(base, "lib", h.replace(".h", ".cpp"))
        if os.path.exists(hh): shutil.copy(hh, sketch)
        if os.path.exists(cc): shutil.copy(cc, sketch)
    cli = os.path.join(os.getcwd(), "deps", "arduino-cli.exe")
    if not port:
        r = subprocess.run([cli, "board", "list"], capture_output=True, text=True).stdout.splitlines()
        for line in r:
            if "COM" in line: port = line.split()[0]; break
    c = subprocess.run([cli, "compile", "--fqbn", fqbn, "."], cwd=sketch, capture_output=True, text=True)
    u = subprocess.run([cli, "upload", "-p", port, "--fqbn", fqbn, "."], cwd=sketch, capture_output=True, text=True)
    log_upload(sketch, c.stdout + c.stderr + u.stdout + u.stderr)
    if c.returncode==0 and u.returncode==0: console.print("[green]Upload success[/green]")
    else: console.print("[red]Upload failed[/red]")

def create_project(name):
    root = os.path.join(os.getcwd(), name)
    if not os.path.exists(root):
        os.makedirs(os.path.join(root, "lib"), exist_ok=True)
        os.makedirs(os.path.join(root, "deps"), exist_ok=True)
        with open(os.path.join(root, "main.py"), "w") as f:
            f.write("from lib.CheapStepper import CheapStepper\n\ndef setup(): pass\n\ndef loop(): pass\n")

def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    a = sp.add_parser("convert-header"); a.add_argument("header"); a.add_argument("--libclang")
    b = sp.add_parser("to-ino"); b.add_argument("pyfile"); b.add_argument("--auto-loop", action="store_true")
    sp.add_parser("setupavr")
    d = sp.add_parser("upload"); d.add_argument("pyfile"); d.add_argument("--auto-loop", action="store_true"); d.add_argument("--port"); d.add_argument("--list-ports", action="store_true"); d.add_argument("--fqbn", default="arduino:avr:uno")
    e = sp.add_parser("create"); e.add_argument("name")
    args = p.parse_args()
    if args.cmd=="convert-header": Config.set_library_file(args.libclang if args.libclang else os.path.join(os.getcwd(),"deps","libclang.dll")); convert_header(args.header)
    elif args.cmd=="to-ino": to_ino(args.pyfile, auto_loop=args.auto_loop)
    elif args.cmd=="setupavr": setup_avr()
    elif args.cmd=="upload": list_ports() if args.list_ports else upload(args.pyfile, auto_loop=args.auto_loop, port=args.port, fqbn=args.fqbn)
    elif args.cmd=="create": create_project(args.name)
    else: p.print_help()

if __name__ == "__main__":
    main()
    