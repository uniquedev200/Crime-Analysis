from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def synthetic_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Lazy fixture: generates synthetic dataset on first use.
    D1 implements synth.generate.generate_all in Wave 1.
    No Gate 0 test may use this fixture."""
    out = tmp_path_factory.mktemp("synth")
    from synth.generate import generate_all

    manifest = generate_all(out, seed=42)
    return manifest
