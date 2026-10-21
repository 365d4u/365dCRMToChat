// Runs on the verified API host. All fixture DDL/data roll back in a private schema.
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire('/data/365d-crm/repository/apps/server/package.json');
const {Client}=require('pg');const e=process.env;
const db=new Client({host:e.DATABASE_HOST,port:Number(e.DATABASE_PORT||5432),database:e.DATABASE_NAME,
 user:e.DATABASE_USER,password:e.DATABASE_PASSWORD,ssl:e.DATABASE_SSL==='false'?false:{rejectUnauthorized:e.DATABASE_SSL_REJECT_UNAUTHORIZED!=='false'},statement_timeout:10000});
await db.connect();
try{
 await db.query('BEGIN');
 await db.query(`CREATE SCHEMA msgsite_fixture;
 CREATE TABLE msgsite_fixture.inbox_workspaces(id bigint primary key,kind text,status text);
 INSERT INTO msgsite_fixture.inbox_workspaces VALUES(1,'production','active'),(2,'test','active');
 CREATE TABLE msgsite_fixture.channel_accounts(id bigint primary key,workspace_id bigint,channel text);
 CREATE TABLE msgsite_fixture.channel_conversations(id bigint primary key,customer_id bigint,channel_account_id bigint);
 CREATE TABLE msgsite_fixture.customers(id bigint primary key,display_name text,avatar_url text);
 CREATE TABLE msgsite_fixture.provider_connections(id bigint primary key,channel_account_id bigint,status text,account_display_name text,account_username text);
 CREATE TABLE msgsite_fixture.messages(id bigint primary key,channel_conversation_id bigint,direction text,kind text,text_body text,
  attachments jsonb,is_deleted boolean default false,customer_suppressed boolean default false,is_test boolean default false,
  timeline_at timestamptz,created_at timestamptz default now(),updated_at timestamptz default now(),reply_to_message_id bigint,status text);
 CREATE TABLE msgsite_fixture.outbox_events(id bigint generated always as identity,aggregate_type text,aggregate_id bigint,event_type text,payload jsonb,exchange_name text,routing_key text);
 INSERT INTO msgsite_fixture.channel_accounts VALUES(1,1,'instagram');
 INSERT INTO msgsite_fixture.channel_conversations VALUES(2001,3001,1);
 INSERT INTO msgsite_fixture.customers VALUES(3001,'Fixture',NULL),(3002,'Second',NULL);
 INSERT INTO msgsite_fixture.provider_connections VALUES(1,1,'active','FixtureAccount',NULL);`);
 await db.query(readFileSync(process.argv[2],'utf8').replaceAll('app.', 'msgsite_fixture.'));
 await db.query(`INSERT INTO msgsite_fixture.messages(id,channel_conversation_id,direction,kind,text_body,attachments,status)
 VALUES(1001,2001,'inbound','image','Fixture','[{"type":"image","mimeType":"image/jpeg"}]','received')`);
 if((await db.query('SELECT count(*)::int AS n FROM msgsite_fixture.outbox_events')).rows[0].n!==0) throw Error('Disabled emitter wrote');
 await db.query('UPDATE msgsite_fixture.msgsite_settings SET enabled=true');
 await db.query('SELECT msgsite_fixture.msgsite_emit_message(1001)');
 await db.query('SELECT msgsite_fixture.msgsite_emit_message(1001)');
 await db.query("UPDATE msgsite_fixture.messages SET text_body='Edited' WHERE id=1001");
 await db.query('UPDATE msgsite_fixture.channel_conversations SET customer_id=3002 WHERE id=2001');
 await db.query('SELECT msgsite_fixture.msgsite_emit_message(1001)');
 await db.query('DELETE FROM msgsite_fixture.messages WHERE id=1001');
 const rows=(await db.query('SELECT payload FROM msgsite_fixture.outbox_events ORDER BY id')).rows;
 if(rows.length!==4||rows[0].payload.revision!=='1'||rows[2].payload.message.customerId!=='3002'||!rows[3].payload.message.deleted||rows[3].payload.message.text!==null) throw Error('Snapshot regression');
 const jobs=(await db.query('SELECT * FROM msgsite_fixture.msgsite_resync')).rows;
 if(jobs.length!==1) throw Error('Ownership resync missing');
 console.log(JSON.stringify({result:'source_schema_and_snapshots_passed',events:rows.length,rolledBack:true}));
}finally{await db.query('ROLLBACK');await db.end()}
