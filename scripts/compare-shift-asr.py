"""Prepare, resume or display an isolated private ASR comparison."""
import argparse
import os
from pathlib import Path
from vet_pipeline.asr_suite import prepare,run,worker,render
from vet_pipeline.runner import ProcessingDeferred
from vet_pipeline.private import private_path
from vet_pipeline.util import now,write_json
import traceback


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','run','worker','report'):
        s=sub.add_parser(name);s.add_argument('--workspace',type=Path,required=True)
        if name=='prepare':
            s.add_argument('--source-workspace',type=Path,required=True)
            s.add_argument('--config',type=Path,required=True)
            s.add_argument('--models',type=Path,required=True)
            s.add_argument('--runtime',type=Path,required=True)
            s.add_argument('--authorization-ref',required=True)
        if name=='worker':s.add_argument('--variant',required=True)
    a=p.parse_args()
    try:
        if a.command=='prepare':prepare(a.source_workspace,a.workspace,a.config,a.models,a.runtime,a.authorization_ref)
        elif a.command=='worker':worker(a.workspace,a.variant)
        elif a.command=='run':run(a.workspace)
        else:render(a.workspace)
    except ProcessingDeferred as error:
        write_json(private_path(a.workspace)/'deferral.json',{'at':now(),'reason':str(error)})
        print('ASR comparison safely queued for shared GPU availability.',flush=True);return 75
    except Exception as error:
        try:
            path=private_path(a.workspace)/'diagnostics/errors.log'
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with path.open('a') as f:f.write(now()+' '+a.command+'\n'+traceback.format_exc()+'\n')
            path.chmod(0o600)
        except (OSError,ValueError):pass
        print('ASR comparison stopped safely: '+type(error).__name__,flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
