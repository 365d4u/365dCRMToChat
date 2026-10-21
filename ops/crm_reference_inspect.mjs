// Runtime-only, read-only reference assessment. Never output configuration.
import {createRequire} from 'node:module';
const require=createRequire('/data/365d-crm/repository/apps/server/package.json');
const {Client}=require('pg'); const e=process.env;
const db=new Client({host:e.DATABASE_HOST,port:Number(e.DATABASE_PORT||5432),database:e.DATABASE_NAME,
 user:e.DATABASE_USER,password:e.DATABASE_PASSWORD,ssl:e.DATABASE_SSL==='false'?false:{rejectUnauthorized:e.DATABASE_SSL_REJECT_UNAUTHORIZED!=='false'},statement_timeout:12000});
await db.connect();
try {
 await db.query('BEGIN READ ONLY');
 const guides=(await db.query("SELECT table_name,title,left(description,500) AS description FROM app.ai_db_guide WHERE project_key='365d_crm' AND table_schema='app' AND table_name IN ('customers','customer_external_references','customer_channel_identities') ORDER BY table_name LIMIT 3")).rows;
 const modules=(await db.query("SELECT module_key,title,left(implementation,700) AS implementation FROM app.ai_sys_guide WHERE project_key='365d_crm' AND related_tables::text LIKE '%customer_external_references%' LIMIT 3")).rows;
 const columns=(await db.query("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='app' AND table_name IN ('customers','customer_external_references') ORDER BY table_name,ordinal_position LIMIT 70")).rows;
 const scopes=(await db.query("SELECT workspace_id::text,environment,source_system,source_instance,source_scope,state,count(*)::int AS references FROM app.customer_external_references WHERE source_system='respond' GROUP BY 1,2,3,4,5,6 ORDER BY 1,2,3,4,5,6 LIMIT 30")).rows;
 const eligibility=(await db.query("SELECT count(*)::int AS total,count(*) FILTER(WHERE c.status='active' AND c.version=r.verified_customer_version)::int AS current_verified_customer FROM app.customer_external_references r JOIN app.customers c ON c.id=r.customer_id WHERE r.workspace_id=1 AND r.environment='production' AND r.source_system='respond' AND r.source_instance='respond/mysql-b0497d24dc471307' AND r.source_scope='contacts' AND r.state='verified'")).rows;
 const sample=(await db.query("SELECT r.customer_id::text,r.external_customer_id,r.state,c.status FROM app.customer_external_references r JOIN app.customers c ON c.id=r.customer_id WHERE r.source_system='respond' AND (r.customer_id=$1::bigint OR r.external_customer_id=$1::text) LIMIT 10",['193516'])).rows;
 console.log(JSON.stringify(process.argv.includes('--counts')?{scopes,eligibility,sample}:{guides,modules,columns,scopes,eligibility,sample}));
 await db.query('ROLLBACK');
} finally {await db.end();}
