import ast
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT_NAME = "kavzi_trader"
_SOURCE_DIR = Path(__file__).resolve().parent.parent / _ROOT_NAME

FORBIDDEN_EDGES = [
    ("spine", "brain"),
    ("brain", "spine"),
    ("spine", "ui"),
    ("events", "spine"),
    ("evals", "ui"),
    ("evals", "cli"),
]
DOMAIN_ALLOWED = {"domain", "commons"}


class ImportGraph:
    """Package-level import graph over the top-level kavzi_trader packages."""

    def __init__(self, source_dir: Path) -> None:
        self.edges: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for path in sorted(source_dir.rglob("*.py")):
            relative = path.relative_to(source_dir)
            if len(relative.parts) < 2:
                continue
            self._collect(relative.parts[0], path, relative.as_posix())

    def _collect(self, package: str, path: Path, label: str) -> None:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            for target in self._imported_packages(node):
                if target != package:
                    self.edges[package][target].append(f"{label}:{node.lineno}")

    @staticmethod
    def _imported_packages(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Import):
            parts_list = [alias.name.split(".") for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split(".")
            if parts == [_ROOT_NAME]:
                parts_list = [[_ROOT_NAME, alias.name] for alias in node.names]
            else:
                parts_list = [parts]
        else:
            return []
        return [p[1] for p in parts_list if p[0] == _ROOT_NAME and len(p) > 1]

    def find_cycle(self) -> list[str] | None:
        visiting: list[str] = []
        done: set[str] = set()

        def visit(package: str) -> list[str] | None:
            if package in visiting:
                return [*visiting[visiting.index(package) :], package]
            if package in done:
                return None
            visiting.append(package)
            for target in sorted(self.edges.get(package, {})):
                cycle = visit(target)
                if cycle:
                    return cycle
            visiting.pop()
            done.add(package)
            return None

        for package in sorted(self.edges):
            cycle = visit(package)
            if cycle:
                return cycle
        return None


@pytest.fixture(scope="module")
def graph() -> ImportGraph:
    return ImportGraph(_SOURCE_DIR)


class TestImportLayers:
    def test_no_package_cycles(self, graph: ImportGraph) -> None:
        cycle = graph.find_cycle()
        assert cycle is None, f"package import cycle: {' -> '.join(cycle or [])}"

    @pytest.mark.parametrize(("source", "target"), FORBIDDEN_EDGES)
    def test_forbidden_edge_absent(
        self, graph: ImportGraph, source: str, target: str
    ) -> None:
        sites = graph.edges.get(source, {}).get(target, [])
        assert not sites, f"{source} must not import {target}: {sites}"

    def test_domain_depends_only_on_commons(self, graph: ImportGraph) -> None:
        extra = {
            target: sites
            for target, sites in graph.edges.get("domain", {}).items()
            if target not in DOMAIN_ALLOWED
        }
        assert not extra, f"domain may only import commons: {extra}"
