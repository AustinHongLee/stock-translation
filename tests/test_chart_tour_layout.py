import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_chart_tour_callout_geometry_harness() -> None:
    subprocess.run(
        ["node", str(ROOT / "tests" / "chart_tour_layout_test.js")],
        cwd=ROOT,
        check=True,
    )
