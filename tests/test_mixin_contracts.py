import sys
import unittest
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.mixin_contracts import (
    MixinContractError,
    collect_declared_mixin_contracts,
    collect_declared_provider_contracts,
    validate_declared_mixin_contracts,
)


class AlphaMixin:
    REQUIRED_PLUGIN_ATTRS = ("alpha_attr",)
    REQUIRED_PLUGIN_METHODS = ("alpha_method",)


class BetaMixin:
    REQUIRED_PLUGIN_ATTRS = ("beta_attr", "alpha_attr")
    REQUIRED_PLUGIN_METHODS = ("beta_method", "alpha_method")


class ContractHarness(BetaMixin, AlphaMixin):
    alpha_attr = 1
    beta_attr = 2

    def alpha_method(self):
        return None

    def beta_method(self):
        return None


class MissingContractHarness(AlphaMixin):
    pass


class ProviderMixin:
    REQUIRED_PLUGIN_PROVIDERS = ("account", "store")


class ProviderRegistry:
    account = object()
    store = object()


class ProviderContractHarness(ProviderMixin):
    providers = ProviderRegistry()


class MissingProviderContractHarness(ProviderMixin):
    pass


class MixinContractsTests(unittest.TestCase):
    def test_collect_declared_mixin_contracts_merges_without_duplicates(self):
        required_attrs, required_methods = collect_declared_mixin_contracts(ContractHarness)

        self.assertEqual(sorted(required_attrs), ["alpha_attr", "beta_attr"])
        self.assertEqual(sorted(required_methods), ["alpha_method", "beta_method"])

    def test_collect_declared_provider_contracts_merges_provider_names(self):
        required_providers = collect_declared_provider_contracts(ProviderContractHarness)

        self.assertEqual(sorted(required_providers), ["account", "store"])

    def test_validate_declared_mixin_contracts_passes_for_complete_host(self):
        validate_declared_mixin_contracts(ContractHarness())
        validate_declared_mixin_contracts(ProviderContractHarness())

    def test_validate_declared_mixin_contracts_reports_missing_items(self):
        with self.assertRaises(MixinContractError) as error_context:
            validate_declared_mixin_contracts(MissingContractHarness())

        message = str(error_context.exception)
        self.assertIn("alpha_attr", message)
        self.assertIn("alpha_method", message)

    def test_validate_declared_mixin_contracts_reports_missing_providers(self):
        with self.assertRaises(MixinContractError) as error_context:
            validate_declared_mixin_contracts(MissingProviderContractHarness())

        self.assertIn("account", str(error_context.exception))

    def test_runtime_mixins_do_not_require_methods_they_define_themselves(self):
        offenders = []
        for source_path in (PROJECT_ROOT / "steamflow").glob("*.py"):
            module_tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in module_tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                own_methods = {
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                required_methods = set()
                for item in node.body:
                    if not isinstance(item, ast.Assign):
                        continue
                    if not any(isinstance(target, ast.Name) and target.id == "REQUIRED_PLUGIN_METHODS" for target in item.targets):
                        continue
                    try:
                        value = ast.literal_eval(item.value)
                    except (TypeError, ValueError):
                        continue
                    required_methods.update(str(name) for name in value)
                overlap = sorted(own_methods & required_methods)
                if overlap:
                    offenders.append(f"{source_path.name}:{node.name}:{', '.join(overlap)}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
