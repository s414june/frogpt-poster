"""CI drift gate between original master, six documents, rules, schema and IDs."""
import json
import ast
import re
from pathlib import Path
from gpt_package.design_rules import DesignRuleLoader, ROOT


def validate_documents(root=ROOT,master=None):
    data=DesignRuleLoader().load(root/'poster-rules.v1.json')
    files=sorted(root.glob('*.md'))
    if len(files)!=6:raise ValueError('Exactly six guideline Markdown files are required')
    rows={}
    for path in files:
        for id,severity,initial,requirement in re.findall(r'^\| ([A-Z]+-\d+) \| (hard|soft|advisory) \| (.*?) \| (.*?) \|$',path.read_text(),re.M):
            if id in rows:raise ValueError('Duplicate document rule: '+id)
            rows[id]=(severity,initial,requirement)
    if set(rows)!=set(r['id'] for r in data['rules']):raise ValueError('Rule IDs drifted')
    for rule in data['rules']:
        severity,initial,requirement=rows[rule['id']]
        if (severity,initial,requirement)!=(rule['severity'],rule['documentation'],rule['rationale']):raise ValueError('Document/rule drift: '+rule['id'])
        if rule['source']!='FroGPT original' and not rule['source'].startswith('https://'):raise ValueError('Missing source URL')
    # A retained master is the immutable review baseline for v1 numeric/default decisions.
    master=Path(master or root.parent/'docs/design-guidelines-master-v1.md').read_text()
    for path,body in re.findall(r'<!-- FILE START: (.*?) -->\n(.*?)<!-- FILE END -->',master,re.S):
        if (root/Path(path).name).read_text()!=body.rstrip()+'\n':raise ValueError('Guideline differs from supplied v1 master: '+path)
    # Range/default consistency with the natural-language initial value, including
    # compound tokens, is recorded in a machine-readable specification projection.
    def numeric_leaves(value):
        if isinstance(value, bool):return []
        if isinstance(value,(int,float)):return [float(value)]
        if isinstance(value,dict):return [number for child in value.values() for number in numeric_leaves(child)]
        if isinstance(value,list):return [number for child in value for number in numeric_leaves(child)]
        return []
    for rule in data['rules']:
        numbers=[float(v) for v in re.findall(r'(?<![A-Za-z])(?:0\.\d+|\d+(?:\.\d+)?)',rule['documentation']+' '+rule['rationale'])]
        if '%' in rule['documentation']+' '+rule['rationale']:numbers += [v/100 for v in list(numbers)]
        if any(number not in numbers for number in numeric_leaves(rule['default'])):
            raise ValueError('Numeric default differs from document: '+rule['id'])
        if 'range' in rule and any(v not in numbers and v!=0 for v in rule['range'].values()):raise ValueError('Range differs from document: '+rule['id'])
    coverage=json.loads((root/'rule-coverage.json').read_text())['rules']
    if {entry['ruleId'] for entry in coverage}!=set(rows) or len(coverage)!=len(rows):raise ValueError('Rule coverage drift')
    for entry in coverage:
        if not entry['tests'] and not entry.get('notAutomaticallyTestable'):raise ValueError('Untracked rule: '+entry['ruleId'])
        for name in entry['tests']:
            parts=name.split('.')
            tree=ast.parse((root.parent/('/'.join(parts[:-2])+'.py')).read_text())
            cls=next((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==parts[-2]),None)
            if cls is None or not any(isinstance(n,ast.FunctionDef) and n.name==parts[-1] for n in cls.body):raise ValueError('Missing coverage test: '+name)
    font_manifest=json.loads((root.parent/'assets/blob-manifest.json').read_text())
    for font in font_manifest['fonts']:
        license_path=root.parent/font.get('license','MISSING_LICENSE')
        if not license_path.is_file() or 'SIL OPEN FONT LICENSE' not in license_path.read_text().upper():raise ValueError('Registered font license is unavailable')
    return dict(ok=True,documents=len(files),rules=len(rows),version=data['schemaVersion'])

if __name__=='__main__':print(json.dumps(validate_documents()))
