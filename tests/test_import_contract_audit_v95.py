from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOTS = {"config", "services", "utils", "views", "ui"}


def _production_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if "tests" in relative.parts or "__pycache__" in relative.parts:
            continue
        if relative.name == "__init__.py":
            module = ".".join(relative.parts[:-1])
        else:
            module = ".".join(relative.with_suffix("").parts)
        modules[module] = path
    return modules


def _top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()

    def collect(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        names.add(alias.asname or alias.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for child in ast.walk(target):
                        if isinstance(child, ast.Name):
                            names.add(child.id)
            elif isinstance(node, (ast.Try, ast.If, ast.With)):
                collect(list(getattr(node, "body", [])))
                collect(list(getattr(node, "orelse", [])))
                collect(list(getattr(node, "finalbody", [])))
                for handler in getattr(node, "handlers", []):
                    collect(list(handler.body))

    collect(list(tree.body))
    return names


def test_every_local_from_import_resolves() -> None:
    modules = _production_modules()
    packages: set[str] = set()
    for module in modules:
        parts = module.split(".")
        for index in range(1, len(parts)):
            packages.add(".".join(parts[:index]))

    exports = {module: _top_level_names(path) for module, path in modules.items()}
    failures: list[str] = []

    for importer, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                source = node.module or ""
                if source not in modules and source not in packages:
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    submodule = f"{source}.{alias.name}"
                    if source in modules:
                        valid = alias.name in exports[source] or submodule in modules or submodule in packages
                    else:
                        valid = submodule in modules or submodule in packages
                    if not valid:
                        failures.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} imports missing "
                            f"{source}.{alias.name}"
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    if top_level in PACKAGE_ROOTS and alias.name not in modules and alias.name not in packages:
                        failures.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} imports missing module {alias.name}"
                        )

    assert not failures, "\n".join(failures)



def test_top_level_local_import_graph_has_no_cycles() -> None:
    modules = _production_modules()
    packages: set[str] = set()
    for module in modules:
        parts = module.split(".")
        for index in range(1, len(parts)):
            packages.add(".".join(parts[:index]))

    graph: dict[str, set[str]] = {module: set() for module in modules}
    for importer, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                source = node.module or ""
                if source in modules:
                    graph[importer].add(source)
                elif source in packages:
                    for alias in node.names:
                        submodule = f"{source}.{alias.name}"
                        if submodule in modules:
                            graph[importer].add(submodule)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in modules:
                        graph[importer].add(alias.name)

    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(module: str) -> None:
        if module in visited:
            return
        if module in visiting:
            cycle_start = trail.index(module)
            cycle = trail[cycle_start:] + [module]
            raise AssertionError("Top-level import cycle: " + " -> ".join(cycle))
        visiting.add(module)
        trail.append(module)
        for dependency in sorted(graph[module]):
            visit(dependency)
        trail.pop()
        visiting.remove(module)
        visited.add(module)

    for module in sorted(modules):
        visit(module)


def test_third_party_imports_are_declared_in_requirements() -> None:
    local_roots = {module.split(".")[0] for module in _production_modules()} | PACKAGE_ROOTS
    imported_roots: set[str] = set()
    for path in _production_modules().values():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported_roots.add(node.module.split(".")[0])

    external = imported_roots - local_roots - set(sys.stdlib_module_names) - {"__future__"}
    requirement_text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower().replace("_", "-")
    package_names = {
        line.split("#", 1)[0].strip().split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].strip()
        for line in requirement_text.splitlines()
        if line.split("#", 1)[0].strip()
    }
    import_to_package = {"streamlit_folium": "streamlit-folium"}
    missing = sorted(
        root for root in external
        if import_to_package.get(root, root.replace("_", "-")) not in package_names
    )
    assert not missing, f"Third-party imports missing from requirements.txt: {missing}"

def test_known_partial_deployment_imports_are_removed() -> None:
    for entrypoint_name in ("app.py", "streamlit_app.py"):
        source = (ROOT / entrypoint_name).read_text(encoding="utf-8")
        assert "from utils.streamlit_utils import user_is_editing" not in source

    for path in _production_modules().values():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "config":
                imported = {alias.name for alias in node.names}
                assert "MANUAL_SERVICE_RECORDS_FILE" not in imported, (
                    f"{path.relative_to(ROOT)} imports MANUAL_SERVICE_RECORDS_FILE directly "
                    "from config instead of the compatibility module"
                )


def test_production_modules_smoke_import_with_streamlit_stub() -> None:
    script = r'''
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

class StubModule(types.ModuleType):
    def __getattr__(self, name):
        value = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, value)
        return value

streamlit = StubModule("streamlit")
streamlit.session_state = {}
streamlit.secrets = {}
streamlit.cache_data = MagicMock(
    side_effect=lambda *args, **kwargs: args[0]
    if args and callable(args[0])
    else (lambda function: function)
)
streamlit.cache_resource = streamlit.cache_data
sys.modules["streamlit"] = streamlit
streamlit_folium = StubModule("streamlit_folium")
streamlit_folium.st_folium = MagicMock()
sys.modules["streamlit_folium"] = streamlit_folium

root = Path.cwd()
modules = []
for path in sorted(root.rglob("*.py")):
    relative = path.relative_to(root)
    if "tests" in relative.parts or relative.name == "__init__.py":
        continue
    modules.append(".".join(relative.with_suffix("").parts))
for module in modules:
    importlib.import_module(module)
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
