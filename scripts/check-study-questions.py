"""Local independent-source verification. Public reference fetching is explicit URL-only."""
import argparse, os, sys
from pathlib import Path
from vet_pipeline.config import config
from vet_pipeline.private import private_path
from vet_pipeline.question_verification import import_url,run_checks,render
from vet_pipeline.store import Store
from vet_pipeline.util import load_json,write_json
p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
a=sub.add_parser('import-url')
for name in ['url','title','scope']:a.add_argument('--'+name,required=True)
a.add_argument('--directory',type=Path,required=True)
for name in ['run','report']:
 a=sub.add_parser(name);a.add_argument('--workspace',type=Path,required=True);a.add_argument('--config',type=Path);a.add_argument('--force',action='store_true');a.add_argument('--question-id',action='append')
a=p.parse_args();os.umask(0o077)
if a.command=='import-url':import_url(a.url,a.title,a.scope,a.directory);print('Public reference imported locally; no private data sent.')
else:
 store=Store(private_path(a.workspace))
 try:
  cfg=config(a.config)
  if a.command=='run':
   results=run_checks(store,cfg,force=a.force,question_ids=a.question_id)
   print(results)
   from vet_pipeline.publication import review_template
   from vet_pipeline.morning import report
   review_template(store,store.root/'review/publication-candidates.json')
   report(store,cfg,load_json(store.root/'unattended/state.json') if (store.root/'unattended/state.json').exists() else {})
  else:render(store)
 finally:store.close()
 if a.command=='run' and any(x['status']=='deferred' for x in results):sys.exit(75)
