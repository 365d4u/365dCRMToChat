"""Validated, bounded CRM reference import. Legacy message data is never written."""
import hashlib,json
from collections import defaultdict
from .contracts import db_id

SCOPE = {'workspaceId':'1','environment':'production','sourceSystem':'respond',
         'sourceInstance':'respond/mysql-b0497d24dc471307','sourceScope':'contacts'}
EVIDENCE_PREFIX = 'crm-ref:v1:'


def read_snapshot(path):
    sha=hashlib.sha256(); refs={}; header=None; footer=None; size=0
    with open(path,'rb') as stream:
        for raw in stream:
            size+=len(raw)
            if size>80_000_000 or len(raw)>4096 or footer is not None:
                raise ValueError('invalid_reference_snapshot')
            value=json.loads(raw)
            if value.get('type')=='footer':
                footer=value
                continue
            sha.update(raw)
            if header is None:
                if value.get('type')!='header' or value.get('schemaVersion')!=1 or value.get('scope')!=SCOPE:
                    raise ValueError('invalid_reference_scope')
                header=value
            else:
                if set(value)!={'type','referenceId','revision','customerId','respondId'} or value['type']!='reference':
                    raise ValueError('invalid_reference_fields')
                rid=db_id(value['respondId']); cid=db_id(value['customerId'])
                reference=db_id(value['referenceId']);revision=db_id(value['revision'])
                if rid in refs or len(refs)>=250000:
                    raise ValueError('duplicate_or_excess_references')
                refs[rid]=(cid,reference,revision)
    if not footer or footer.get('count')!=len(refs) or footer.get('sha256')!=sha.hexdigest():
        raise ValueError('incomplete_reference_snapshot')
    return refs,header


def history_links(refs, existing_conversations, edges):
    """Never merge a legacy conversation whose Respond aliases disagree."""
    aliases=defaultdict(set)
    for conversation,rid in edges:
        if conversation in existing_conversations and not conversation.startswith('crm_'):
            aliases[conversation].add(rid)
    for rid in refs:
        conversation='rd_'+rid
        if conversation in existing_conversations:
            aliases[conversation].add(rid)
    links={}; conflicts=0; unknown=0
    for conversation,rids in aliases.items():
        if any(rid not in refs for rid in rids):
            unknown+=1
            continue
        customers={refs[rid][0] for rid in rids}
        if len(customers)!=1:
            conflicts+=1
            continue
        cid=next(iter(customers))
        proof=sorted((refs[rid][1],refs[rid][2]) for rid in rids)
        # Evidence is reproducible, scoped to this CRM-exported reference set.
        evidence=EVIDENCE_PREFIX+hashlib.sha256(json.dumps(proof).encode()).hexdigest()
        links[conversation]=(cid,evidence)
    return links,{'conflictingHistory':conflicts,'unverifiedHistory':unknown}
