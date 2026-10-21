// Private NDJSON stream of CRM-owned, verified historical customer references.
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {once} from 'node:events';
import {eligibleReference} from './reference-policy.mjs';
const require=createRequire('/data/365d-crm/repository/apps/server/package.json');
const {Client}=require('pg'); const e=process.env;
const db=new Client({host:e.DATABASE_HOST,port:Number(e.DATABASE_PORT||5432),database:e.DATABASE_NAME,
 user:e.DATABASE_USER,password:e.DATABASE_PASSWORD,ssl:e.DATABASE_SSL==='false'?false:{rejectUnauthorized:e.DATABASE_SSL_REJECT_UNAUTHORIZED!=='false'},statement_timeout:15000,
 options:'-c default_transaction_read_only=on -c lock_timeout=2000'});
const scope={workspaceId:'1',environment:'production',sourceSystem:'respond',sourceInstance:'respond/mysql-b0497d24dc471307',sourceScope:'contacts'};
const sha=createHash('sha256'); let count=0,after='0';
async function line(value,hash=true) {const raw=JSON.stringify(value)+'\n';if(hash)sha.update(raw);if(!process.stdout.write(raw))await once(process.stdout,'drain');}
await db.connect();
try {
 await db.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
 // Merge/split/undo and route transfers are ownership evidence. Profile and
 // lifecycle version increments do not invalidate an otherwise reviewed owner.
 const audits=(await db.query(`WITH changes AS (
  SELECT source_customer_id AS customer_id,greatest(created_at,coalesce(reverted_at,created_at)) AS changed_at FROM app.contact_operations
  UNION ALL SELECT target_customer_id,greatest(created_at,coalesce(reverted_at,created_at)) FROM app.contact_operations
  UNION ALL SELECT from_customer_id,created_at FROM app.contact_identity_transfers
  UNION ALL SELECT to_customer_id,created_at FROM app.contact_identity_transfers
 ) SELECT customer_id::text,max(changed_at) AS changed_at FROM changes GROUP BY customer_id LIMIT 250001`)).rows;
 if(audits.length>250000)throw new Error('ownership_audit_limit');
 const lastChange=new Map(audits.map(row=>[row.customer_id,new Date(row.changed_at).getTime()]));
 await line({type:'header',schemaVersion:1,scope,verificationPolicy:'owner-audit-v1',exportedAt:new Date().toISOString()});
 while(true) {
  const rows=(await db.query(`SELECT r.id::text AS "referenceId",r.revision::text AS revision,
    r.customer_id::text AS "customerId",r.external_customer_id AS "respondId",
    r.updated_at AS "referenceReviewedAt",root.updated_at AS "rootReviewedAt",
    r.verified_customer_version AS "referenceVersion",root.verified_customer_version AS "rootVersion",c.version AS "customerVersion",
    coalesce(r.evidence->>'sha256' ~ '^[a-f0-9]{64}$' AND root.evidence->>'sha256' ~ '^[a-f0-9]{64}$'
     AND r.evidence->>'approvedPlanHash' ~ '^[a-f0-9]{64}$' AND root.evidence->>'approvedPlanHash' ~ '^[a-f0-9]{64}$'
     AND nullif(r.evidence->>'recordKey','') IS NOT NULL AND nullif(root.evidence->>'recordKey','') IS NOT NULL,false) AS "reviewedEvidence"
   FROM app.customer_external_references r JOIN app.customers c ON c.id=r.customer_id
   JOIN app.customer_external_references root ON root.workspace_id=r.workspace_id AND root.environment=r.environment
    AND root.source_system=r.source_system AND root.source_instance=r.source_instance AND root.source_scope=r.source_scope
    AND root.external_customer_id=r.canonical_external_customer_id AND root.canonical_external_customer_id=root.external_customer_id
    AND root.customer_id=r.customer_id AND root.state='verified'
   WHERE r.workspace_id=$1::bigint AND r.environment=$2 AND r.source_system=$3 AND r.source_instance=$4 AND r.source_scope=$5
    AND r.state='verified' AND c.status='active'
    AND r.external_customer_id ~ '^[1-9][0-9]{0,18}$' AND r.id>$6::bigint
    AND EXISTS(SELECT 1 FROM app.customer_channel_identities i JOIN app.provider_connections p ON p.id=i.provider_connection_id
      WHERE i.customer_id=c.id AND p.workspace_id=r.workspace_id)
   ORDER BY r.id LIMIT 5000`,[scope.workspaceId,scope.environment,scope.sourceSystem,scope.sourceInstance,scope.sourceScope,after])).rows;
  if(!rows.length)break;
  for(const row of rows) {
   if(!eligibleReference(row,lastChange.get(row.customerId)))continue;
   if(++count>250000)throw new Error('reference_export_limit');
   const {referenceId,revision,customerId,respondId}=row;
   await line({type:'reference',referenceId,revision,customerId,respondId});
  }
  after=rows.at(-1).referenceId;
 }
 await line({type:'footer',count,sha256:sha.digest('hex')},false);
 await db.query('ROLLBACK');
} finally {await db.end();}
