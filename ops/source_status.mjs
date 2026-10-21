// Bounded read-only verification; runtime configuration remains on the server.
import {createRequire} from 'node:module';
const require=createRequire('/data/365d-crm/repository/apps/server/package.json');
const {Client}=require('pg');const e=process.env;
const db=new Client({host:e.DATABASE_HOST,port:Number(e.DATABASE_PORT||5432),database:e.DATABASE_NAME,
 user:e.DATABASE_USER,password:e.DATABASE_PASSWORD,ssl:e.DATABASE_SSL==='false'?false:{rejectUnauthorized:e.DATABASE_SSL_REJECT_UNAUTHORIZED!=='false'},statement_timeout:8000});
await db.connect();
try {
 await db.query('BEGIN READ ONLY');
 const settings=(await db.query('SELECT enabled,workspace_ids FROM app.msgsite_settings')).rows;
 const jobs=(await db.query('SELECT count(*)::int AS remaining_resync_jobs FROM app.msgsite_resync')).rows[0];
 const versions=(await db.query('SELECT count(*)::int AS versioned_messages FROM app.msgsite_message_versions')).rows[0];
 console.log(JSON.stringify({settings,...jobs,...versions}));
 await db.query('ROLLBACK');
} finally { await db.end(); }
