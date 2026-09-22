"""Build a standalone business-process document, without loading the application."""
from pathlib import Path
import json
import runpy
import hashlib
import re

HERE=Path(__file__).resolve().parent

def _find_root(p):
    """向上查找仓库根（含 apps/ 与 docker-compose.yml 的目录）。"""
    for parent in [p, *p.parents]:
        if (parent/'apps').is_dir() and (parent/'docker-compose.yml').exists():
            return parent
    return p.parent

ROOT=_find_root(HERE)
D={"title":"智能问答 · 业务流程图","date":"2026-09-20","version":"业务版 2.0","sections":[],"materials":[],"operations":[],"references":[]}

def section(id,title,desc,goal):
    item=dict(id=id,title=title,desc=desc,goal=goal,flows=[],notes=[])
    D['sections'].append(item)
    return item

def flow(s,id,title,trigger,lanes,inputs,outputs,notes=None):
    item=dict(id=id,title=title,trigger=trigger,lanes=lanes,inputs=inputs,outputs=outputs,notes=notes or [],nodes=[],edges=[])
    s['flows'].append(item)
    return item

def node(f,id,lane,row,title,kind='task',detail='',inputs=None,outputs=None,rule='',module='',mode='system',target=''):
    item=dict(id=id,lane=lane,row=row,title=title,kind=kind,detail=detail or title,inputs=inputs or [],outputs=outputs or [],rule=rule,module=module,mode=mode,target=target)
    f['nodes'].append(item)
    return id

def edge(f,a,b,label='',kind='normal'):
    f['edges'].append(dict(a=a,b=b,label=label,kind=kind))

def path(f,*ids):
    for a,b in zip(ids,ids[1:]):edge(f,a,b)

def simple(f,steps):
    for i,step in enumerate(steps):
        lane,title,*rest=step
        node(f,str(i+1),lane,i,title,**(rest[0] if rest else {}))
    path(f,*[str(i+1) for i in range(len(steps))])

context={k:v for k,v in globals().copy().items() if not k.startswith('__')}
for name in ['overview.py','school.py','scores.py','analysis.py','reports.py','chat.py','operations.py']:
    runpy.run_path(str(HERE/name),init_globals=context)

all_flows=[f for s in D['sections'] for f in s['flows']]
flow_ids={f['id'] for f in all_flows}
assert len(flow_ids)==len(all_flows)
for f in all_flows:
    nodes={n['id']:n for n in f['nodes']}
    assert len(nodes)==len(f['nodes']),f['id']
    occupied=set()
    for n in f['nodes']:
        assert 0<=n['lane']<len(f['lanes'])
        assert (n['lane'],n['row']) not in occupied,(f['id'],n['id'])
        occupied.add((n['lane'],n['row']))
        if n['target']:assert n['target'] in flow_ids,n['target']
        assert not re.search(r'(_id\b|SELECT |GET /|POST /|student_exam_scores|UUID|JSONB)',n['title']),(f['id'],n['title'])
    for e in f['edges']:
        assert e['a'] in nodes and e['b'] in nodes,(f['id'],e)
    starts=[n['id'] for n in f['nodes'] if n['kind']=='start']
    ends=[n['id'] for n in f['nodes'] if n['kind']=='end']
    assert starts and ends,f['id']
    visited=set(starts)
    while True:
        more={e['b'] for e in f['edges'] if e['a'] in visited}
        if more<=visited:break
        visited|=more
    assert visited==set(nodes),(f['id'],'unreachable',set(nodes)-visited)
    can_end=set(ends)
    while True:
        more={e['a'] for e in f['edges'] if e['b'] in can_end}
        if more<=can_end:break
        can_end|=more
    assert can_end==set(nodes),(f['id'],'dead end',set(nodes)-can_end)
    for n in f['nodes']:
        if n['kind']=='decision':
            out=[e for e in f['edges'] if e['a']==n['id']]
            assert len(out)>=2 and all(e['label'] for e in out),(f['id'],n['id'],'unlabeled decision')

for rel in ['apps/api/app/services/school_workbench.py','apps/api/app/services/import_workbench.py','apps/api/app/services/learning_workbench.py','apps/api/app/api/v1/endpoints/education.py','apps/api/app/api/v1/endpoints/platform.py','apps/api/app/api/v1/endpoints/chat.py','apps/api/app/agent/agent_loop.py','apps/api/app/tools/analysis_tools.py','apps/api/app/core/diagnosis_access.py','apps/api/app/core/platform_workflows.py']:
    p=ROOT/rel
    D['references'].append(dict(path=rel,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
D['stats']=dict(sections=len(D['sections']),flows=len(all_flows),steps=sum(len(f['nodes']) for f in all_flows),decisions=sum(n['kind']=='decision' for f in all_flows for n in f['nodes']),materials=len(D['materials']))
encoded=json.dumps(D,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
html=(HERE/'template.html').read_text().replace('__DATA__',encoded).replace('__CSS__',(HERE/'style.css').read_text()).replace('__JS__',(HERE/'diagram.js').read_text()+'\n'+(HERE/'app.js').read_text())
output=HERE.parent/'智能问答_业务流程图.html'
output.write_text(html)
print(json.dumps(dict(file=str(output),bytes=output.stat().st_size,**D['stats']),ensure_ascii=False,indent=2))
