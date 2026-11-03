const $=id=>document.getElementById(id);
let round=null,projection='iso',busy=false;
async function api(path,payload){const r=await fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{});const d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');return d;}
function setBusy(value){busy=value;for(const id of ['daily','practice','guess-button','skip'])$(id).disabled=value||(['guess-button','skip'].includes(id)&&round?.status!=='playing');}
async function perform(action){if(busy)return;setBusy(true);$('error').textContent='';try{round=await action();render();await updateStats();}catch(e){$('error').textContent=e.message;}finally{setBusy(false);}}
function render(){
  const active=round.status==='playing';$('clue-title').textContent=`CLUE ${round.turn} / 6`;$('portal-count').textContent=`${round.portalCount} portal${round.portalCount===1?'':'s'} revealed`;
  $('round-label').textContent=(round.mode==='daily'?'DAILY · '+round.day:'PRACTICE')+' / '+(projection==='iso'?'ISOMETRIC':'TOP VIEW');
  $('clue').src=`/api/image/${round.id}.png?version=${round.version}&view=${projection}`;
  $('daily').classList.toggle('active',round.mode==='daily');$('practice').classList.toggle('active',round.mode==='practice');
  $('guess').disabled=!active;$('guess').value='';$('result').hidden=active;$('guess-form').hidden=!active;$('skip').hidden=!active;
  $('status').textContent=active?'Name that arena.':round.status==='won'?'You found it.':'One to remember.';
  $('instruction').textContent=active?'Start with a hunch. You have six guesses.':`The arena was ${round.answer}.`;
  $('turns').replaceChildren();for(let i=0;i<6;i++){const cell=document.createElement('span'),a=round.attempts[i];cell.className=a?(a.correct?'won':a.kind==='skip'?'skipped':'miss'):i===round.attempts.length?'current':'';cell.textContent=a?(a.correct?'✓':a.kind==='skip'?'↗':'×'):String(i+1);$('turns').append(cell);}
  $('history').replaceChildren();for(const a of round.attempts){const row=document.createElement('div');row.className='history-item';const name=document.createElement('span'),result=document.createElement('span');name.textContent=a.name||'Skipped clue';result.textContent=a.correct?'Correct':a.kind==='skip'?'More portals':'Try again';row.append(name,result);$('history').append(row);}
  if(!active)$('share-text').textContent=round.share;
}
async function updateStats(){const s=await api('/api/stats');$('played').textContent=s.played;$('wins').textContent=s.wins;$('streak').textContent=s.currentStreak;}
$('daily').onclick=()=>perform(()=>api('/api/start',{mode:'daily'}));
$('practice').onclick=()=>perform(()=>api('/api/start',{mode:'practice'}));
$('guess-form').onsubmit=event=>{event.preventDefault();const guess=$('guess').value.trim();if(guess)perform(()=>api('/api/action',{id:round.id,version:round.version,guess,eventId:crypto.randomUUID()}));};
$('skip').onclick=()=>perform(()=>api('/api/action',{id:round.id,version:round.version,skip:true,eventId:crypto.randomUUID()}));
$('projection').onclick=()=>{if(!round)return;const guess=$('guess').value;projection=projection==='iso'?'top':'iso';$('projection').textContent=projection==='iso'?'Top view ⤢':'Isometric view ⤢';render();$('guess').value=guess;};
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(round.share);$('copy').textContent='Copied ✓';setTimeout(()=>$('copy').textContent='Copy spoiler-free result',1800);}catch{$('error').textContent='Select and copy the result above.';}};
try{const info=await api('/api/info');$('day').textContent=info.day;$('reset-note').textContent=`A new daily puzzle arrives at midnight ${info.timezone}. Practice does not affect your daily record.`;for(const name of info.maps){const option=document.createElement('option');option.value=name;$('maps').append(option);}await perform(()=>api('/api/start',{mode:'daily'}));}catch(e){$('error').textContent=e.message;}
