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


def plan_import(cursor,refs):
    cursor.execute('SELECT conversation_id FROM chatwoot_conversation_update')
    conversations={str(r['conversation_id']) for r in cursor.fetchall()}
    cursor.execute('SELECT chatwoot_conv_id,respond_conv_id FROM map_conversation_respond '
                   'UNION SELECT chatwoot_conv_id,respond_conv_id FROM respond_conv_map')
    edges=[(str(r['chatwoot_conv_id']),str(r['respond_conv_id'])) for r in cursor.fetchall()]
    links,stats=history_links(refs,conversations,edges)
    cursor.execute('SELECT conversation_id,crm_customer_id,verified,evidence FROM crm_conversation_link')
    existing={str(r['conversation_id']):r for r in cursor.fetchall()}
    # Keep manual/unrelated mappings; a different owner always needs review.
    blocked=set()
    for conv,(cid,_) in links.items():
        old=existing.get(conv)
        if old and not old['evidence'].startswith(EVIDENCE_PREFIX):
            blocked.add(conv)
    for conv in blocked:del links[conv]
    stats.update({'references':len(refs),'historyLinks':len(links),'protectedExistingLinks':len(blocked)})
    return links,stats


def apply_import(connection,refs,links):
    """Commit bounded batches; refresh only this service's own CRM-proven mappings."""
    with connection.cursor() as q:
        q.execute('SELECT respond_id,crm_customer_id,source_reference_id,source_revision,verified,evidence FROM crm_respond_customer_link')
        old={str(r['respond_id']):r for r in q.fetchall()}
        q.execute("SELECT conversation_id,crm_customer_id,verified,evidence FROM crm_conversation_link WHERE evidence LIKE 'crm-ref:v1:%'")
        old_links=q.fetchall()
    for rid,record in refs.items():
        previous=old.get(rid)
        if previous and (not previous['evidence'].startswith(EVIDENCE_PREFIX)
            or str(previous['source_reference_id'])!=record[1] or int(previous['source_revision'])>int(record[2])
            or (int(previous['source_revision'])==int(record[2]) and str(previous['crm_customer_id'])!=record[0])):
            raise ValueError('reference_ownership_changed_requires_review')
    active=sum(bool(record['verified']) for record in old.values())
    if active>1000 and len(refs)<active/2:
        raise ValueError('reference_snapshot_shrank_requires_review')
    # Revoke obsolete derived links before changing the cached source owner.
    revoke_links=[(str(r['conversation_id']),) for r in old_links if r['verified'] and
                  (str(r['conversation_id']) not in links or str(r['crm_customer_id'])!=links[str(r['conversation_id'])][0])]
    revoke_refs=[(rid,) for rid in old if old[rid]['verified'] and rid not in refs]
    records=[(rid,cid,1,reference,revision,1,EVIDENCE_PREFIX+reference+':'+revision)
             for rid,(cid,reference,revision) in refs.items() if rid not in old or
             (str(old[rid]['crm_customer_id']),str(old[rid]['source_revision']),old[rid]['verified'])!=(cid,revision,1)]
    old_history={str(r['conversation_id']):r for r in old_links}
    histories=[(conv,cid,1,evidence) for conv,(cid,evidence) in links.items() if conv not in old_history or
               (str(old_history[conv]['crm_customer_id']),old_history[conv]['verified'],old_history[conv]['evidence'])!=(cid,1,evidence)]
    for sql,values in [
        ("UPDATE crm_conversation_link SET verified=0 WHERE conversation_id=%s AND evidence LIKE 'crm-ref:v1:%%'",revoke_links),
        ("UPDATE crm_respond_customer_link SET verified=0 WHERE respond_id=%s AND evidence LIKE 'crm-ref:v1:%%'",revoke_refs),
        ('INSERT INTO crm_respond_customer_link (respond_id,crm_customer_id,workspace_id,source_reference_id,source_revision,verified,evidence) '
         'VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE '
         'crm_customer_id=VALUES(crm_customer_id),source_revision=VALUES(source_revision),verified=1,evidence=VALUES(evidence)',records),
        ('INSERT INTO crm_conversation_link (conversation_id,crm_customer_id,verified,evidence) VALUES (%s,%s,%s,%s) '
         "ON DUPLICATE KEY UPDATE crm_customer_id=IF(evidence LIKE 'crm-ref:v1:%%',VALUES(crm_customer_id),crm_customer_id),"
         "verified=IF(evidence LIKE 'crm-ref:v1:%%',1,verified),"
         "evidence=IF(evidence LIKE 'crm-ref:v1:%%',VALUES(evidence),evidence)",histories)]:
        for start in range(0,len(values),500):
            connection.begin()
            try:
                with connection.cursor() as q:q.executemany(sql,values[start:start+500])
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    return {'referenceChanges':len(records),'historyChanges':len(histories),
            'revokedReferences':len(revoke_refs),'revokedHistory':len(revoke_links)}
