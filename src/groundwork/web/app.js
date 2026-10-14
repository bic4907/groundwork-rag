'use strict';
const $ = (id) => document.getElementById(id);
const escapeHTML = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (v) => v == null ? 'N/A' : (Number(v)*100).toFixed(1)+'%';
let accessToken = '', gold = [], runs = [], currentReview = null, corpusOffset = 0, corpusTotal = 0, activeJob = null;
const labels = {evidence_recall:'Evidence recall',all_evidence_found:'All evidence found',answer_token_f1:'Answer token F1',answer_exact_match:'Exact match',citation_validity:'Citation validity',judge_correctness:'Judge correctness',citation_support:'Citation support',abstention_precision:'Abstention precision',abstention_recall:'Abstention recall',abstention_f1:'Abstention F1',error_rate:'Error rate',answer_rate:'Answer rate'};

function notice(text) { $('notice').textContent = text; $('notice').hidden = !text; }
function fail(error) { notice(error.message || String(error)); }
async function api(path, options={}) {
  const headers = {'Content-Type':'application/json', ...(options.headers || {})};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const response = await fetch('/api'+path, {...options, headers});
  if (response.status === 401) { $('auth-dialog').showModal(); throw new Error('앱 접근 토큰을 입력하세요.'); }
  if (!response.ok) { const body = await response.json().catch(()=>({})); throw new Error(typeof body.detail === 'string' ? body.detail : `요청 실패 (${response.status})`); }
  return response;
}
async function json(path, options) { return (await api(path, options)).json(); }
function buttonBusy(button, busy, text) { button.disabled = busy; if (text) button.textContent = text; }
function setView(view) {
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== 'view-'+view);
  document.querySelectorAll('.nav').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  $('breadcrumb').textContent = document.querySelector(`.nav[data-view="${view}"]`).textContent.trim().slice(1).trim();
  if (view === 'corpus') loadCorpus().catch(fail);
  if (view === 'experiments' || view === 'review') loadRuns().catch(fail);
  window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('.nav').forEach(button => button.addEventListener('click',()=>setView(button.dataset.view)));

async function boot() {
  const state = await json('/status');
  $('connection-text').textContent = 'Workspace connected';
  $('connection-dot').classList.remove('offline');
  $('model-tag').textContent = `${state.models.generation.provider} / ${state.models.generation.model}`;
  const index = state.indexes.find(x=>x.corpus_sha256 === state.dataset?.corpus_sha256);
  $('stats').innerHTML = [[state.dataset?.documents ?? '—','source documents'],[state.dataset?.questions ?? '—','gold questions'],[index?.chunks ?? '—','indexed chunks'],[3,'retrieval strategies']].map(([n,label])=>`<div><strong>${escapeHTML(n)}</strong><span>${label}</span></div>`).join('');
  gold = await json('/gold');
  const examples = [gold.find(g=>g.category==='comparison'),gold.find(g=>g.category==='bridge'),gold.find(g=>g.category==='summary')].filter(Boolean);
  $('suggestions').innerHTML = examples.map(g=>`<button type="button" data-question="${escapeHTML(g.id)}">${escapeHTML(g.category==='comparison'?'비교 질문':g.category==='summary'?'문서 요약':'다중 문서 추론')} ↗</button>`).join('');
  if (!index) notice('아직 인덱스가 없습니다. Corpus 탭에서 인덱스를 준비하세요.');
  $('eval-judge').disabled = state.models.judge.provider === 'disabled';
  await loadRuns();
}
$('suggestions').addEventListener('click', e=>{ const b=e.target.closest('[data-question]'); if(b){$('question').value=gold.find(x=>x.id===b.dataset.question).question;$('question').focus();} });
$('auth-form').addEventListener('submit', async e=>{e.preventDefault();accessToken=$('access-token').value;$('access-token').value='';$('auth-dialog').close();notice('');try{await boot();}catch(err){fail(err);} });

function evidence(hits) {
  $('evidence-count').textContent=hits.length;
  $('evidence-list').innerHTML=hits.map((hit,i)=>{const c=hit.chunk;return `<article class="source" id="source-${escapeHTML(c.id)}"><div class="source-top"><span class="source-num">${i+1}</span><small>score ${Number(hit.score).toFixed(3)}</small></div><h3>${escapeHTML(c.title)}</h3><p>${escapeHTML(c.text.slice(0,190))}${c.text.length>190?'…':''}</p><details><summary>전체 근거 보기</summary><p>${escapeHTML(c.text)}</p><small>${escapeHTML(c.id)}<br>Dense ${hit.dense_score.toFixed(3)} · BM25 ${hit.bm25_score.toFixed(2)}</small><p><a href="${escapeHTML(c.url)}" target="_blank" rel="noopener noreferrer">원문 출처 ↗</a></p></details></article>`;}).join('');
}
function stage(message) { $('answer-area').innerHTML=`<div class="stage"><span class="spinner" aria-hidden="true"></span>${escapeHTML(message)}</div>`; }
function renderAnswer(result) {
  evidence(result.retrieval);
  const answered=result.status==='answered';
  const index=new Map(result.retrieval.map((h,i)=>[h.chunk.id,i+1]));
  const claims=result.claims.map(c=>`<p>${escapeHTML(c.text)} ${c.evidence.map(ev=>`<button class="citation" title="인용 근거 확인" data-citation="${escapeHTML(ev.chunk_id)}">${index.get(ev.chunk_id)}</button>`).join('')}</p>`).join('');
  $('answer-area').innerHTML=`<article class="answer-card"><div class="answer-heading"><span class="eyebrow">${answered?'GROUNDED RESPONSE':'INSUFFICIENT EVIDENCE'}</span><span class="badge ${answered?'':'warning'}">${answered?'인용 검증됨':'답변 보류'}</span></div>${answered?`<p class="short-answer">${escapeHTML(result.short_answer)}</p>${claims}`:`<h2>문서에서 충분한 근거를 찾지 못했습니다.</h2><p>${escapeHTML(result.reason)}</p>`}<div class="answer-footer"><span>${(result.timings.total_ms/1000).toFixed(2)}s total</span><span>${Math.round(result.timings.retrieval_ms)}ms retrieval</span><span>${result.retrieval.length} chunks</span><span>${escapeHTML(result.config)}</span></div><p class="fine">인용 ID와 원문 구절을 검증했습니다. 의미적 뒷받침 여부는 별도 평가 대상입니다.</p></article>`;
}
$('answer-area').addEventListener('click',e=>{const b=e.target.closest('[data-citation]');if(!b)return;document.querySelectorAll('.source').forEach(s=>s.classList.remove('selected'));const target=$('source-'+b.dataset.citation);if(target){target.classList.add('selected');target.querySelector('details').open=true;target.scrollIntoView({behavior:'smooth',block:'nearest'});}});
$('ask-form').addEventListener('submit',async e=>{
  e.preventDefault();notice('');buttonBusy($('ask-button'),true,'검색 중…');stage('질문에 관련된 근거를 찾고 있습니다.');
  try {
    const response=await api('/qa/stream',{method:'POST',body:JSON.stringify({question:$('question').value.trim(),config:$('query-config').value})});
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',terminal=false;
    function handle(block){const event=block.split('\n').find(l=>l.startsWith('event: '))?.slice(7);const raw=block.split('\n').find(l=>l.startsWith('data: '))?.slice(6);if(!raw)return;const data=JSON.parse(raw);if(event==='evidence')evidence(data.hits);if(event==='generating'){stage('찾은 문서로 답변을 작성하고 인용을 검증하고 있습니다.');$('ask-button').textContent='답변 작성 중…';}if(event==='answer'){renderAnswer(data);terminal=true;}if(event==='error'){terminal=true;throw new Error(data.detail);}}
    while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let end;while((end=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,end);buffer=buffer.slice(end+2);handle(block);}if(done)break;}
    if(!terminal)throw new Error('응답 연결이 종료되었습니다. 다시 시도하세요.');
  }catch(error){$('answer-area').innerHTML=`<div class="error-box">${escapeHTML(error.message)}</div>`;}finally{buttonBusy($('ask-button'),false,'질문하기 ↗');}
});

async function loadCorpus(){const q=$('corpus-search').value;const data=await json(`/corpus?q=${encodeURIComponent(q)}&offset=${corpusOffset}&limit=12`);corpusTotal=data.total;$('corpus-meta').textContent=`${data.total} documents · Historical snapshot · CC BY-SA 4.0`;$('corpus-list').innerHTML=data.documents.map(d=>`<article class="corpus-doc"><span class="eyebrow">PUBLIC DOCUMENT</span><h2>${escapeHTML(d.title)}</h2><p>${escapeHTML(d.sentences[0]?.text||'')}</p><details><summary>${d.sentences.length}개 문장과 ID 확인</summary>${d.sentences.map(s=>`<div class="sentence"><code>${escapeHTML(s.id)}</code><p>${escapeHTML(s.text)}</p></div>`).join('')}<p><a href="${escapeHTML(d.url)}" target="_blank" rel="noopener noreferrer">Wikipedia 출처 ↗</a></p></details></article>`).join('')||'<p class="fine">검색 결과가 없습니다.</p>';$('corpus-page').textContent=`${data.total?corpusOffset+1:0}–${Math.min(corpusOffset+12,data.total)} / ${data.total}`;$('corpus-prev').disabled=corpusOffset===0;$('corpus-next').disabled=corpusOffset+12>=data.total;}
let corpusTimer;$('corpus-search').addEventListener('input',()=>{clearTimeout(corpusTimer);corpusTimer=setTimeout(()=>{corpusOffset=0;loadCorpus().catch(fail);},250);});
$('corpus-prev').addEventListener('click',()=>{corpusOffset=Math.max(0,corpusOffset-12);loadCorpus().catch(fail);});
$('corpus-next').addEventListener('click',()=>{corpusOffset+=12;loadCorpus().catch(fail);});

async function loadRuns(){runs=await json('/runs');$('run-history').innerHTML=runs.length?`<table><thead><tr><th>Configuration / run</th><th>Split</th><th>Recall</th><th>Token F1</th><th>Errors</th><th>Status</th></tr></thead><tbody>${runs.map(r=>`<tr><td><button class="text-button" data-run="${escapeHTML(r.manifest.run_id)}">${escapeHTML(r.manifest.config.name)} ↗</button><br><span class="mono">${escapeHTML(r.manifest.run_id)}</span></td><td>${escapeHTML(r.manifest.split)} · ${r.manifest.question_count}${r.manifest.limited?' · limited':''}</td><td>${fmt(r.summary?.metrics.evidence_recall)}</td><td>${fmt(r.summary?.metrics.answer_token_f1)}</td><td>${fmt(r.summary?.metrics.error_rate)}</td><td><span class="badge">${escapeHTML(r.manifest.status)}</span></td></tr>`).join('')}</tbody></table>`:'<div class="card"><p>아직 실행 기록이 없습니다. 첫 평가를 시작하세요.</p></div>';
  const complete=runs.filter(r=>r.manifest.status==='completed'&&!r.manifest.limited);
  for(const id of ['before-run','after-run','review-run']){const previous=$(id).value;const eligible=id==='review-run'?complete:complete.filter(r=>r.manifest.split!=='dev');$(id).innerHTML='<option value="">실행 선택</option>'+eligible.map(r=>`<option value="${escapeHTML(r.manifest.run_id)}">${escapeHTML(r.manifest.config.name)} · ${escapeHTML(r.manifest.split)} · ${escapeHTML(r.manifest.run_id)}</option>`).join('');if(eligible.some(r=>r.manifest.run_id===previous))$(id).value=previous;}
  if(!$('before-run').value)$('before-run').value=complete.find(r=>r.manifest.config.name==='baseline'&&r.manifest.split!=='dev')?.manifest.run_id||'';
  if(!$('after-run').value)$('after-run').value=complete.find(r=>r.manifest.config.name==='hybrid'&&r.manifest.split!=='dev')?.manifest.run_id||'';
}
$('refresh-runs').addEventListener('click',()=>loadRuns().catch(fail));
$('run-history').addEventListener('click',async e=>{const b=e.target.closest('[data-run]');if(!b)return;try{const run=await json('/runs/'+encodeURIComponent(b.dataset.run));$('run-detail').innerHTML=`<article class="card"><h2>Question-level trace</h2><p class="fine">${escapeHTML(run.manifest.run_id)} · ${escapeHTML(run.manifest.commit||'unversioned')}</p>${run.predictions.map(r=>`<details class="run-detail-row"><summary>${escapeHTML(r.question)} <span class="badge ${r.error?'warning':''}">${r.error?'ERROR':fmt(r.metrics.evidence_recall)}</span></summary><p class="fine">${escapeHTML(r.category)} / ${escapeHTML(r.split)}</p><p>${escapeHTML(r.error||r.response?.answer||r.response?.reason)}</p><pre>${escapeHTML(JSON.stringify(r.metrics,null,2))}</pre></details>`).join('')}</article>`;$('run-detail').scrollIntoView({behavior:'smooth'});}catch(error){fail(error);}});

async function launch(kind){if(activeJob)return;notice('');const body={kind,config:$('eval-config').value,split:$('eval-split').value,judge:$('eval-judge').checked};const job=await json('/jobs',{method:'POST',body:JSON.stringify(body)});activeJob=job.id;for(const id of ['run-eval','run-experiment','rebuild-index'])$(id).disabled=true;if(kind==='ingest')notice('인덱스를 준비하고 있습니다. 완료되면 문서 수가 갱신됩니다.');pollJob();}
async function pollJob(){try{const job=await json('/jobs/'+activeJob);const p=job.progress;const percent=p?Math.round(p.completed/p.total*100):0;$('job-status').innerHTML=`<span>${job.status==='running'?'실행 중':escapeHTML(job.status)} ${p?`· ${p.completed}/${p.total}`:''}</span><progress max="100" value="${percent}">${percent}%</progress><div class="fine">${escapeHTML(p?.question||'모델과 인덱스를 준비하고 있습니다.')}</div>`;if(job.status==='completed'||job.status==='failed'){activeJob=null;for(const id of ['run-eval','run-experiment','rebuild-index'])$(id).disabled=false;if(job.status==='failed')throw new Error(job.error);notice('작업이 완료되었습니다. 실행 기록에서 결과를 확인하세요.');if(job.request.kind==='ingest')await boot();else await loadRuns();return;}setTimeout(pollJob,2000);}catch(error){activeJob=null;for(const id of ['run-eval','run-experiment','rebuild-index'])$(id).disabled=false;fail(error);}}
$('run-eval').addEventListener('click',()=>launch('eval').catch(fail));$('run-experiment').addEventListener('click',()=>launch('experiment').catch(fail));$('rebuild-index').addEventListener('click',()=>launch('ingest').catch(fail));

$('compare-button').addEventListener('click',async()=>{notice('');if(!$('before-run').value||!$('after-run').value)return notice('비교할 두 실행을 선택하세요.');buttonBusy($('compare-button'),true);try{const r=await json(`/compare?before=${encodeURIComponent($('before-run').value)}&after=${encodeURIComponent($('after-run').value)}&split=test`);const selected=['evidence_recall','all_evidence_found','answer_token_f1','abstention_f1'];$('comparison-output').innerHTML=`<p class="fine">${r.n} paired test questions · ${escapeHTML(r.hypothesis)}</p><div class="legend"><span><i></i>Before</span><span><i class="after"></i>After</span></div><div class="metric-bars">${selected.map(k=>{const m=r.metrics[k];return `<div><div class="metric-label"><b>${labels[k]}</b><span class="${m.delta>=0?'positive':'negative'}">${m.delta==null?'N/A':(m.delta>=0?'+':'')+(m.delta*100).toFixed(1)+' pp'}</span></div><svg class="bar-svg" aria-label="Before ${fmt(m.before)}"><rect height="7" width="${(m.before||0)*100}%"></rect></svg><svg class="bar-svg after" aria-label="After ${fmt(m.after)}"><rect height="7" width="${(m.after||0)*100}%"></rect></svg><span class="fine">${fmt(m.before)} → ${fmt(m.after)}${m.delta_ci95_cluster_bootstrap?` · CI [${m.delta_ci95_cluster_bootstrap.map(v=>(v*100).toFixed(1)).join(', ')}] pp`:''}</span></div>`;}).join('')}</div><div class="table-wrap"><table><thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Delta</th></tr></thead><tbody>${Object.entries(r.metrics).map(([key,m])=>`<tr><td>${escapeHTML(labels[key]||key)}</td><td>${fmt(m.before)}</td><td>${fmt(m.after)}</td><td>${m.delta==null?'N/A':(m.delta*100).toFixed(1)+' pp'}</td></tr>`).join('')}</tbody></table></div><p class="fine">${escapeHTML(r.limitations)}</p>`;
    // Dynamic bar widths use element properties; no untrusted markup is evaluated.
  }catch(error){fail(error);}finally{buttonBusy($('compare-button'),false);}});

$('review-run').addEventListener('change',async()=>{try{if(!$('review-run').value){$('review-form').hidden=true;return;}currentReview=await json('/runs/'+encodeURIComponent($('review-run').value));$('review-question').innerHTML=currentReview.predictions.filter(r=>r.response).map(r=>`<option value="${escapeHTML(r.id)}">${escapeHTML(r.question)}</option>`).join('');renderReview();}catch(error){fail(error);}});
$('review-question').addEventListener('change',renderReview);
async function renderReview(){const id=$('review-question').value;const row=currentReview?.predictions.find(r=>r.id===id),g=gold.find(x=>x.id===id);if(!row||!g){$('review-form').hidden=true;return;}$('review-content').innerHTML=`<h2>${escapeHTML(row.question)}</h2><div class="review-columns"><div><span class="eyebrow">ACCEPTANCE CRITERIA</span><ul>${g.acceptance.map(a=>`<li>${escapeHTML(a)}</li>`).join('')}</ul><p class="fine">${escapeHTML(g.construction)}</p></div><div><span class="eyebrow">CANDIDATE ANSWER</span><p class="review-candidate">${escapeHTML(row.response.answer||row.response.reason)}</p><span class="badge">${escapeHTML(row.response.status)}</span></div></div><div class="review-evidence"><strong>인용된 원문</strong>${row.response.claims.flatMap(c=>c.evidence.map(ev=>`<p><b>${escapeHTML(c.text)}</b><br>“${escapeHTML(ev.quote)}”<br><code>${escapeHTML(ev.chunk_id)}</code></p>`)).join('')||'<p>인용 없음</p>'}</div>`;$('review-form').hidden=false;$('human-confirm').checked=false;$('human-faithful').checked=false;$('human-correctness').value='';$('human-notes').value='';$('calibration-result').textContent='';try{const detail=await json('/gold/'+encodeURIComponent(id));if($('review-question').value!==id)return;const box=document.createElement('div');box.className='review-evidence';box.innerHTML='<strong>Gold 원문 근거</strong>'+detail.evidence.map(ev=>`<p><b>${escapeHTML(ev.title)}</b><br>${escapeHTML(ev.text)}<br><code>${escapeHTML(ev.sentence_id)}</code></p>`).join('');if(!detail.evidence.length)box.innerHTML='<strong>Gold 원문 근거</strong><p>근거 제거 질문입니다. Corpus에 필요한 정보가 없는 조건에서 보류해야 합니다.</p>';$('review-content').append(box);}catch(error){fail(error);}}
$('review-form').addEventListener('submit',async e=>{e.preventDefault();try{const result=await json('/runs/'+encodeURIComponent($('review-run').value)+'/reviews',{method:'POST',body:JSON.stringify({question_id:$('review-question').value,correctness:Number($('human-correctness').value),faithful:$('human-faithful').checked,notes:$('human-notes').value,reviewed_by_human:$('human-confirm').checked})});const row=currentReview.predictions.find(r=>r.id===$('review-question').value);$('calibration-result').textContent=result.status==='pending'?'검토를 저장했습니다. 연결된 Judge 판정이 없어 일치도는 아직 측정하지 않았습니다.':`${result.n} labels · agreement ${fmt(result.exact_agreement)} · κ ${result.cohen_kappa?.toFixed(3)??'N/A'} · Judge ${row.judgment?.correctness??'N/A'}`;}catch(error){fail(error);}});

boot().catch(error=>{$('connection-text').textContent='연결 확인 필요';$('connection-dot').classList.add('offline');fail(error);});
