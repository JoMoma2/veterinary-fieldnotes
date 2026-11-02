from __future__ import annotations
import json,time
from .extraction import Provider,validate_extraction
from .ingest import transcript_valid
from .util import load_json,write_json,now

def benchmark(cfg,inputs,output,origin='synthetic',authorization_ref=''):
    if origin=='authorized-record' and not authorization_ref:raise ValueError('Authorized benchmark requires a recording/processing authorization reference')
    rows=[]
    for file in inputs:
        t=transcript_valid(load_json(file));start=time.monotonic()
        try:
            data=Provider(cfg).extract(t,[], origin);validate_extraction(data,t)
            gold=load_json(file.with_suffix('.expected.json')) if file.with_suffix('.expected.json').exists() else {}
            text=json.dumps(data).lower();expected=gold.get('must_capture',[]);forbidden=gold.get('must_not_assert',[])
            row={'input':file.name,'valid':True,'seconds':round(time.monotonic()-start,3),'captured_markers':[s for s in expected if s.lower() in text],'missed_markers':[s for s in expected if s.lower() not in text],'forbidden_markers_found':[s for s in forbidden if s.lower() in text],'output':data}
        except Exception as e:row={'input':file.name,'valid':False,'seconds':round(time.monotonic()-start,3),'error':type(e).__name__}
        row['manual_review']={'important_information_captured':None,'important_information_missed':None,'invented_details':None,'clinical_terminology':None,'case_linking':None,'safe_additive_updates':None};rows.append(row)
    report={'at':now(),'provider':cfg['provider']['kind'],'model':cfg['provider']['model'],'warning':'Marker matching is a smoke check, not a medical accuracy score. Human review is required. No 90% capture claim is implied.','results':rows};write_json(output,report);return report
