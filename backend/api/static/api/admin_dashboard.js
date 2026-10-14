// Same origin as the page Django rendered, so this works wherever it is served.
const API='/api';
// Minted server-side for the staff user who is already signed in; never stored,
// so it dies with the tab instead of lingering in localStorage.
const token=JSON.parse(document.getElementById('admin-access-token').textContent||'""');
let allUsers=[],deleteUserId=null,monthlyData=[],moodData=[];
let mC,mPC,mBC,mDC,tC;
const EC={happy:'#ffd166',sad:'#4da6ff',angry:'#ff4d6d',motivational:'#ff9a3c',fear:'#b06aff',depressing:'#6b7d8e',surprising:'#ff69b4',stressed:'#ff6b6b',calm:'#4dffd2',lonely:'#778899',romantic:'#ff85c8',nostalgic:'#deb887',mixed:'#9370db'};
const EE={happy:'😊',sad:'😢',angry:'😠',motivational:'💪',fear:'😨',depressing:'😔',surprising:'😲',stressed:'😤',calm:'😌',lonely:'🥺',romantic:'💕',nostalgic:'🌅',mixed:'🎭'};
// Display names are free text (spaces allowed since 2026-10-04), so anything a
// user typed goes through esc() before it becomes HTML: a name like
// <img onerror=...> or one with a quote would otherwise run script in a staff
// browser or break the table and its delete buttons.
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function normalizeMoodKey(mood){return String(mood||'').trim().toLowerCase();}
function accentClass(index){return `accent-${index%7}`;}
function moodFillClass(emotion){const key=normalizeMoodKey(emotion);return EC[key]?`mood-fill-${key}`:'mood-fill-default';}
function applyMoodFillWidths(scope=document){scope.querySelectorAll('.mood-bar-fill[data-width]').forEach(bar=>requestAnimationFrame(()=>{bar.style.width=`${bar.dataset.width}%`;}));}

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

function describeFailure(status){
  if(status===401||status===403)return 'Your admin session has expired. Reload the page to sign in again.';
  return 'Could not load dashboard data from the server.';
}

async function loadDashboard(){
  try{
    const h={'Authorization':`Bearer ${token}`};
    const[dR,uR]=await Promise.all([fetch(`${API}/admin/dashboard/`,{headers:h}),fetch(`${API}/admin/users/`,{headers:h})]);
    // Showing invented numbers when the server refuses is worse than showing
    // nothing: an admin cannot tell a real figure from a placeholder.
    if(!dR.ok)throw new Error(describeFailure(dR.status));
    if(!uR.ok)throw new Error(describeFailure(uR.status));
    const dash=await dR.json();const users=await uR.json();
    allUsers=users;monthlyData=dash.monthly_playlists||[];moodData=dash.mood_distribution||[];
    renderStats(users);renderMonthlyChart();renderMoodPie();renderMoodBars();renderActivity(users);
  }catch(e){showToast('⚠ '+e.message,'error');}
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
  el.innerHTML=moodData.slice(0,7).map(m=>{const moodKey=normalizeMoodKey(m.detected_emotion);return `<div class="mood-row"><span class="mood-emoji">${EE[moodKey]||'🎵'}</span><div class="mood-info"><div class="mood-name"><span>${esc(m.detected_emotion)}</span><span class="mood-count">${m.count}</span></div><div class="mood-bar-bg"><div class="mood-bar-fill ${moodFillClass(moodKey)}" data-width="${m.count/max*100}"></div></div></div></div>`;}).join('');
  applyMoodFillWidths(el);
}

function renderActivity(users){
  const el=document.getElementById('recent-activity');if(!el)return;
  const recent=[...users].sort((a,b)=>new Date(b.created_at||0)-new Date(a.created_at||0)).slice(0,5);
  el.innerHTML=recent.map((u,i)=>`<div class="activity-item"><div class="activity-avatar ${accentClass(i)}">${esc((u.username||'U')[0].toUpperCase())}</div><div class="activity-main"><div class="activity-name">${esc(u.username||'User')}</div><div class="activity-meta">Joined ${fmtDate(u.created_at)}</div></div><div class="activity-prompts">${u.prompt_count||0} prompts</div></div>`).join('');
}

let curPage=1;const PER=10;

async function loadUsers(){
  if(!allUsers.length){
    try{
      const r=await fetch(`${API}/admin/users/`,{headers:{'Authorization':`Bearer ${token}`}});
      if(!r.ok)throw new Error(describeFailure(r.status));
      allUsers=await r.json();
    }catch(e){showToast('⚠ '+e.message,'error');}
  }
  renderUsersTable(allUsers);
}

function filterUsers(q){const ql=q.toLowerCase();renderUsersTable(allUsers.filter(u=>(u.username||'').toLowerCase().includes(ql)||(u.email||'').toLowerCase().includes(ql)));}
function renderUsersTable(users){curPage=1;renderPage(users,1);}

function renderPage(users,page){
  const start=(page-1)*PER;const pu=users.slice(start,start+PER);
  document.getElementById('users-tbody').innerHTML=pu.length?pu.map((u,i)=>`<tr><td><div class="user-cell"><div class="user-avatar ${accentClass(start+i)}">${esc((u.username||'U')[0].toUpperCase())}</div><div><div class="user-name">${esc(u.username||'—')}</div><div class="user-email">${esc(u.email||'—')}</div></div></div></td><td class="user-joined">${fmtDate(u.created_at)}</td><td><span class="prompt-count">${u.prompt_count||0}</span></td><td>${u.is_spotify_connected?'<span class="badge green">✓ Connected</span>':'<span class="badge gray">Not connected</span>'}</td><td><button class="delete-btn" onclick="openDeleteModal(${Number(u.id)})">🗑 Delete</button></td></tr>`).join(''):'<tr><td colspan="5" class="table-empty-compact">No users found</td></tr>';
  document.getElementById('users-count').textContent=`${users.length} user${users.length!==1?'s':''}`;
  const tot=Math.ceil(users.length/PER);
  document.getElementById('page-btns').innerHTML=Array.from({length:tot},(_,i)=>`<button class="page-btn ${i+1===page?'active':''}" onclick="changePage(${i+1})">${i+1}</button>`).join('');
}

function changePage(p){const q=document.getElementById('user-search').value.toLowerCase();const f=q?allUsers.filter(u=>(u.username||'').toLowerCase().includes(q)||(u.email||'').toLowerCase().includes(q)):allUsers;curPage=p;renderPage(f,p);}

function openDeleteModal(id){const user=allUsers.find(u=>u.id===id);const name=user?.username||'this user';deleteUserId=id;document.getElementById('modal-text').textContent=`Delete "${name}"? This action cannot be undone.`;document.getElementById('delete-modal').classList.add('open');}
function closeModal(){document.getElementById('delete-modal').classList.remove('open');deleteUserId=null;}

async function confirmDelete(){
  if(!deleteUserId)return;
  try{
    const r=await fetch(`${API}/admin/users/${deleteUserId}/`,{method:'DELETE',headers:{'Authorization':`Bearer ${token}`}});
    // The row used to disappear and report success even on a 403, which hid
    // both permission problems and users that were still there.
    if(!r.ok)throw new Error(describeFailure(r.status));
  }catch(e){showToast('⚠ '+e.message,'error');closeModal();return;}
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
  list.innerHTML=moodData.map(m=>{const moodKey=normalizeMoodKey(m.detected_emotion);return `<div class="mood-detail-row"><span class="mood-detail-emoji">${EE[moodKey]||'🎵'}</span><div class="mood-detail-info"><div class="mood-detail-header"><span class="mood-detail-name">${esc(m.detected_emotion)}</span><span class="mood-detail-meta">${m.count} · ${(m.count/tot*100).toFixed(1)}%</span></div><div class="mood-bar-bg"><div class="mood-bar-fill ${moodFillClass(moodKey)}" data-width="${m.count/max*100}"></div></div></div></div>`;}).join('');
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

loadDashboard();

