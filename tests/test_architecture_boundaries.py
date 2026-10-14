"""Static dependency rules keep domain, use cases and inbound HTTP independent."""
import ast
import sys
from pathlib import Path

from pytest_intent import intent

ROOT = Path(__file__).resolve().parents[1] / "orchestrator"


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = list(path.relative_to(ROOT.parent).parent.parts)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                yield ".".join(package[:len(package) - node.level + 1] + (node.module or "").split("."))
            else:
                yield node.module or ""


@intent("INT-FC-R163")
def test_domain_has_no_application_transport_or_framework_dependency():
    allowed = sys.stdlib_module_names | {"__future__"}
    violations = [(str(path.relative_to(ROOT)), module) for path in (ROOT / "domain").rglob("*.py")
                  for module in imports(path)
                  if not (module == "orchestrator.domain" or module.startswith("orchestrator.domain.") or module.split(".")[0] in allowed)]
    assert violations == []


@intent("INT-FC-R163")
def test_use_cases_and_ports_have_no_concrete_adapter_dependency():
    violations = [(str(path.relative_to(ROOT)), module) for path in (ROOT / "application").rglob("*.py")
                  for module in imports(path) if module.startswith(("orchestrator.adapters", "fastapi", "pydantic"))]
    assert violations == []


@intent("INT-FC-R163")
def test_inbound_adapters_use_contracts_without_outbound_adapters():
    violations = [(str(path.relative_to(ROOT)), module) for path in (ROOT / "adapters/inbound").rglob("*.py")
                  for module in imports(path) if module.startswith(("orchestrator.adapters.outbound", "orchestrator.application.use_cases"))]
    assert violations == []


@intent("INT-FC-R163")
def test_models_and_use_cases_have_one_public_class_per_file():
    violations = []
    for directory in ("domain/model", "domain/exceptions", "application/use_cases", "adapters/inbound/http/models", "adapters/outbound"):
        for path in (ROOT / directory).rglob("*.py"):
            classes = [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body
                       if isinstance(node, ast.ClassDef) and not node.name.startswith("_")]
            if len(classes) > 1:
                violations.append((str(path.relative_to(ROOT)), classes))
    assert violations == []
