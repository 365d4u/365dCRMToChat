import {createRequire} from 'node:module';
const {Client}=createRequire('/data/365d-crm/repository/apps/server/package.json')('pg');const e=process.env;
const db=new Client({host:e.DATABASE_HOST,port:Number(e.DATABASE_PORT||5432),database:e.DATABASE_NAME,user:e.DATABASE_USER,password:e.DATABASE_PASSWORD,
 ssl:e.DATABASE_SSL==='false'?false:{rejectUnauthorized:e.DATABASE_SSL_REJECT_UNAUTHORIZED!=='false'},statement_timeout:15000,options:'-c default_transaction_read_only=on -c lock_timeout=2000'});
await db.connect();try{
 await db.query('BEGIN READ ONLY');
 const tables=['recovered_conversation_targets','channel_conversations','channel_participants','channel_accounts'];
 const guides=(await db.query("SELECT table_name,title,left(description,500) AS description FROM app.ai_db_guide WHERE project_key='365d_crm' AND table_name=ANY($1::text[]) LIMIT 8",[tables])).rows;
 const columns=(await db.query("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='app' AND table_name=ANY($1::text[]) ORDER BY table_name,ordinal_position",[tables])).rows;
 const anchors=(await db.query(`SELECT i.customer_id::text,t.evidence->>'sourceKey' AS source_key,t.evidence->>'recordKey' AS record_key,
 t.evidence->>'approvedPlanHash'=r.evidence->>'approvedPlanHash' AS same_plan,
 i.customer_id=v.customer_id AS same_owner,i.provider_connection_id=t.provider_connection_id AS same_connection,
 i.channel_account_id=t.channel_account_id AND v.channel_account_id=t.channel_account_id AS same_account,
 i.channel_contact_id=t.channel_contact_id AS same_native,t.workspace_id::text
 FROM app.recovered_conversation_targets t JOIN app.customer_channel_identities i ON i.id=t.customer_channel_identity_id
 JOIN app.channel_conversations v ON v.id=t.channel_conversation_id JOIN app.customer_external_references r ON r.customer_id=i.customer_id
 WHERE r.source_system='respond' AND r.external_customer_id=ANY($1::text[]) LIMIT 15`,[['429120621','317763983','457693542']])).rows;
 const auditGuides=(await db.query("SELECT table_name,title,left(description,700) AS description FROM app.ai_db_guide WHERE project_key='365d_crm' AND table_name IN ('contact_operations','contact_identity_transfers') LIMIT 3")).rows;
 const auditColumns=(await db.query("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='app' AND table_name IN ('contact_operations','contact_identity_transfers') ORDER BY table_name,ordinal_position LIMIT 45")).rows;
 const operations=(await db.query(`SELECT count(*)::int AS operations FROM app.contact_operations`)).rows;
 console.log(JSON.stringify({operations}));
 const blocked=(await db.query(`WITH change AS (
 SELECT source_customer_id AS customer_id,greatest(created_at,coalesce(reverted_at,created_at)) AS at FROM app.contact_operations
 UNION ALL SELECT target_customer_id,greatest(created_at,coalesce(reverted_at,created_at)) FROM app.contact_operations
 UNION ALL SELECT from_customer_id,created_at FROM app.contact_identity_transfers
 UNION ALL SELECT to_customer_id,created_at FROM app.contact_identity_transfers
 ), last_change AS (SELECT customer_id,max(at) AS at FROM change GROUP BY customer_id)
 SELECT CASE WHEN c.status<>'active' THEN 'inactive' WHEN x.at>=least(r.updated_at,root.updated_at) THEN 'identity_changed'
 WHEN c.version=r.verified_customer_version AND c.version=root.verified_customer_version THEN 'version_current'
 WHEN r.evidence->>'sha256' ~ '^[a-f0-9]{64}$' AND root.evidence->>'sha256' ~ '^[a-f0-9]{64}$'
 AND r.evidence->>'approvedPlanHash' ~ '^[a-f0-9]{64}$' AND root.evidence->>'approvedPlanHash' ~ '^[a-f0-9]{64}$' THEN 'audited_owner_unchanged'
 ELSE 'needs_review' END AS status,count(*)::int AS count
 FROM app.customer_external_references r JOIN app.customers c ON c.id=r.customer_id
 JOIN app.customer_external_references root ON root.workspace_id=r.workspace_id AND root.environment=r.environment AND root.source_system=r.source_system
 AND root.source_instance=r.source_instance AND root.source_scope=r.source_scope AND root.external_customer_id=r.canonical_external_customer_id
 AND root.canonical_external_customer_id=root.external_customer_id AND root.customer_id=r.customer_id AND root.state='verified'
 LEFT JOIN last_change x ON x.customer_id=c.id
 WHERE r.workspace_id=1 AND r.environment='production' AND r.source_system='respond' AND r.source_instance='respond/mysql-b0497d24dc471307'
 AND r.external_customer_id IN ('429120621','317763983','457693542')
 AND r.source_scope='contacts' AND r.state='verified' GROUP BY 1 ORDER BY 1`)).rows;
 console.log(JSON.stringify({operations,blocked}));await db.query('ROLLBACK');
}finally{await db.end();}
