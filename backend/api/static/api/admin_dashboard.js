const API='http://127.0.0.1:8000/api';
let token=localStorage.getItem('emotune_admin_token')||'';
let allUsers=[],deleteUserId=null,monthlyData=[],moodData=[];
let mC,mPC,mBC,mDC,tC;
const EC={happy:'#ffd166',sad:'#4da6ff',angry:'#ff4d6d',motivational:'#ff9a3c',fear:'#b06aff',depressing:'#6b7d8e',surprising:'#ff69b4',stressed:'#ff6b6b',calm:'#4dffd2',lonely:'#778899',romantic:'#ff85c8',nostalgic:'#deb887',mixed:'#9370db'};
const EE={happy:'😊',sad:'😢',angry:'😠',motivational:'💪',fear:'😨',depressing:'😔',surprising:'😲',stressed:'😤',calm:'😌',lonely:'🥺',romantic:'💕',nostalgic:'🌅',mixed:'🎭'};
function normalizeMoodKey(mood){return String(mood||'').trim().toLowerCase();}
function accentClass(index){return `accent-${index%7}`;}
function moodFillClass(emotion){const key=normalizeMoodKey(emotion);return EC[key]?`mood-fill-${key}`:'mood-fill-default';}
function applyMoodFillWidths(scope=document){scope.querySelectorAll('.mood-bar-fill[data-width]').forEach(bar=>requestAnimationFrame(()=>{bar.style.width=`${bar.dataset.width}%`;}));}

async function doLogin(){
  const email=document.getElementById('login-email').value.trim();
  const pass=document.getElementById('login-password').value;
  document.getElementById('login-error').style.display='none';
  if(!email||!pass){document.getElementById('login-error').textContent='Please enter email and password.';document.getElementById('login-error').style.display='block';return;}
  try{
    const r=await fetch(`${API}/users/login/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password:pass})});
    const d=await r.json();
    if(d.access){
      if(!d.user?.is_staff&&!d.user?.is_superuser){document.getElementById('login-error').textContent='Access denied. Admin accounts only.';document.getElementById('login-error').style.display='block';return;}
      token=d.access;localStorage.setItem('emotune_admin_token',token);
      document.getElementById('admin-username').textContent=d.user.username||'Admin';
      showApp();loadDashboard();
    } else {
      document.getElementById('login-error').textContent=d.error||'Invalid credentials.';
      document.getElementById('login-error').style.display='block';
    }
  }catch(e){
    document.getElementById('login-error').textContent='Cannot connect to server at '+API+'. Make sure Django is running.';
    document.getElementById('login-error').style.display='block';
  }
}

function showApp(){document.getElementById('login-page').style.display='none';document.getElementById('app').style.display='flex';}
function doLogout(){localStorage.removeItem('emotune_admin_token');token='';location.reload();}

function showPage(name,el){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  document.getElementById('page-'+name).classList.add('active');el.classList.add('active');
  const titles={dashboard:'Admin <span>Dashboard</span>',users:'User <span>Management</span>',moods:'Mood <span>Analytics</span>',playlists:'Playlist <span>Statistics</span>'};
  document.getElementById('topbar-title').innerHTML=titles[name]||name;
  if(name==='users')loadUsers();
  if(name==='moods')renderMoodAnalytics();
  if(name==='playlists')renderPlaylists();
}

async function loadDashboard(){
  try{
    const h={'Authorization':`Bearer ${token}`};
    const[dR,uR]=await Promise.all([fetch(`${API}/admin/dashboard/`,{headers:h}),fetch(`${API}/admin/users/`,{headers:h})]);
    if(!dR.ok)throw new Error('Auth failed');
    const dash=await dR.json();const users=await uR.json();
    allUsers=users;monthlyData=dash.monthly_playlists||[];moodData=dash.mood_distribution||[];
    renderStats(users);renderMonthlyChart();renderMoodPie();renderMoodBars();renderActivity(users);
  }catch(e){console.warn('Using demo data:',e.message);loadDemo();}
}

function loadDemo(){
  allUsers=genUsers();
  monthlyData=[{month:'2024-10-01',count:45},{month:'2024-11-01',count:62},{month:'2024-12-01',count:88},{month:'2025-01-01',count:71},{month:'2025-02-01',count:95},{month:'2025-03-01',count:112}];
  moodData=[{detected_emotion:'sad',count:234},{detected_emotion:'happy',count:198},{detected_emotion:'stressed',count:167},{detected_emotion:'lonely',count:143},{detected_emotion:'motivational',count:121},{detected_emotion:'calm',count:98},{detected_emotion:'angry',count:87},{detected_emotion:'romantic',count:76},{detected_emotion:'nostalgic',count:65},{detected_emotion:'fear',count:54},{detected_emotion:'depressing',count:43},{detected_emotion:'surprising',count:38},{detected_emotion:'mixed',count:29}];
  renderStats(allUsers);renderMonthlyChart();renderMoodPie();renderMoodBars();renderActivity(allUsers);
}

function renderStats(users){
  document.getElementById('stat-total').textContent=users.length;
  document.getElementById('stat-total-change').textContent='↑ Active users';
  const sc=users.filter(u=>u.is_spotify_connected).length;
  document.getElementById('stat-spotify').textContent=sc;
  document.getElementById('stat-spotify-change').textContent=users.length?`${Math.round(sc/users.length*100)}% of users`:'0%';
  document.getElementById('stat-prompts').textContent=moodData.reduce((s,m)=>s+m.count,0);
  if(moodData.length){const t=moodData[0];document.getElementById('stat-top-mood').textContent=(EE[t.detected_emotion]||'')+' '+t.detected_emotion;document.getElementById('stat-top-mood-count').textContent=`${t.count} prompts`;}
}

function renderMonthlyChart(){
  const ctx=document.getElementById('monthlyChart');if(!ctx)return;if(mC)mC.destroy();
  mC=new Chart(ctx,{type:'line',data:{labels:monthlyData.map(d=>{const dt=new Date(d.month);return dt.toLocaleDateString('en',{month:'short',year:'2-digit'});}),datasets:[{label:'Playlists',data:monthlyData.map(d=>d.count),borderColor:'#9eff65',backgroundColor:'rgba(158,255,101,.08)',borderWidth:2,pointBackgroundColor:'#9eff65',pointRadius:4,fill:true,tension:.4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'#1e2730'},ticks:{color:'#6b7d8e',font:{size:11}}},y:{grid:{color:'#1e2730'},ticks:{color:'#6b7d8e',font:{size:11}},beginAtZero:true}}}});
}

function renderMoodPie(){
  const ctx=document.getElementById('moodPieChart');if(!ctx)return;if(mPC)mPC.destroy();
  const t6=moodData.slice(0,6);
  mPC=new Chart(ctx,{type:'doughnut',data:{labels:t6.map(m=>m.detected_emotion),datasets:[{data:t6.map(m=>m.count),backgroundColor:t6.map(m=>EC[m.detected_emotion]||'#6b7d8e'),borderColor:'#131920',borderWidth:3}]},options:{responsive:true,maintainAspectRatio:false,cutout:'65%',plugins:{legend:{position:'bottom',labels:{color:'#6b7d8e',font:{size:10},padding:8,boxWidth:10}}}}});
}

function renderMoodBars(){
  const el=document.getElementById('mood-bars');if(!el)return;
  const max=moodData[0]?.count||1;
  el.innerHTML=moodData.slice(0,7).map(m=>{const moodKey=normalizeMoodKey(m.detected_emotion);return `<div class="mood-row"><span class="mood-emoji">${EE[moodKey]||'🎵'}</span><div class="mood-info"><div class="mood-name"><span>${m.detected_emotion}</span><span class="mood-count">${m.count}</span></div><div class="mood-bar-bg"><div class="mood-bar-fill ${moodFillClass(moodKey)}" data-width="${m.count/max*100}"></div></div></div></div>`;}).join('');
  applyMoodFillWidths(el);
}

function renderActivity(users){
  const el=document.getElementById('recent-activity');if(!el)return;
  const recent=[...users].sort((a,b)=>new Date(b.created_at||0)-new Date(a.created_at||0)).slice(0,5);
  el.innerHTML=recent.map((u,i)=>`<div class="activity-item"><div class="activity-avatar ${accentClass(i)}">${(u.username||'U')[0].toUpperCase()}</div><div class="activity-main"><div class="activity-name">${u.username||'User'}</div><div class="activity-meta">Joined ${fmtDate(u.created_at)}</div></div><div class="activity-prompts">${u.prompt_count||0} prompts</div></div>`).join('');
}

let curPage=1;const PER=10;

async function loadUsers(){
  if(!allUsers.length){try{const r=await fetch(`${API}/admin/users/`,{headers:{'Authorization':`Bearer ${token}`}});if(r.ok)allUsers=await r.json();else throw new Error();}catch(e){if(!allUsers.length)allUsers=genUsers();}}
  renderUsersTable(allUsers);
}

function filterUsers(q){const ql=q.toLowerCase();renderUsersTable(allUsers.filter(u=>(u.username||'').toLowerCase().includes(ql)||(u.email||'').toLowerCase().includes(ql)));}
function renderUsersTable(users){curPage=1;renderPage(users,1);}

function renderPage(users,page){
  const start=(page-1)*PER;const pu=users.slice(start,start+PER);
  document.getElementById('users-tbody').innerHTML=pu.length?pu.map((u,i)=>`<tr><td><div class="user-cell"><div class="user-avatar ${accentClass(start+i)}">${(u.username||'U')[0].toUpperCase()}</div><div><div class="user-name">${u.username||'—'}</div><div class="user-email">${u.email||'—'}</div></div></div></td><td class="user-joined">${fmtDate(u.created_at)}</td><td><span class="prompt-count">${u.prompt_count||0}</span></td><td>${u.is_spotify_connected?'<span class="badge green">✓ Connected</span>':'<span class="badge gray">Not connected</span>'}</td><td><button class="delete-btn" onclick="openDeleteModal(${u.id},'${(u.username||'').replace(/'/g,'')}')" >🗑 Delete</button></td></tr>`).join(''):'<tr><td colspan="5" class="table-empty-compact">No users found</td></tr>';
  document.getElementById('users-count').textContent=`${users.length} user${users.length!==1?'s':''}`;
  const tot=Math.ceil(users.length/PER);
  document.getElementById('page-btns').innerHTML=Array.from({length:tot},(_,i)=>`<button class="page-btn ${i+1===page?'active':''}" onclick="changePage(${i+1})">${i+1}</button>`).join('');
}

function changePage(p){const q=document.getElementById('user-search').value.toLowerCase();const f=q?allUsers.filter(u=>(u.username||'').toLowerCase().includes(q)||(u.email||'').toLowerCase().includes(q)):allUsers;curPage=p;renderPage(f,p);}

function openDeleteModal(id,name){deleteUserId=id;document.getElementById('modal-text').textContent=`Delete "${name}"? This action cannot be undone.`;document.getElementById('delete-modal').classList.add('open');}
function closeModal(){document.getElementById('delete-modal').classList.remove('open');deleteUserId=null;}

async function confirmDelete(){
  if(!deleteUserId)return;
  try{await fetch(`${API}/admin/users/${deleteUserId}/`,{method:'DELETE',headers:{'Authorization':`Bearer ${token}`}});}catch(e){}
  allUsers=allUsers.filter(u=>u.id!==deleteUserId);
  showToast('✅ User deleted successfully','success');closeModal();renderUsersTable(allUsers);
}

function renderMoodAnalytics(){
  if(!moodData.length)return;
  const bCtx=document.getElementById('moodBarChart');
  if(bCtx){if(mBC)mBC.destroy();mBC=new Chart(bCtx,{type:'bar',data:{labels:moodData.map(m=>m.detected_emotion),datasets:[{data:moodData.map(m=>m.count),backgroundColor:moodData.map(m=>EC[normalizeMoodKey(m.detected_emotion)]||'#9eff65'),borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'#1e2730'},ticks:{color:'#6b7d8e',font:{size:10}}},y:{grid:{color:'#1e2730'},ticks:{color:'#6b7d8e'},beginAtZero:true}}}});}
  const dCtx=document.getElementById('moodDonutChart');
  if(dCtx){if(mDC)mDC.destroy();mDC=new Chart(dCtx,{type:'doughnut',data:{labels:moodData.map(m=>m.detected_emotion),datasets:[{data:moodData.map(m=>m.count),backgroundColor:moodData.map(m=>EC[normalizeMoodKey(m.detected_emotion)]||'#9eff65'),borderColor:'#131920',borderWidth:3}]},options:{responsive:true,maintainAspectRatio:false,cutout:'60%',plugins:{legend:{position:'right',labels:{color:'#6b7d8e',font:{size:10},padding:6,boxWidth:10}}}}});}
  const tot=moodData.reduce((s,m)=>s+m.count,0);const max=moodData[0]?.count||1;
  const list=document.getElementById('mood-detail-list');
  list.innerHTML=moodData.map(m=>{const moodKey=normalizeMoodKey(m.detected_emotion);return `<div class="mood-detail-row"><span class="mood-detail-emoji">${EE[moodKey]||'🎵'}</span><div class="mood-detail-info"><div class="mood-detail-header"><span class="mood-detail-name">${m.detected_emotion}</span><span class="mood-detail-meta">${m.count} · ${(m.count/tot*100).toFixed(1)}%</span></div><div class="mood-bar-bg"><div class="mood-bar-fill ${moodFillClass(moodKey)}" data-width="${m.count/max*100}"></div></div></div></div>`;}).join('');
  applyMoodFillWidths(list);
}

function renderPlaylists(){
  const at=monthlyData.reduce((s,m)=>s+m.count,0);
  document.getElementById('pl-total').textContent=at;
  document.getElementById('pl-this-month').textContent=monthlyData[monthlyData.length-1]?.count||0;
  document.getElementById('pl-last-month').textContent=monthlyData[monthlyData.length-2]?.count||0;
  const ctx=document.getElementById('playlistTrendChart');if(!ctx)return;if(tC)tC.destroy();
  tC=new Chart(ctx,{type:'bar',data:{labels:monthlyData.map(d=>{const dt=new Date(d.month);return dt.toLocaleDateString('en',{month:'long',year:'numeric'});}),datasets:[{label:'Playlists',data:monthlyData.map(d=>d.count),backgroundColor:'rgba(158,255,101,.15)',borderColor:'#9eff65',borderWidth:2,borderRadius:8}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'#1e2730'},ticks:{color:'#6b7d8e'}},y:{grid:{color:'#1e2730'},ticks:{color:'#6b7d8e'},beginAtZero:true}}}});
}

function fmtDate(s){if(!s)return'—';try{return new Date(s).toLocaleDateString('en',{month:'short',day:'numeric',year:'numeric'});}catch(e){return'—';}}
function showToast(msg,type='success'){const t=document.getElementById('toast');t.textContent=msg;t.className=`toast ${type} show`;setTimeout(()=>t.classList.remove('show'),3000);}

function genUsers(){
  const ns=['maria_santos','juan_dela_cruz','ana_reyes','carlos_garcia','lea_mendoza','miguel_torres','grace_lim','ryan_uy','jasmine_go','kevin_tan','patricia_cruz','mark_ramos','claire_dg','jerome_sy','kate_villanueva'];
  return ns.map((n,i)=>({id:i+1,username:n,email:`${n}@gmail.com`,is_spotify_connected:Math.random()>.4,created_at:new Date(Date.now()-Math.random()*90*86400000).toISOString(),prompt_count:Math.floor(Math.random()*80)+1}));
}

document.getElementById('login-password').addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
// Auto-login if token saved
if(token){showApp();loadDashboard();}

