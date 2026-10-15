"""Smoke tests: the package imports and the layer layout exists."""

import importlib
import importlib.util

import pytest

import openfactory


def test_package_imports():
    assert openfactory is not None


@pytest.mark.parametrize("layer", ["domain", "ports", "adapters", "app"])
def test_layer_packages_import(layer):
    assert importlib.import_module(f"openfactory.{layer}") is not None


def test_gates_package_is_removed():
    assert importlib.util.find_spec("openfactory.gates") is None
