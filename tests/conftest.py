"""Shared pytest fixtures."""
import os
import pytest


@pytest.fixture
def sample_tree(tmp_path):
    """Create a small public-dir tree with text/markdown files for tests."""
    (tmp_path / "study" / "mcat").mkdir(parents=True)
    (tmp_path / "study" / "biochem").mkdir(parents=True)
    (tmp_path / "random").mkdir(parents=True)

    (tmp_path / "study" / "mcat" / "kinematics_notes.txt").write_text(
        "Projectile motion and kinematics. Velocity, acceleration, and the "
        "equations of motion for the MCAT physics section.",
        encoding="utf-8",
    )
    (tmp_path / "study" / "biochem" / "enzymes.md").write_text(
        "# Enzyme kinetics\n\nMichaelis-Menten, Km and Vmax, competitive "
        "inhibition. Important biochemistry for exams.",
        encoding="utf-8",
    )
    (tmp_path / "random" / "grocery.txt").write_text(
        "milk eggs bread coffee bananas", encoding="utf-8",
    )
    return tmp_path
