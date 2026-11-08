"""Local-only voice reference. Never imports a clinical job or updates shift labels."""
import argparse
from pathlib import Path
from vet_pipeline import voice_reference

p = argparse.ArgumentParser(description=__doc__)
sub = p.add_subparsers(dest='command', required=True)
a = sub.add_parser('prepare'); a.add_argument('source', type=Path); a.add_argument('--directory', type=Path, required=True); a.add_argument('--library-workspace', type=Path, required=True)
a = sub.add_parser('inspect'); a.add_argument('directory', type=Path); a.add_argument('--models', type=Path, required=True); a.add_argument('--compare', type=Path)
a = sub.add_parser('confirm-owner-only'); a.add_argument('directory', type=Path)
a = sub.add_parser('calibration'); a.add_argument('directory', type=Path); a.add_argument('--compare', type=Path, required=True); a.add_argument('--models', type=Path, required=True); a.add_argument('--clips', type=int, default=12)
a = sub.add_parser('evaluate'); a.add_argument('directory', type=Path); a.add_argument('--labels', type=Path, required=True)
args = p.parse_args()
if args.command == 'prepare':
    print(voice_reference.prepare(args.source, args.directory, args.library_workspace))
elif args.command == 'inspect':
    voice_reference.inspect(args.directory, args.models, args.compare)
elif args.command == 'confirm-owner-only':
    voice_reference.confirm_owner_only(args.directory)
elif args.command == 'calibration':
    from vet_pipeline.voice_calibration import prepare
    print(prepare(args.directory, args.compare, args.models, args.clips))
elif args.command == 'evaluate':
    from vet_pipeline.voice_calibration import evaluate
    print(evaluate(args.directory, args.labels))
print('Private voice-reference artifacts saved; no shift labels or knowledge records changed.')
