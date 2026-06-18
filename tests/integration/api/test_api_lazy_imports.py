import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_main_import_does_not_load_analysis_heavy_deps():
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
sys.path.insert(0, 'src')
import aicbc.main

# pandas is the primary heavy dependency we removed from analysis routes
assert 'pandas' not in sys.modules, 'pandas loaded at startup'

# Verify analysis heavy modules are not eagerly loaded
analysis_modules = [
    'aicbc.analysis.preprocessing',
    'aicbc.analysis.tasks',
    'aicbc.analysis.simulation.market_simulator',
    'aicbc.analysis.results.segment_comparison',
    'aicbc.analysis.nl_scenario_parser',
    'aicbc.analysis.report_builder',
    'aicbc.analysis.cbc_visualizer',
]
for mod in analysis_modules:
    assert mod not in sys.modules, f'{mod} loaded at startup'

print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr
