const $=id=>document.getElementById(id);
let data=null,selected='',key='',busy=false;
async function api(path,payload){
  const response=await fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json','X-Portle-Editor':key},body:JSON.stringify(payload)}:{});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed');return result;
}
function render(){
  if(!data)return;
  $('map').replaceChildren();for(const map of data.maps){const option=document.createElement('option');option.value=map.id;option.textContent=map.name+(map.published?' · Published':'');$('map').append(option);}
  selected=selected||data.maps[0].id;$('map').value=selected;
  $('open-atlas').href='http://127.0.0.1:8741/#'+new URLSearchParams({map:selected});
  const map=data.maps.find(m=>m.id===selected),count=map.draft.filter(Boolean).length;
  $('pack-status').textContent=`${count} / 6 draft screenshots · `+(map.published?'A published set is available for play.':'Not published yet.');
  $('slots').replaceChildren();
  for(let index=0;index<6;index++){
    const slot=document.createElement('section');slot.className='clue-slot';
    const heading=document.createElement('h2');heading.textContent=`Clue ${index+1}`+(index===0?' · First impression':index===5?' · Last chance':'');slot.append(heading);
    if(map.draft[index]){const image=document.createElement('img');image.src=`/api/manage/image/${map.draft[index]}.png`;image.alt=`Draft clue ${index+1}`;slot.append(image);}
    else{const empty=document.createElement('div');empty.className='image-placeholder';empty.textContent='Choose a screenshot';slot.append(empty);}
    const label=document.createElement('label');label.htmlFor='clue-'+index;label.textContent=`SCREENSHOT ${index+1}`;
    const input=document.createElement('input');input.type='file';input.id=label.htmlFor;input.accept='image/png,image/jpeg,image/webp';input.disabled=busy;
    input.onchange=()=>{const file=input.files[0];if(!file)return;run(async()=>{
      if(file.size>8*1024*1024)throw new Error('Choose an image smaller than 8 MiB.');
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read that file.'));reader.readAsDataURL(file);});
      return api('/api/manage/upload',{mapId:selected,slot:index+1,image:content});
    },`Clue ${index+1} saved to draft.`);};
    slot.append(label,input);
    if(map.draft[index]){const clear=document.createElement('button');clear.className='secondary';clear.textContent=`Clear clue ${index+1}`;clear.disabled=busy;clear.onclick=()=>run(()=>api('/api/manage/clear',{mapId:selected,slot:index+1}),'Draft slot cleared; published clues are unchanged.');slot.append(clear);}
    $('slots').append(slot);
  }
  $('map').disabled=busy;$('publish').disabled=busy||count!==6;$('unpublish').disabled=busy||!map.published;
}
async function run(action,message){if(busy)return;busy=true;$('message').textContent='Saving…';render();try{data=await action();$('message').textContent=message;}catch(error){$('message').textContent=error.message;}finally{busy=false;render();}}
$('map').onchange=()=>{selected=$('map').value;$('message').textContent='';render();};
$('publish').onclick=()=>run(()=>api('/api/manage/publish',{mapId:selected}),'Published. New puzzles can use these screenshots.');
$('unpublish').onclick=()=>run(()=>api('/api/manage/unpublish',{mapId:selected}),'Removed from future puzzles. Existing rounds remain available.');
try{data=await api('/api/manage/info');key=data.key;render();}catch(error){$('message').textContent=error.message;}
