"""Isolated whole-night local Qwen extraction; never transcribes or publishes."""
import argparse
from pathlib import Path
from vet_pipeline import shift_context
from vet_pipeline.runner import ProcessingDeferred

p = argparse.ArgumentParser(description=__doc__)
sub = p.add_subparsers(dest='command', required=True)
a = sub.add_parser('prepare')
a.add_argument('--source-workspace', type=Path, required=True)
a.add_argument('--shift-id', required=True)
a.add_argument('--directory', type=Path, required=True)
a.add_argument('--config', type=Path, required=True)
for name in ['run', 'report', 'watch-report']:
    sub.add_parser(name).add_argument('directory', type=Path)
args = p.parse_args()
try:
    if args.command == 'prepare':
        print(shift_context.prepare(args.source_workspace, args.shift_id, args.directory, args.config))
    elif args.command == 'run':
        shift_context.run(args.directory)
    elif args.command == 'watch-report':
        shift_context.watch_reports(args.directory)
    else:
        print(shift_context.render(args.directory))
except ProcessingDeferred:
    print('Shared resources unavailable; checkpoints retained for automatic retry.')
    raise SystemExit(75)
except Exception as error:
    print('Experiment stopped:', type(error).__name__, '— private checkpoints and report are retained.')
    raise SystemExit(1)
