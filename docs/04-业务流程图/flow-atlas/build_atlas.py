"""Build the offline, source-backed flow atlas. Run from any working directory.
Only reads source code; never imports the app, reads credentials, or queries data.
"""
from pathlib import Path
import ast
import hashlib
import json
import runpy

HERE = Path(__file__).resolve().parent

def _find_root(p):
    """向上查找仓库根（含 apps/ 与 docker-compose.yml 的目录）。"""
    for parent in [p, *p.parents]:
        if (parent / 'apps').is_dir() and (parent / 'docker-compose.yml').exists():
            return parent
    return p.parent

ROOT = _find_root(HERE)
DATA = {"title": "智能问答 · 全链路流程图谱", "date": "2026-09-18", "sections": [], "sources": {}, "tables": [], "apis": []}

ALIASES = {
    "school": "apps/api/app/services/school_workbench.py",
    "imports": "apps/api/app/services/import_workbench.py",
    "csv": "apps/api/app/data/csv_importer.py",
    "importer": "apps/api/app/data/import_service.py",
    "education": "apps/api/app/api/v1/endpoints/education.py",
    "schemas": "apps/api/app/schemas/education.py",
    "learning": "apps/api/app/services/learning_workbench.py",
    "curriculum": "apps/api/app/services/curriculum.py",
    "legacy": "apps/api/app/services/legacy_snapshot.py",
    "legacy_schema": "apps/api/app/schemas/legacy_snapshot.py",
    "chat": "apps/api/app/api/v1/endpoints/chat.py",
    "agent": "apps/api/app/agent/agent_loop.py",
    "context": "apps/api/app/agent/context.py",
    "router": "apps/api/app/agent/intent_router.py",
    "exam_tool": "apps/api/app/tools/exam_tools.py",
    "score_tool": "apps/api/app/tools/score_tools.py",
    "analysis_tool": "apps/api/app/tools/analysis_tools.py",
    "guard": "apps/api/app/core/response_guard.py",
    "grants": "apps/api/app/core/diagnosis_access.py",
    "scope": "apps/api/app/core/access_scope.py",
    "auth": "apps/api/app/api/deps.py",
    "common": "apps/api/app/services/education_common.py",
    "platform": "apps/api/app/api/v1/endpoints/platform.py",
    "details": "apps/api/app/api/v1/endpoints/management_details.py",
    "workflow": "apps/api/app/core/platform_workflows.py",
    "gateway": "apps/api/app/ai/gateway.py",
    "main": "apps/api/app/main.py",
    "ocr": "apps/api/app/services/ocr_jobs.py",
    "school_ui": "apps/web/src/features/education/SchoolWorkbench.tsx",
    "import_ui": "apps/web/src/features/education/ImportWorkbench.tsx",
    "report_ui": "apps/web/src/features/education/EvidenceWorkbench.tsx",
    "learning_ui": "apps/web/src/features/education/LearningPanels.tsx",
    "management_ui": "apps/web/src/pages/ManagementPages.tsx",
    "chat_ui": "apps/web/src/components/ChatContainer.tsx",
    "bubble_ui": "apps/web/src/components/MessageBubble.tsx",
    "stream_ui": "apps/web/src/hooks/useStreamChat.ts",
    "answer_ui": "apps/web/src/components/AnswerText.tsx",
    "nav_ui": "apps/web/src/layouts/AppShell.tsx",
    "routes_ui": "apps/web/src/App.tsx",
}

def src(alias, symbol=None):
    path = ALIASES.get(alias, alias)
    key = path + ("#" + symbol if symbol else "")
    if key not in DATA["sources"]:
        text = (ROOT / path).read_text()
        lines = text.splitlines()
        line, end = 1, min(len(lines), 72)
        if symbol and path.endswith(".py"):
            for n in ast.walk(ast.parse(text)):
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == symbol:
                    line, end = n.lineno, n.end_lineno
                    break
            else:
                raise ValueError(f"Unknown symbol: {key}")
        elif symbol:
            for i, text_line in enumerate(lines, 1):
                if symbol in text_line:
                    line, end = i, min(len(lines), i + 60)
                    break
            else:
                raise ValueError(f"Unknown source anchor: {key}")
        shown_end = min(end, line + 95)
        DATA["sources"][key] = {"path": path, "symbol": symbol, "line": line, "end": end,
            "sha": hashlib.sha256(text.encode()).hexdigest(),
            "snippet": "\n".join(f"{i:>4}  {lines[i-1]}" for i in range(line, shown_end + 1)),
            "truncated": end > shown_end}
    return key

def section(id, num, title, sub, group="业务模块", **kwargs):
    s = dict(id=id, num=num, title=title, subtitle=sub, group=group, diagrams=[], notes=[], tables=[], **kwargs)
    DATA["sections"].append(s)
    return s

def n(id, title, text, col=0, row=0, kind="process", detail=None, tables=None, api=None, refs=None, target=None):
    return dict(id=id, title=title, text=text, col=col, row=row, kind=kind,
        detail=detail or text, tables=tables or [], api=api or [], refs=refs or [], target=target)

def e(a, b, label="", kind="normal", via=None):
    return dict(a=a, b=b, label=label, kind=kind, via=via)

def graph(s, id, title, desc, nodes, edges=None, refs=None, note=None):
    s["diagrams"].append(dict(id=id, title=title, desc=desc, nodes=nodes,
        edges=edges if edges is not None else [e(nodes[i]["id"], nodes[i+1]["id"]) for i in range(len(nodes)-1)],
        refs=refs or [], note=note))

def chain(s, id, title, desc, steps, refs=None, note=None):
    # A three-column snake keeps all labels legible, with explicit directed edges.
    nodes=[]
    for i, step in enumerate(steps):
        row, col = divmod(i, 3)
        if row % 2: col = 2-col
        if isinstance(step, dict):
            node=n(f"{id}-{i+1}", col=col, row=row, **step)
        else:
            title_, text_, *rest = step
            node=n(f"{id}-{i+1}", title_, text_, col, row, rest[0] if rest else "process")
        nodes.append(node)
    graph(s,id,title,desc,nodes,refs=refs,note=note)

def note(s,title,text,tone="info"):
    s["notes"].append(dict(title=title,text=text,tone=tone))

def table(s,title,headers,rows):
    s["tables"].append(dict(title=title,headers=headers,rows=rows))

ENV={k:v for k,v in globals().copy().items() if not k.startswith("__")}
for file in ["domain_content.py", "analysis_content.py", "qa_content.py", "reference_content.py", "extra_diagrams.py"]:
    runpy.run_path(str(HERE/file),init_globals=ENV)

# Derive every field from the current ORM declarations; constraints stay exact.
for path in sorted((ROOT/"apps/api/app/db/models").glob("*.py")):
    if path.name in {"__init__.py"}: continue
    text=path.read_text()
    tree=ast.parse(text)
    for cls in [c for c in tree.body if isinstance(c,ast.ClassDef)]:
        name=None
        for a in cls.body:
            if isinstance(a,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="__tablename__" for t in a.targets):
                name=ast.literal_eval(a.value)
        if not name: continue
        fields=[]; constraints=[]
        for a in cls.body:
            if not isinstance(a,ast.Assign) or not isinstance(a.targets[0],ast.Name): continue
            attr=a.targets[0].id
            if attr=="__table_args__":
                constraints=[ast.unparse(v) for v in getattr(a.value,"elts",[])]
            if not isinstance(a.value,ast.Call): continue
            call=a.value; fn=ast.unparse(call.func)
            if fn not in {"Column","identity","school","timestamp"}: continue
            kwargs={kw.arg:kw.value for kw in call.keywords}
            comment=ast.literal_eval(kwargs["comment"]) if "comment" in kwargs else ""
            db_name=attr
            args=list(call.args)
            if fn=="Column" and args and isinstance(args[0],ast.Constant) and isinstance(args[0].value,str):
                db_name=args.pop(0).value
            type_=ast.unparse(args[0]) if args else {"identity":"UUID（主键）","school":"UUID → schools.id","timestamp":"DateTime(timezone=True)"}.get(fn,"")
            pk=kwargs.get("primary_key")
            nullable="不可空" if fn in {"identity","school","timestamp"} or (pk and isinstance(pk,ast.Constant) and pk.value) or ("nullable" in kwargs and isinstance(kwargs["nullable"],ast.Constant) and kwargs["nullable"].value is False) else "可空"
            default=" / ".join(f"{k}={ast.unparse(kwargs[k])}" for k in ("default","server_default") if k in kwargs)
            fields.append(dict(name=db_name, attr=attr, type=type_, comment=comment, nullable=nullable, default=default, definition=ast.unparse(a.value),line=a.lineno))
        DATA["tables"].append(dict(name=name,model=cls.name,path=str(path.relative_to(ROOT)),line=cls.lineno,fields=fields,constraints=constraints,ref=src(str(path.relative_to(ROOT)),cls.name)))

# Static endpoint inventory, including read/write permission dependencies and request types.
for alias in ["education","chat","platform","details"]:
    path=ALIASES[alias]; tree=ast.parse((ROOT/path).read_text()); prefix=""
    for a in tree.body:
        if isinstance(a,ast.Assign) and isinstance(a.value,ast.Call) and ast.unparse(a.value.func)=="APIRouter":
            for kw in a.value.keywords:
                if kw.arg=="prefix":prefix=ast.literal_eval(kw.value)
    for fn in tree.body:
        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        for d in fn.decorator_list:
            if not isinstance(d,ast.Call) or not isinstance(d.func,ast.Attribute) or ast.unparse(d.func.value)!="router":continue
            if d.func.attr not in {"get","post","put","patch","delete"}:continue
            route=ast.literal_eval(d.args[0]); params=[]
            defaults=[None]*(len(fn.args.args)-len(fn.args.defaults))+list(fn.args.defaults)
            for arg,default in zip(fn.args.args,defaults):
                if arg.arg in {"request","db","background"}:continue
                params.append(arg.arg+(": "+ast.unparse(arg.annotation) if arg.annotation else "")+(" = "+ast.unparse(default) if default else ""))
            DATA["apis"].append(dict(method=d.func.attr.upper(),path="/api/v1"+prefix+route,function=fn.name,params=params,ref=src(alias,fn.name)))

# Validate all diagram IDs, source references, targets, and table names before output.
ids=set(); known_tables={t["name"] for t in DATA["tables"]}; sections={s["id"] for s in DATA["sections"]}
for s in DATA["sections"]:
    for d in s["diagrams"]:
        assert d["id"] not in ids,d["id"]
        ids.add(d["id"]); node_ids={node["id"] for node in d["nodes"]}
        assert len(node_ids)==len(d["nodes"])
        for edge in d["edges"]:assert edge["a"] in node_ids and edge["b"] in node_ids,(d["id"],edge)
        occupied=set()
        for node in d["nodes"]:
            pos=(node["col"],node["row"])
            assert pos not in occupied,(d["id"],pos)
            occupied.add(pos)
            for name in node["tables"]:assert name in known_tables,(d["id"],name)
            for ref in node["refs"]:assert ref in DATA["sources"]
            if node["target"]:assert node["target"] in sections,node["target"]
        for ref in d["refs"]:assert ref in DATA["sources"]
DATA["stats"]={"diagrams":len(ids),"nodes":sum(len(d["nodes"]) for s in DATA["sections"] for d in s["diagrams"]),"edges":sum(len(d["edges"]) for s in DATA["sections"] for d in s["diagrams"]),"tables":len(DATA["tables"]),"fields":sum(len(t["fields"]) for t in DATA["tables"]),"apis":len(DATA["apis"]),"files":len({v["path"] for v in DATA["sources"].values()})}
encoded=json.dumps(DATA,ensure_ascii=False,separators=(",",":")).replace("<","\\u003c").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
html=(HERE/"atlas.template.html").read_text().replace("__ATLAS_DATA__",encoded)
html=html.replace("__ATLAS_CSS__",(HERE/"atlas.css").read_text())
html=html.replace("__ATLAS_SCRIPT__",(HERE/"graphs.js").read_text()+"\n"+(HERE/"atlas.js").read_text())
output=HERE.parent/"智能问答_全链路流程图.html"
output.write_text(html)
print(json.dumps({"output":str(output),"bytes":output.stat().st_size,**DATA["stats"]},ensure_ascii=False,indent=2))
