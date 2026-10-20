"""Versioned, schema-validated rules; only soft tokens can be overridden."""
import copy
import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from jsonschema import Draft202012Validator
from .errors import ValidationError

ROOT = Path(__file__).resolve().parents[2] / 'design-guidelines'


class DesignRuleError(ValidationError):
    def __init__(self, code, rule_id, reason, element_id='poster', before=None, after=None):
        super().__init__(reason)
        self.code = code
        self.diagnostics = [diagnostic(rule_id, 'error', element_id, before, after, reason)]


def diagnostic(rule, level, element, original, resolved, reason):
    return dict(ruleId=rule, level=level, severity=level, elementId=element,
                original=original, resolved=resolved, before=original, after=resolved, reason=reason)


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise DesignRuleError('RULESET_INVALID', 'GRID-001', 'Non-finite value')
    if isinstance(value, dict):
        for child in value.values(): _finite(child)
    elif isinstance(value, list):
        for child in value: _finite(child)


class DesignRuleLoader:
    def load(self, path=None):
        try:
            data = json.loads(Path(path or ROOT/'poster-rules.v1.json').read_text())
            schema = json.loads((ROOT/'poster-rules.schema.json').read_text())
            _finite(data)
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(data)
            ids = [r['id'] for r in data['rules']]
            if len(ids) != len(set(ids)): raise ValueError('Duplicate rule IDs')
            rules = {r['id']:r for r in data['rules']}
            for rule in data['rules']:
                if rule['operator'] != rule['id'].lower().replace('-','_'):raise ValueError('Unknown rule operator')
                if rule['severity'] == 'hard' and (not rule['enabled'] or rule['overridePolicy'] != 'never'):
                    raise ValueError('Hard rules cannot be disabled/overridden')
                if 'range' in rule:
                    lo, hi = rule['range']['min'], rule['range']['max']
                    if lo > hi: raise ValueError('Reversed range')
                    if isinstance(rule['default'], (int,float)) and not isinstance(rule['default'],bool) and not lo <= rule['default'] <= hi:
                        raise ValueError('Default outside range')
            for preset in data['presets'].values():
                self.validate_overrides(rules, preset)
            return data
        except DesignRuleError: raise
        except Exception as exc:
            raise DesignRuleError('RULESET_INVALID','VAL-001',str(exc)) from exc

    @staticmethod
    def validate_overrides(rules, overrides):
        if not isinstance(overrides,dict): raise DesignRuleError('RULESET_INVALID','VAL-001','Overrides must be an object')
        for key,value in overrides.items():
            if key not in rules: raise DesignRuleError('RULESET_INVALID','VAL-001','Unknown rule ID: '+key)
            rule=rules[key]
            if rule['severity'] != 'soft': raise DesignRuleError('RULESET_INVALID',key,'Only soft rules can be overridden')
            _finite(value)
            # Preserve token structure and units; range is soft, reported separately.
            if isinstance(rule['default'],bool): valid=isinstance(value,bool)
            elif isinstance(rule['default'],(int,float)): valid=isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0
            else: valid=isinstance(value,type(rule['default']))
            if not valid or ('choices' in rule and value not in rule['choices']):
                raise DesignRuleError('RULESET_INVALID',key,'Invalid token type/choice')
            if isinstance(value,dict) and set(value)!=set(rule['default']):
                raise DesignRuleError('RULESET_INVALID',key,'Invalid token members')
            def same_shape(original, updated):
                if isinstance(original, dict):
                    return isinstance(updated, dict) and set(original)==set(updated) and all(same_shape(original[k],updated[k]) for k in original)
                if isinstance(original,list):
                    return isinstance(updated,list) and len(original)==len(updated) and all(same_shape(a,b) for a,b in zip(original,updated)) and (not all(isinstance(x,(int,float)) for x in updated) or updated==sorted(updated))
                if isinstance(original,(int,float)) and not isinstance(original,bool):
                    return isinstance(updated,(int,float)) and not isinstance(updated,bool) and updated>=0
                return isinstance(updated,type(original))
            if not same_shape(rule['default'],value):
                raise DesignRuleError('RULESET_INVALID',key,'Invalid compound token or reversed range')


@dataclass
class DesignIntent:
    version: str = '1.0.0'
    stylePreset: str = 'editorial'
    referenceOverrides: dict = field(default_factory=dict)
    userOverrides: dict = field(default_factory=dict)
    typography: list = field(default_factory=list)
    subjectPosition: dict | None = None
    assetProvenance: dict = field(default_factory=dict)
    allowColorRepair: bool = True
    allowBackdrop: bool = False
    protectionZones: list = field(default_factory=list)

    def to_dict(self):
        value=asdict(self)
        if self.subjectPosition is None:value.pop('subjectPosition')
        if not self.typography:value.pop('typography')
        return value


@dataclass
class ResolvedDesignTokens:
    version: str
    values: dict
    runtime: dict
    provenance: dict
    history: list
    diagnostics: list


class DesignTokenResolver:
    def resolve(self, data, intent):
        schema=json.loads((ROOT/'design-intent.schema.json').read_text())
        try:
            _finite(intent)
            Draft202012Validator(schema).validate(intent)
        except Exception as exc: raise DesignRuleError('RULESET_INVALID','GRID-001',str(exc)) from exc
        rules={r['id']:r for r in data['rules']}
        values={k:copy.deepcopy(r['default']) for k,r in rules.items()}
        provenance={k:'default' for k in rules};history=[];diagnostics=[]
        preset=intent.get('stylePreset','editorial')
        if preset not in data['presets']: raise DesignRuleError('RULESET_INVALID','VAL-001','Unknown preset')
        for source,overrides in [('preset',data['presets'][preset]),('reference',intent.get('referenceOverrides',{})),('user',intent.get('userOverrides',{}))]:
            DesignRuleLoader.validate_overrides(rules,overrides)
            for key,value in overrides.items():
                before=values[key];values[key]=copy.deepcopy(value);provenance[key]=source
                change=diagnostic(key,'info','tokens',before,value,'Override from '+source)
                history.append(change)
                if rules[key]['enforcement']=='experimental':
                    diagnostics.append(diagnostic(key,'warning','tokens',before,value,'Art-direction token retained; heuristic is experimental and not automatically enforced'))
                limit=rules[key].get('range')
                if limit and isinstance(value,(int,float)) and not limit['min']<=value<=limit['max']:
                    diagnostics.append(diagnostic(key,'warning','tokens',limit,value,'Soft range exceeded by explicit style/reference/user token'))
        runtime=copy.deepcopy(data['runtime'])
        runtime['headlinePreferredRange']=[rules['TYPO-004']['range']['min'],rules['TYPO-004']['range']['max']]
        return ResolvedDesignTokens(data['schemaVersion'],values,runtime,provenance,history,diagnostics)
