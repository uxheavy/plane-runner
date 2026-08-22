from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).parents[2]
CREDENTIALS = ROOT / "apps/api/plane/agent/runtime/credentials.py"
RESOLVER = ROOT / "apps/api/bin/plane-agent-runtime-credential-resolver"


def _load_resolver():
    loader = importlib.machinery.SourceFileLoader("test_runtime_resolver", str(RESOLVER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_as_package(name: str):
    package = types.ModuleType(name)
    package.__path__ = [str(CREDENTIALS.parent)]
    sys.modules[name] = package
    try:
        spec = importlib.util.spec_from_file_location(f"{name}.credentials", CREDENTIALS)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(f"{name}.contracts", None)
        sys.modules.pop(f"{name}.credentials", None)
        sys.modules.pop(name, None)


def test_credentials_package_import_keeps_the_budget_constant_owner() -> None:
    module = _load_as_package("test_plane_agent_runtime")

    assert module.RUNTIME_BUDGET_MAX_SECONDS == 3600


def test_standalone_resolver_loader_imports_package_relative_contracts() -> None:
    resolver = _load_resolver()

    module = resolver._load_credentials_module()

    assert module.RUNTIME_BUDGET_MAX_SECONDS == 3600
    assert module.__name__.endswith(".credentials")
