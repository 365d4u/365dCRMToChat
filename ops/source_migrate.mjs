import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire('/data/365d-crm/repository/apps/server/package.json');
const {Client}=require('pg');const e=process.env;
const db=new Client({host:e.DATABASE_HOST,port:Number(e.DATABASE_PORT||5432),database:e.DATABASE_NAME,
 user:e.DATABASE_USER,password:e.DATABASE_PASSWORD,ssl:e.DATABASE_SSL==='false'?false:{rejectUnauthorized:e.DATABASE_SSL_REJECT_UNAUTHORIZED!=='false'},statement_timeout:10000});
const source=readFileSync(process.argv[2],'utf8');
const backup='/data/365d-crm/config/migration/msgsite-20261012';
await db.connect();
try{
 await db.query('BEGIN');
 const existing=(await db.query("SELECT table_name FROM information_schema.tables WHERE table_schema='app' AND table_name IN ('msgsite_settings','msgsite_message_versions','msgsite_resync')")).rows;
 if(existing.length) throw Error('Source integration already installed');
 const columns=(await db.query("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='app' AND table_name IN ('messages','channel_conversations','customers','outbox_events') ORDER BY table_name,ordinal_position")).rows;
 const triggers=(await db.query("SELECT tgname,pg_get_triggerdef(oid) AS definition FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('app.messages'::regclass,'app.channel_conversations'::regclass,'app.customers'::regclass)")).rows;
 writeFileSync(backup+'/schema-preimage.json',JSON.stringify({columns,triggers},null,2),{mode:0o600});
 writeFileSync(backup+'/applied.sql',source,{mode:0o600});
 await db.query(source);
 await db.query('COMMIT');
 console.log(JSON.stringify({result:'source_schema_installed',enabled:false,sha256:createHash('sha256').update(source).digest('hex')}));
 const workspaces=(await db.query("SELECT id::text,kind FROM app.inbox_workspaces WHERE status='active' ORDER BY id")).rows;
 console.log(JSON.stringify({workspaces}));
}catch(error){await db.query('ROLLBACK');console.error(JSON.stringify({result:'migration_failed',code:error.code||'preflight'}));process.exitCode=1}
finally{await db.end()}
