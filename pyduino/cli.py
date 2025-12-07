import argparse, os, ast, re, subprocess, shutil, datetime
from clang.cindex import Index, Config, CursorKind
from rich.console import Console
from rich.panel import Panel

console = Console()

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

def parse_header(header_file):
    index = Index.create()
    return index.parse(header_file, args=['-x', 'c++', '-std=c++11'])

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
                if name == cls['name']:
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
    console.print(f"[green]Python stub → {out_file}[/green]")

def convert_header(header_file):
    out_dir = "lib"
    os.makedirs(out_dir, exist_ok=True)
    py_file = os.path.join(out_dir, os.path.splitext(os.path.basename(header_file))[0] + ".py")
    tu = parse_header(header_file)
    classes = extract_classes(tu)
    generate_python_stub(classes, py_file)

BIN_OPS = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.FloorDiv: '/', ast.Mod: '%', ast.Pow: '**'}
CMP_OPS = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}
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
        return f"({py_expr_to_cpp(node.left)} {CMP_OPS[type(node.ops[0])]} {py_expr_to_cpp(node.comparators[0])})"
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
    return "0"

def py_stmt_to_cpp(node, indent=0, raw_lines=None):
    ind = "    " * indent
    lines = []
    if isinstance(node, ast.Assign):
        code = f"{ind}{node.targets[0].id} = {py_expr_to_cpp(node.value)};"
    elif isinstance(node, ast.AugAssign):
        code = f"{ind}{node.target.id} {BIN_OPS[type(node.op)]}= {py_expr_to_cpp(node.value)};"
    elif isinstance(node, ast.Expr):
        code = f"{ind}{py_expr_to_cpp(node.value)};"
    elif isinstance(node, ast.If):
        code = f"{ind}if {py_expr_to_cpp(node.test)} {{"
        lines.append((node.lineno, code))
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1, raw_lines))
        if node.orelse:
            lines.append((node.lineno, f"{ind}}} else {{"))
            for n in node.orelse:
                lines.extend(py_stmt_to_cpp(n, indent+1, raw_lines))
        lines.append((node.lineno, f"{ind}}}"))
        return lines
    elif isinstance(node, ast.While):
        code = f"{ind}while {py_expr_to_cpp(node.test)} {{"
        lines.append((node.lineno, code))
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1, raw_lines))
        lines.append((node.lineno, f"{ind}}}"))
        return lines
    elif isinstance(node, ast.For):
        if isinstance(node.iter, ast.Call) and getattr(node.iter.func, "id", "")=="range":
            args = node.iter.args
            start, end = ("0", py_expr_to_cpp(args[0])) if len(args)==1 else (py_expr_to_cpp(args[0]), py_expr_to_cpp(args[1]))
            var = node.target.id
            code = f"{ind}for (int {var}={start}; {var}<{end}; {var}++) {{"
            lines.append((node.lineno, code))
            for n in node.body:
                lines.extend(py_stmt_to_cpp(n, indent+1, raw_lines))
            lines.append((node.lineno, f"{ind}}}"))
            return lines
        code = ind
    elif isinstance(node, ast.FunctionDef):
        args = ", ".join(f"auto {a.arg}" for a in node.args.args)
        code = f"{ind}void {node.name}({args}) {{"
        lines.append((node.lineno, code))
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1, raw_lines))
        lines.append((node.lineno, f"{ind}}}"))
        return lines
    else:
        code = ind
    lines.append((node.lineno, code))
    return lines

def detect_headers(py_file):
    headers = set()
    with open(py_file) as f:
        for line in f:
            m = re.match(r'from lib\.(\w+) import', line)
            if m:
                headers.add(m.group(1) + ".h")
    return list(headers)

def to_ino(py_file, auto_loop=False):
    raw = open(py_file).read().splitlines()
    tree = ast.parse("\n".join(raw))
    func_defs = {}
    body_lines = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            func_defs[node.name] = py_stmt_to_cpp(node, raw_lines=raw)
        elif not isinstance(node, (ast.Import, ast.ImportFrom)):
            body_lines.extend(py_stmt_to_cpp(node, raw_lines=raw))
    if "setup" not in func_defs:
        func_defs["setup"] = [(0, "void setup() {}")]
    if "loop" not in func_defs:
        if auto_loop:
            calls = [f"{n}();" for n in func_defs if n not in ("setup","loop")]
            func_defs["loop"] = [(0, "void loop() {")] + [(0, c) for c in calls] + [(0, "}")] 
        else:
            func_defs["loop"] = [(0, "void loop() {}")]
    out_file = os.path.splitext(py_file)[0] + ".ino"
    with open(out_file, "w") as f:
        for lineno, code in body_lines:
            if 1 <= lineno <= len(raw) and "#" in raw[lineno-1]:
                c = raw[lineno-1].split("#",1)[1].strip()
                if code.strip():
                    f.write(code + " //" + c + "\n")
                else:
                    f.write("// " + c + "\n")
            else:
                f.write(code + "\n")
        for name, block in func_defs.items():
            for lineno, code in block:
                if 1 <= lineno <= len(raw) and "#" in raw[lineno-1]:
                    c = raw[lineno-1].split("#",1)[1].strip()
                    if code.strip():
                        f.write(code + " //" + c + "\n")
                    else:
                        f.write("// " + c + "\n")
                else:
                    f.write(code + "\n")
    console.print(Panel(f"Transpiled {py_file} → {out_file}"))
    return out_file, detect_headers(py_file)

def list_ports():
    cli = os.path.join(os.getcwd(), "deps", "arduino-cli.exe")
    result = subprocess.run([cli, "board", "list"], capture_output=True, text=True)
    console.print(result.stdout)

def setup_avr():
    cli = os.path.join(os.getcwd(), "deps", "arduino-cli.exe")
    result = subprocess.run([cli, "core", "install", "arduino:avr"], capture_output=True, text=True)
    console.print(result.stdout)

def log_upload(sketch_dir, content):
    log_dir = os.path.join(sketch_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
    with open(log_file, "w") as f:
        f.write(content)
    return log_file

def upload(py_file, auto_loop=False, port=None, fqbn="arduino:avr:uno"):
    ino_file, headers = to_ino(py_file, auto_loop=auto_loop)
    ino_name = os.path.splitext(os.path.basename(ino_file))[0]
    base_dir = os.path.dirname(py_file)
    sketch_dir = os.path.join(base_dir, ino_name)
    if os.path.exists(sketch_dir):
        try:
            shutil.rmtree(sketch_dir)
        except:
            pass
    os.makedirs(sketch_dir, exist_ok=True)
    target_ino = os.path.join(sketch_dir, f"{ino_name}.ino")
    shutil.move(ino_file, target_ino)
    lib_dir = os.path.join(base_dir, "lib")
    for h in headers:
        src_h = os.path.join(lib_dir, h)
        src_cpp = os.path.join(lib_dir, h.replace(".h", ".cpp"))
        if os.path.exists(src_h):
            shutil.copy(src_h, sketch_dir)
        if os.path.exists(src_cpp):
            shutil.copy(src_cpp, sketch_dir)
    cli = os.path.join(os.getcwd(), "deps", "arduino-cli.exe")
    if not port:
        result = subprocess.run([cli, "board", "list"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "COM" in line:
                port = line.split()[0]
                break
    compile_result = subprocess.run([cli, "compile", "--fqbn", fqbn, "."], cwd=sketch_dir, capture_output=True, text=True)
    log_upload(sketch_dir, compile_result.stdout + compile_result.stderr)
    upload_result = subprocess.run([cli, "upload", "-p", port, "--fqbn", fqbn, "."], cwd=sketch_dir, capture_output=True, text=True)
    log_upload(sketch_dir, upload_result.stdout + upload_result.stderr)
    if compile_result.returncode==0 and upload_result.returncode==0:
        console.print("[green]Upload success[/green]")
    else:
        console.print("[red]Upload failed[/red]")
        
def create_project(name):
    root = os.path.join(os.getcwd(), name)
    if os.path.exists(root):
        return
    os.makedirs(os.path.join(root, "lib"), exist_ok=True)
    os.makedirs(os.path.join(root, "deps"), exist_ok=True)
    with open(os.path.join(root, "main.py"), "w") as f:
        f.write("from lib.CheapStepper import CheapStepper\n\ndef setup(): pass\n\ndef loop(): pass\n")

def main():
    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers(dest="cmd")
    a = sp.add_parser("convert-header"); a.add_argument("header"); a.add_argument("--libclang")
    b = sp.add_parser("to-ino"); b.add_argument("pyfile"); b.add_argument("--auto-loop", action="store_true")
    c = sp.add_parser("setupavr")
    d = sp.add_parser("upload"); d.add_argument("pyfile"); d.add_argument("--auto-loop", action="store_true"); d.add_argument("--port"); d.add_argument("--list-ports", action="store_true"); d.add_argument("--fqbn", default="arduino:avr:uno")
    e = sp.add_parser("create"); e.add_argument("name")
    args = parser.parse_args()
    if args.cmd=="convert-header":
        libclang = os.path.join(os.getcwd(),"deps","libclang.dll")
        if args.libclang: Config.set_library_file(args.libclang)
        else: Config.set_library_file(libclang)
        convert_header(args.header)
    elif args.cmd=="to-ino":
        to_ino(args.pyfile, auto_loop=args.auto_loop)
    elif args.cmd=="setupavr":
        setup_avr()
    elif args.cmd=="upload":
        if args.list_ports: list_ports()
        else: upload(args.pyfile, auto_loop=args.auto_loop, port=args.port, fqbn=args.fqbn)
    elif args.cmd=="create":
        create_project(args.name)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
    