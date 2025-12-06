import argparse, os, ast, re, subprocess, shutil, datetime
from clang.cindex import Index, Config, CursorKind
from rich.console import Console
from rich.panel import Panel

console = Console()

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
    console.print(f"[green]✅ Python stub written to {out_file}[/green]")

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
            val = func.value.id if isinstance(func.value, ast.Name) else "obj"
            return f"{val}.{func.attr}({args})"
        elif isinstance(func, ast.Name):
            return f"{func.id}({args})"
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return repr(node.value)
    return "0"

def py_stmt_to_cpp(node, indent=0, global_scope=True):
    ind = "    " * indent
    lines = []
    if isinstance(node, ast.Assign):
        # Detect class instantiation
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            cls_name = node.value.func.id
            args = ", ".join(py_expr_to_cpp(a) for a in node.value.args)
            lines.append(f"{cls_name} {node.targets[0].id}({args});")
        # Detect numeric constants
        elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
            lines.append(f"#define {node.targets[0].id} {node.value.value}")
        else:
            lines.append(f"{ind}{node.targets[0].id} = {py_expr_to_cpp(node.value)};")
    elif isinstance(node, ast.AugAssign):
        lines.append(f"{ind}{node.target.id} {BIN_OPS[type(node.op)]}= {py_expr_to_cpp(node.value)};")
    elif isinstance(node, ast.Expr):
        lines.append(f"{ind}{py_expr_to_cpp(node.value)};")
    elif isinstance(node, ast.If):
        lines.append(f"{ind}if {py_expr_to_cpp(node.test)} {{")
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1, False))
        if node.orelse:
            lines.append(f"{ind}}} else {{")
            for n in node.orelse:
                lines.extend(py_stmt_to_cpp(n, indent+1, False))
        lines.append(f"{ind}}}")
    elif isinstance(node, ast.While):
        lines.append(f"{ind}while {py_expr_to_cpp(node.test)} {{")
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1, False))
        lines.append(f"{ind}}}")
    elif isinstance(node, ast.For):
        if isinstance(node.iter, ast.Call) and getattr(node.iter.func, "id", "")=="range":
            args = node.iter.args
            start, end = ("0", py_expr_to_cpp(args[0])) if len(args)==1 else (py_expr_to_cpp(args[0]), py_expr_to_cpp(args[1]))
            var = node.target.id
            lines.append(f"{ind}for (int {var}={start}; {var}<{end}; {var}++) {{")
            for n in node.body:
                lines.extend(py_stmt_to_cpp(n, indent+1, False))
            lines.append(f"{ind}}}")
    elif isinstance(node, ast.FunctionDef):
        args = ", ".join(f"auto {a.arg}" for a in node.args.args)
        lines.append(f"{ind}void {node.name}({args}) {{")
        for n in node.body:
            lines.extend(py_stmt_to_cpp(n, indent+1, False))
        lines.append(f"{ind}}}")
    elif isinstance(node, (ast.Break, ast.Continue)):
        lines.append(f"{ind}{type(node).__name__.lower()};")
    return lines

def detect_headers(py_file):
    headers = set()
    with open(py_file) as f:
        for line in f:
            m = re.match(r'from (\w+) import', line)
            if m and m.group(1) != "Arduino":
                headers.add(f"{m.group(1)}.h")
    return list(headers)

def to_ino(py_file, auto_loop=False):
    headers = detect_headers(py_file)
    with open(py_file) as f:
        tree = ast.parse(f.read())

    func_defs = {}
    other_stmts = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            func_defs[node.name] = py_stmt_to_cpp(node)
        elif not isinstance(node, (ast.Import, ast.ImportFrom)):
            other_stmts.extend(py_stmt_to_cpp(node))

    if "setup" not in func_defs:
        func_defs["setup"] = ["void setup() {}", ""]
    if "loop" not in func_defs:
        if auto_loop:
            loop_body = [f"{name}();" for name in func_defs if name not in ("setup", "loop")]
            func_defs["loop"] = ["void loop() {"] + loop_body + ["}", ""]
        else:
            func_defs["loop"] = ["void loop() {}", ""]

    out_file = os.path.splitext(py_file)[0] + ".ino"
    with open(out_file, "w") as f:
        for h in headers:
            f.write(f'#include "{h}"\n')
        f.write("\n")
        for stmt in other_stmts:
            f.write(stmt + "\n")
        f.write("\n")
        for func in func_defs.values():
            for line in func:
                f.write(line + "\n")
    console.print(Panel(f"[bold green]✅ Transpiled {py_file} → {out_file}[/bold green]\nHeaders: {headers}"))
    return out_file

def list_ports():
    try:
        result = subprocess.run(["arduino-cli", "board", "list"], capture_output=True, text=True)
        console.print("[bold cyan]Connected Arduino boards:[/bold cyan]")
        console.print(result.stdout)
    except FileNotFoundError:
        console.print("[red]❌ arduino-cli not found. Install it first.[/red]")

# -------------------- Upload with Logs --------------------
def log_upload(sketch_dir, content):
    log_dir = os.path.join(sketch_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"upload_{timestamp}.log")
    with open(log_file, "w") as f:
        f.write(content)
    return log_file

def upload(py_file, auto_loop=False, port=None, fqbn="arduino:avr:uno"):
    ino_file = to_ino(py_file, auto_loop=auto_loop)
    ino_name = os.path.splitext(os.path.basename(ino_file))[0]
    sketch_dir = os.path.join(os.path.dirname(ino_file), ino_name)
    if os.path.exists(sketch_dir):
        shutil.rmtree(sketch_dir)
    os.makedirs(sketch_dir)
    target_ino = os.path.join(sketch_dir, f"{ino_name}.ino")
    shutil.move(ino_file, target_ino)

    if not port:
        try:
            result = subprocess.run(["arduino-cli", "board", "list"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 1 and "COM" in parts[0]:
                    port = parts[0]
                    break
            if not port:
                console.print("[red]❌ Could not auto-detect Arduino port. Please specify with --port[/red]")
                return
            console.print(f"[cyan]Auto-detected port:[/cyan] {port}")
        except FileNotFoundError:
            console.print("[red]❌ arduino-cli not found. Install it first.[/red]")
            return

    try:
        console.print(f"[yellow]Compiling {target_ino}...[/yellow]")
        compile_result = subprocess.run(["arduino-cli", "compile", "--fqbn", fqbn, sketch_dir],
                                        capture_output=True, text=True)
        console.print(compile_result.stdout)
        log_file = log_upload(sketch_dir, compile_result.stdout + compile_result.stderr)

        console.print(f"[yellow]Uploading {target_ino} to {port}...[/yellow]")
        upload_result = subprocess.run(["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, sketch_dir],
                                       capture_output=True, text=True)
        console.print(upload_result.stdout)
        log_upload(sketch_dir, upload_result.stdout + upload_result.stderr)

        if compile_result.returncode == 0 and upload_result.returncode == 0:
            console.print(f"[green]✅ Upload successful! Logs saved in {sketch_dir}/logs[/green]")
        else:
            console.print(f"[red]❌ Upload failed! Check logs in {sketch_dir}/logs[/red]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Error during upload: {e}[/red]")

# -------------------- CLI --------------------
def main():
    parser = argparse.ArgumentParser()
    sp = parser.add_subparsers(dest="command")

    header_parser = sp.add_parser("convert-header")
    header_parser.add_argument("header")
    header_parser.add_argument("--libclang")

    ino_parser = sp.add_parser("to-ino")
    ino_parser.add_argument("pyfile")
    ino_parser.add_argument("--auto-loop", action="store_true")

    upload_parser = sp.add_parser("upload")
    upload_parser.add_argument("pyfile")
    upload_parser.add_argument("--auto-loop", action="store_true")
    upload_parser.add_argument("--port")
    upload_parser.add_argument("--list-ports", action="store_true")
    upload_parser.add_argument("--fqbn", default="arduino:avr:uno")

    args = parser.parse_args()
    if args.command == "convert-header":
        if args.libclang:
            Config.set_library_file(args.libclang)
        convert_header(args.header)
    elif args.command == "to-ino":
        to_ino(args.pyfile, auto_loop=args.auto_loop)
    elif args.command == "upload":
        if getattr(args, "list_ports", False):
            list_ports()
        else:
            upload(args.pyfile, auto_loop=args.auto_loop, port=args.port, fqbn=args.fqbn)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
    