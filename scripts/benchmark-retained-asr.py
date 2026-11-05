"""Real or synthetic retained WAVs; strictly private/local, never knowledge export."""
import argparse
import json
from pathlib import Path

from vet_pipeline.asr_comparison import run
from vet_pipeline.evaluation import local_config
from vet_pipeline.runner import ProcessingDeferred


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-workspace', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--authorization-ref', required=True)
    a = p.parse_args()
    try:
        result = run(a.source_workspace, a.output, local_config(a.config), a.authorization_ref)
        print(json.dumps({'status': 'finished', 'completed': result['completed'], 'total': result['total'], 'report': str(a.output / 'index.html')}))
    except ProcessingDeferred as error:
        print(json.dumps({'status': 'deferred', 'reason': str(error)}), flush=True)
        return 75
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': type(error).__name__}), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
