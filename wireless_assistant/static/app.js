'use strict';
const $=id=>document.getElementById(id);
let csrf='', current=null, active=null, sessionCursor=null, messageCursor=null, watchId=0, sending=false, ready=false;
let pending=null;
const terminal=new Set(['COMPLETED','CANCELED','FAILED','TIMED_OUT','INTERRUPTED']);
function notice(text){$('notice').textContent=text;$('notice').hidden=!text;}
async function api(path,method='GET',body=null,key=null){
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
 try{
  const headers={};if(method!=='GET'){headers['Content-Type']='application/json';headers['X-WA-CSRF']=csrf;headers['Idempotency-Key']=key||crypto.randomUUID();}
  const response=await fetch(path,{method,headers,body:body===null?null:JSON.stringify(body),signal:controller.signal});
  const data=await response.json();if(!response.ok)throw new Error(data.error?.message||'Request failed.');return data.data;
 }catch(e){if(e.name==='AbortError')throw new Error('The connection timed out. Check saved chat status before sending again.');throw e;}finally{clearTimeout(timeout);}
}
function controls(){
 const busy=active?.status==='ACTIVE';const waiting=active?.status==='WAITING_USER';
 $('send').disabled=sending||busy||!ready;$('question').disabled=sending||busy;
 $('send').textContent=waiting?'Reply ↑':'Send ↑';$('composer-label').textContent=waiting?'Reply to the saved clarification':'Ask about the prepared 3GPP collection';
 $('rename-chat').hidden=!current;$('delete-chat').hidden=!current;
 $('run-status').hidden=!active||terminal.has(active.status);
 $('busy-indicator').hidden=!busy;$('run-label').textContent=waiting?'Waiting for your reply — processing is paused':busy?({NEED:'Understanding your question',A:'Collecting context',B:'Writing an answer',C:'Checking the answer'}[active.stage]||'Processing your question'):'';
 $('cancel-run').hidden=!active||terminal.has(active.status);
}
async function listChats(append=false){
 const result=await api('/api/sessions?query='+encodeURIComponent($('chat-search').value)+'&cursor='+(append?(sessionCursor||0):0));
 if(!append)$('chat-list').replaceChildren();sessionCursor=result.next_cursor;$('more-chats').hidden=sessionCursor===null;
 for(const chat of result.items){const b=document.createElement('button');b.className='chat-item'+(chat.session_id===current?.session_id?' active':'');b.textContent=chat.title;b.onclick=()=>openChat(chat.session_id).catch(e=>notice(e.message));$('chat-list').append(b);}
}
function renderMessage(m,before=null){
 if(document.getElementById('message-'+m.message_id))return;
 const article=document.createElement('article');article.id='message-'+m.message_id;article.className='message '+m.role;
 const label=document.createElement('div');label.className='role';label.textContent=m.role==='user'?'You':m.role==='assistant'?'Wireless Assistant · Reviewed':m.role==='clarification'?'Clarification':'Status';
 const body=document.createElement('div');body.className='message-body';body.textContent=m.content_text;
 article.append(label,body);
 if(m.citations){
  const sources=document.createElement('div');sources.className='sources';
  for(const citation of m.citations){for(const pid of citation.passage_ids){const button=document.createElement('button');button.textContent=citation.marker+' View source';button.onclick=()=>showSource(m.run_id,m.outcome.evidence_set_id,pid).catch(e=>notice(e.message));sources.append(button);}}
  article.append(sources);
  const feedback=document.createElement('div');feedback.className='feedback';feedback.append(document.createTextNode('Report an issue:'));
  for(const category of ['wrong','unclear','irrelevant','incomplete']){const b=document.createElement('button');b.textContent=category;b.onclick=async()=>{try{await api('/api/feedback','POST',{run_id:m.run_id,candidate_id:m.outcome.candidate_id,category,comment:null});b.textContent='Saved';b.disabled=true;}catch(e){notice(e.message);}};feedback.append(b);}article.append(feedback);
 }
 if(m.outcome?.retryable){const b=document.createElement('button');b.textContent='Retry this question';b.onclick=async()=>{try{const receipt=await api('/api/runs/'+m.run_id+'/retry','POST',{});await follow(receipt.run_id);}catch(e){notice(e.message);}};article.append(b);}
 $('messages').insertBefore(article,before);
}
async function loadMessages(append=false){
 if(!current)return;const id=current.session_id;
 const result=await api('/api/sessions/'+id+'/messages'+(append?'?before='+messageCursor:'?latest=true'));
 if(current?.session_id!==id)return;
 if(!append)$('messages').replaceChildren();const anchor=append?$('messages').firstChild:null;result.items.forEach(m=>renderMessage(m,anchor));
 messageCursor=result.previous_cursor;$('more-messages').hidden=messageCursor===null;
 $('welcome').hidden=result.items.length>0||append;
}
async function openChat(id){
 ++watchId;notice('');current=await api('/api/sessions/'+id);$('chat-title').textContent=current.title;active=current.active_run;
 await loadMessages();await listChats();controls();if(active?.status==='ACTIVE')watch(active.run_id);
}
async function newChat(){
 const chat=await api('/api/sessions','POST',{title:null});await openChat(chat.session_id);$('question').focus();
}
async function follow(rid){
 active=await api('/api/runs/'+rid);await loadMessages();controls();if(active.status==='ACTIVE')watch(rid);
}
async function watch(rid){
 const own=++watchId;let failures=0;
 $('refresh-status').hidden=true;
 // No automatic generation retry. Polling stops on idle/terminal or bounded loss of contact.
 for(let count=0;count<240&&own===watchId;count++){
  try{const status=await api('/api/runs/'+rid);if(own!==watchId)return;active=status;failures=0;controls();
   if(status.status!=='ACTIVE'){await loadMessages();return;}
  }catch(e){if(++failures>=3){notice('Connection lost. Processing status is unknown; use Check status. Your question will not be resubmitted.');break;}}
  await new Promise(resolve=>setTimeout(resolve,1000));
 }
 if(own===watchId){$('busy-indicator').hidden=true;$('run-label').textContent='Status unavailable — check before retrying';$('refresh-status').hidden=false;}
}
async function send(event){
 event.preventDefault();if(sending||active?.status==='ACTIVE')return;const text=$('question').value;if(!text.trim())return;
 if(new TextEncoder().encode(text).length>4000){notice('Question exceeds the 4,000-byte input limit. Please shorten it.');return;}
 sending=true;controls();notice('');
 try{
  if(!current){const chat=await api('/api/sessions','POST',{title:text.slice(0,70)});current=chat;$('chat-title').textContent=chat.title;await listChats();}
  const waiting=active?.status==='WAITING_USER';
  const path=waiting?'/api/runs/'+active.run_id+'/clarifications/'+active.pending_clarification.clarification_id+'/reply':'/api/sessions/'+current.session_id+'/messages';
  const body=waiting?{text,expected_run_version:active.state_version}:{text};
  if(!pending||pending.path!==path||JSON.stringify(pending.body)!==JSON.stringify(body))pending={path,body,key:crypto.randomUUID()};
  const receipt=await api(path,'POST',body,pending.key);pending=null;$('question').value='';await follow(receipt.run_id);
 }catch(e){notice(e.message);if(current){try{current=await api('/api/sessions/'+current.session_id);active=current.active_run;await loadMessages();if(active?.status==='ACTIVE')watch(active.run_id);}catch(_){}}}
 finally{sending=false;controls();}
}
async function showSource(rid,eid,pid){
 const p=await api('/api/runs/'+rid+'/evidence/'+eid+'/'+pid);$('source-title').textContent='TS '+p.spec_number+' · Clause '+p.clause_id;
 $('source-meta').textContent='Release '+p.release+' · Version '+p.document_version+' · PDF page '+p.page_location;
 $('source-text').textContent=p.text;const url=new URL(p.source_uri);
 $('source-link').hidden=!(url.protocol==='https:'&&['etsi.org','www.etsi.org'].includes(url.hostname));
 if(!$('source-link').hidden)$('source-link').href=p.source_uri+'#page='+encodeURIComponent(p.page_location);
 $('source-dialog').showModal();
}
$('composer').onsubmit=send;
$('question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('composer').requestSubmit();}};
$('new-chat').onclick=()=>newChat().catch(e=>notice(e.message));
$('more-chats').onclick=()=>listChats(true).catch(e=>notice(e.message));
$('more-messages').onclick=()=>loadMessages(true).catch(e=>notice(e.message));
let searchTimer;$('chat-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>listChats().catch(e=>notice(e.message)),250);};
$('rename-chat').onclick=async()=>{const title=prompt('Chat title',current.title);if(!title?.trim())return;try{current=await api('/api/sessions/'+current.session_id,'PATCH',{title,expected_session_version:current.state_version});$('chat-title').textContent=current.title;await listChats();}catch(e){notice(e.message);}};
$('delete-chat').onclick=async()=>{if(!confirm('Delete this chat and its saved messages, sources and feedback?'))return;try{await api('/api/sessions/'+current.session_id,'DELETE');++watchId;current=null;active=null;pending=null;$('messages').replaceChildren();$('welcome').hidden=false;$('chat-title').textContent='Wireless Assistant';controls();await listChats();}catch(e){notice(e.message);}};
$('cancel-run').onclick=async()=>{if(!active)return;try{active=await api('/api/runs/'+active.run_id+'/cancel','POST',{});++watchId;await loadMessages();controls();}catch(e){notice(e.message);}};
$('refresh-status').onclick=()=>active&&follow(active.run_id).catch(e=>notice(e.message));
$('close-source').onclick=()=>$('source-dialog').close();
$('corpus-badge').onclick=async()=>{try{const c=await api('/api/corpus/status');$('source-title').textContent='Prepared source collection';$('source-meta').textContent=c.ready?'Hybrid collection ready':'Collection setup incomplete';$('source-text').textContent=c.documents.map(d=>'TS '+d.spec_number+' · v'+d.version+'\n'+d.title).join('\n\n')+'\n\n'+c.coverage_gaps.join('\n');$('source-link').hidden=true;$('source-dialog').showModal();}catch(e){notice(e.message);}};
for(const b of document.querySelectorAll('[data-question]'))b.onclick=()=>{$('question').value=b.dataset.question;$('question').focus();};
(async()=>{try{const boot=await api('/api/bootstrap');csrf=boot.csrf_token;const health=await api('/api/health');ready=health.ready;
 if(!ready){$('setup-notice').hidden=false;$('setup-notice').textContent='Setup required: '+(!health.provider_configured?'configure the server’s free AI API access. ':'')+(!health.corpus_ready?'Prepare and activate the searchable corpus. ':'')+'Saved chats remain available. See the repository setup guide.';}
 await listChats();controls();}catch(e){notice(e.message);$('send').disabled=true;}})();
