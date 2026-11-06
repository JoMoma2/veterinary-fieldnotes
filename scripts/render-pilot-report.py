"""Rebuild a private two-sample report as one portable HTML file with embedded audio."""
import argparse
from pathlib import Path
from vet_pipeline.pilot_report import render_pilot

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('workspace', type=Path)
p.add_argument('--output', type=Path)
a = p.parse_args()
print(render_pilot(a.workspace, a.output))
