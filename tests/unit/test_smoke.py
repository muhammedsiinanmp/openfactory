"""Smoke tests: the package imports and the layer layout exists."""

import importlib

import pytest

import openfactory


def test_package_imports():
    assert openfactory is not None


@pytest.mark.parametrize("layer", ["domain", "ports", "adapters", "app", "gates"])
def test_layer_packages_import(layer):
    assert importlib.import_module(f"openfactory.{layer}") is not None