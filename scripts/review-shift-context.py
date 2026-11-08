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
f = sub.add_parser('prepare-focused')
f.add_argument('reference', type=Path); f.add_argument('directory', type=Path)
f = sub.add_parser('prepare-speakers')
f.add_argument('reference', type=Path); f.add_argument('directory', type=Path)
f = sub.add_parser('run-speakers')
f.add_argument('directory', type=Path); f.add_argument('--models', type=Path, required=True)
f = sub.add_parser('prepare-global-speakers')
f.add_argument('reference', type=Path); f.add_argument('directory', type=Path)
f = sub.add_parser('run-global-speakers')
f.add_argument('directory', type=Path); f.add_argument('--models', type=Path, required=True)
for name in ['run', 'report', 'watch-report', 'run-focused']:
    sub.add_parser(name).add_argument('directory', type=Path)
args = p.parse_args()
try:
    if args.command == 'prepare':
        print(shift_context.prepare(args.source_workspace, args.shift_id, args.directory, args.config))
    elif args.command == 'run':
        shift_context.run(args.directory)
    elif args.command == 'watch-report':
        shift_context.watch_reports(args.directory)
    elif args.command == 'prepare-focused':
        print(shift_context.prepare_focused(args.reference, args.directory))
    elif args.command == 'run-focused':
        shift_context.run_focused_after_reference(args.directory)
    elif args.command == 'prepare-speakers':
        print(shift_context.prepare_speaker_study(args.reference, args.directory))
    elif args.command == 'run-speakers':
        shift_context.run_speaker_study(args.directory, args.models)
    elif args.command == 'prepare-global-speakers':
        root = shift_context.prepare_speaker_study(args.reference, args.directory)
        from vet_pipeline.util import load_json, write_json
        experiment = load_json(root / 'experiment.json')
        experiment.update(version='whole-shift-speakers-global-v2',
                          baselineLabel='Previous fragmented speaker labels — these are NOT current identities')
        write_json(root / 'experiment.json', experiment)
        print(root)
    elif args.command == 'run-global-speakers':
        from vet_pipeline.global_speakers import run_after_reference
        run_after_reference(args.directory, args.models)
    else:
        print(shift_context.render(args.directory))
except ProcessingDeferred:
    print('Shared resources unavailable; checkpoints retained for automatic retry.')
    raise SystemExit(75)
except Exception as error:
    print('Experiment stopped:', type(error).__name__, '— private checkpoints and report are retained.')
    raise SystemExit(1)
