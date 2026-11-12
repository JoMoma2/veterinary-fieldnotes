"""Refresh only the already selected public medical-reference URLs; no clinical input."""
import argparse
import json
from pathlib import Path
from vet_pipeline.config import config
from vet_pipeline.question_verification import refresh_sources

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, required=True)
args = parser.parse_args()
settings = config(args.config)['question_verification']
results = refresh_sources(settings['references_dir'], settings['refresh_days'])
print(json.dumps({'checked': len(results), 'refreshed': sum(r['status'] == 'refreshed' for r in results),
                  'unavailable': sum(r['status'] == 'unavailable' for r in results)}))
