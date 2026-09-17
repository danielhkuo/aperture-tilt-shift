import numpy as np
import pytest

from sa import synth


@pytest.fixture
def rng():
    return np.random.default_rng(0)


@pytest.fixture
def ring(rng):
    """24 cameras on a 0.2-unit ring around a central reference camera, with hand jitter."""
    return synth.ring_poses(n=24, diameter=0.2, width=640, height=480, f=500.0, jitter_deg=1.5, rng=rng)
