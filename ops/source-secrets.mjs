// Output is piped directly through SSH into the target's restricted configuration.
// Never run this file without that sink, and never capture or print its stdout.
import {writeFileSync,existsSync,readFileSync} from 'node:fs';
import {randomBytes} from 'node:crypto';
const path='/data/365d-crm/config/msgsite.env';
if(!existsSync(path)) writeFileSync(path,'MSGSITE_MEDIA_TOKEN='+randomBytes(32).toString('hex')+'\nMSGSITE_WORKSPACE_IDS=1\n',{mode:0o600});
const content=readFileSync(path,'utf8');
const token=content.match(/^MSGSITE_MEDIA_TOKEN=(.+)$/m)?.[1];
if(!token) throw Error('Token absent');
const url=new URL(process.env.RABBITMQ_URL);url.hostname='127.0.0.1';url.port='35672';
process.stdout.write('CRM_TO_CHAT_AMQP_URL='+url.toString()+'\nCRM_MEDIA_TOKEN='+token+'\nCRM_TO_CHAT_WRITE_ENABLED=true\nCRM_TO_CHAT_WORKSPACE_IDS=1\n');
