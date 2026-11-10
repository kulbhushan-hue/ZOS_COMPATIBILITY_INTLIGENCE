"""Inspect raw vendor page coverage without fetching anything or using the dashboard.
Usage: python inspect_source_cache.py --output exports/deep
"""
from pathlib import Path
from collections import Counter
from argparse import ArgumentParser
import csv
import json
from source_cache_v11 import ResponseCache,describe_document

def main():
    p=ArgumentParser()
    p.add_argument('--output',default='exports/deep')
    a=p.parse_args()
    root=Path(a.output)
    cache=ResponseCache(root/'source_cache')
    docs=[]
    for rec,body in cache.entries():
        item=describe_document(rec['vendor'],rec['url'],rec['content_type'],body,rec['sha256'],'Cached')
        docs.append(item)
    quality={}
    path=root/'vendor_source_quality.csv'
    if path.is_file():
        with path.open(encoding='utf-8-sig',newline='') as stream:
            quality={(x['vendor'],x['url']):x for x in csv.DictReader(stream)}
    for d in docs:
        q=quality.get((d['vendor'],d['url']),{})
        d['quality_class']=q.get('result_class','Not yet parsed')
    output=root/'vendor_cache_inspection.csv'
    output.parent.mkdir(parents=True,exist_ok=True)
    fields=['vendor','url','format','response_sha256','cache_status','bytes','html_tables','table_rows','title','script_tags','potential_dynamic_content','reason','quality_class']
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(docs)
    print(json.dumps({'cached_documents':len(docs),'vendors':dict(Counter(d['vendor'] for d in docs)),
          'quality':dict(Counter(d['quality_class'] for d in docs)),
          'output':str(output)},indent=2))
if __name__=='__main__':main()
