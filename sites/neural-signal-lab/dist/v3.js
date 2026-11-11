'use strict';
const $=s=>document.querySelector(s);
const labels={full_rate:'A · Full rate',prefilter_full_rate:'B · Prefilter control',multirate:'C · Multirate',multirate_notch:'C + 60 Hz notch'};
const pct=(n,d=3)=>(100*n).toFixed(d)+'%';
const number=(n,d=0)=>Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const ns='http://www.w3.org/2000/svg';
let data,current,index=0,plotState;
function resetSelection(){
 const values=['2000','2','multirate','1','clean','aligned'];
 ['adc-rate','modulation','architecture','seed','content','alignment'].forEach((key,i)=>$('#'+key).value=values[i]);
 index=0;render();
}
function svgNode(tag,attrs={},text=''){const e=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text)e.textContent=text;return e;}
function inspect(i){
 if(!plotState)return;
 const p=plotState;index=Math.max(0,Math.min(p.t.length-1,i));
 for(const plot of p.panels){const x=plot.x(p.t[index]);plot.cross.setAttribute('x1',x);plot.cross.setAttribute('x2',x);plot.dot.setAttribute('cx',x);plot.dot.setAttribute('cy',plot.y(plot.values[index]));}
 const difference=p.selected[index]-p.reference[index];
 $('#plot-readout').textContent=`t = ${p.t[index].toFixed(2)} s · Selected ${p.selected[index].toFixed(6)} · Reference ${p.reference[index].toFixed(6)} · Difference ${difference.toExponential(3)} FS²`;
}
function drawPanel(el,t,series,difference=false){
 const W=Math.max(260,el.clientWidth),H=el.clientHeight;
 const pad={l:difference?74:59,r:18,t:27,b:40},w=W-pad.l-pad.r,h=H-pad.t-pad.b;
 const values=series.flatMap(s=>s.values);const low=Math.min(...values),high=Math.max(...values);
 const peak=Math.max(Math.abs(low),Math.abs(high),1e-12),range=Math.max(high-low,1e-10);
 const ymin=difference?-1.15*peak:low-.1*range,ymax=difference?1.15*peak:high+.1*range;
 const x=v=>pad.l+(v-6)*w,y=v=>pad.t+(ymax-v)/(ymax-ymin)*h;
 const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':difference?'Selected minus full-rate power, separate symmetric FS² scale':'Recorded selected and full-rate power feature overlay'});
 for(let i=0;i<=4;i++){
  const v=ymin+(ymax-ymin)*i/4;
  svg.append(svgNode('line',{x1:pad.l,x2:W-pad.r,y1:y(v),y2:y(v),class:'grid-line'}));
  svg.append(svgNode('text',{x:pad.l-8,y:y(v)+4,'text-anchor':'end'},difference?(Math.abs(v)<peak*1e-9?'0':v.toExponential(1)):v.toFixed(3)));
  const tick=6+i/4;svg.append(svgNode('text',{x:x(tick),y:H-20,'text-anchor':'middle'},tick.toFixed(2)));
 }
 svg.append(svgNode('text',{x:pad.l,y:13,class:'axis'},difference?'Difference · FS²':'Mean-square · FS²'));
 svg.append(svgNode('text',{x:W-pad.r,y:H-3,class:'axis','text-anchor':'end'},'Original timestamp · s'));
 if(difference)svg.append(svgNode('line',{x1:pad.l,x2:W-pad.r,y1:y(0),y2:y(0),stroke:'#8c959f','stroke-width':1}));
 for(const item of series){const d=item.values.map((v,i)=>(i?'L':'M')+x(t[i]).toFixed(2)+' '+y(v).toFixed(2)).join(' ');svg.append(svgNode('path',{d,class:'plot-line',stroke:item.color,'stroke-dasharray':item.dash||''}));}
 const cross=svgNode('line',{class:'cross',x1:0,x2:0,y1:pad.t,y2:H-pad.b});
 const dot=svgNode('circle',{class:'dot',r:3,cx:0,cy:0});svg.append(cross,dot);el.replaceChildren(svg);
 svg.addEventListener('pointermove',event=>{const r=svg.getBoundingClientRect();const at=6+((event.clientX-r.left)*W/r.width-pad.l)/w;inspect(Math.round((at-6)*100));});
 return {x,y,cross,dot,values:series[0].values};
}
function draw(){
 if(!current)return;
 const p=current.plot,clean=$('#content').value==='clean',aligned=$('#alignment').value==='aligned';
 const selected=p[clean?'clean':'noisy'],reference=p[(aligned?'aligned_':'')+'full_'+(clean?'clean':'noisy')];
 const a=drawPanel($('#feature-chart'),p.t,[{values:selected,color:'#315e85'},{values:reference,color:'#99603e',dash:'5 4'}]);
 const b=drawPanel($('#difference-chart'),p.t,[{values:selected.map((v,i)=>v-reference[i]),color:'#315e85'}],true);
 plotState={t:p.t,selected,reference,panels:[a,b]};inspect(index);
}
function render(){
 const fs=Number($('#adc-rate').value),fm=Number($('#modulation').value),seed=Number($('#seed').value);
 const notch=$('#architecture option[value="multirate_notch"]');notch.disabled=fs!==2000;
 if(fs!==2000&&$('#architecture').value==='multirate_notch')$('#architecture').value='multirate';
 const arch=$('#architecture').value,name=`${fs}_${arch}`;
 current=data.records.find(c=>c.fs===fs&&c.fm===fm&&c.seed===seed&&c.name===name);
 if(!current)throw new Error('Recorded case is unavailable');
 const r=current.trial,clean=$('#content').value==='clean',aligned=$('#alignment').value==='aligned';
 const metric=clean?(aligned?'clean_paired_aligned_nrmse':'clean_paired_unaligned_nrmse'):(aligned?'paired_aligned_nrmse':'paired_unaligned_nrmse');
 const base=data.records.find(c=>c.fs===fs&&c.fm===fm&&c.seed===seed&&c.name===`${fs}_full_rate`).trial;
 const change=100*(r.multiplications_per_s/base.multiplications_per_s-1);
 $('#record-label').textContent=`${labels[arch]} · ADC ${number(fs)} Hz → processing ${number(data.filters.digital[name].processing_fs)} Hz → features 100 Hz · fₘ ${fm} Hz · seed ${seed}`;
 $('#alignment-note').textContent=aligned?
  `For this view, I shift only the reference by the independently calibrated relative delay (${((r.calibrated_delay_s-base.calibrated_delay_s)*1000).toFixed(2)} ms). The selected output keeps its original timestamps. This is an offline comparison; the modeled signal delay remains.`:
  'Here I’m comparing the original common-clock timestamps. The difference includes delay, filter response, and, on the ADC path, passed disturbances.';
 $('#metrics').innerHTML=[
  [`${clean?'Clean':'Noisy'} paired NRMSE`,pct(r[metric]),aligned?'Fixed calibration alignment':'Original timestamps'],
  ['Clean mean bias',(r.clean_mean_bias_fraction>0?'+':'')+pct(r.clean_mean_bias_fraction),'Against analytic mean power'],
  ['Calibrated signal delay',(1000*r.calibrated_delay_s).toFixed(2)+' ms',`Phase delay at ${fm} Hz modulation`],
  ['Multiplications / second',number(r.multiplications_per_s),`${change.toFixed(1)}% versus full rate · not cycles`]
 ].map(([title,value,sub])=>`<div><span>${title}</span><b>${value}</b><small>${sub}</small></div>`).join('');
 $('#metric-scope').textContent=`Full-record metrics, ${number(r.valid_features)} valid features. Aligned clean analytic-oracle NRMSE: ${pct(r.clean_oracle_aligned_nrmse)}. Combined contamination/quantization NRMSE: ${pct(r.contamination_and_quantization_nrmse)}. I don’t refit delay or gain for each seed.`;
 const c=data.filters.digital[name],onset=data.calibration.onset[name];
 const collection=1000*(fs/125-1)/fs;
 $('#delay-breakdown').innerHTML=`
 <div><h4>Linear-phase FIR contributions</h4><dl><div><dt>Acquisition FIR</dt><dd>${(1000*c.acquisition_delay_s).toFixed(2)} ms</dd></div><div><dt>Smoothing FIR</dt><dd>${(1000*c.feature_delay_s).toFixed(2)} ms</dd></div></dl><p>Known filter delays; no CPU work is timed.</p></div>
 <div><h4>Measured chain response</h4><b>${(1000*r.calibrated_delay_s).toFixed(2)} ms</b><p>Small-modulation phase delay at ${fm} Hz, including analog and frequency-dependent IIR behavior.</p><p>T10 / T50 / T90: ${[onset.T10_s,onset.T50_s,onset.T90_s].map(t=>(t*1000).toFixed(0)).join(' / ')} ms, a separate onset test at 100 Hz output.</p></div>
 <div><h4>Delivery and compute</h4><b>≤ ${collection.toFixed(2)} ms</b><p>Input block collection wait (${fs/125} samples). CPU, transport, and scheduling remain unmeasured.</p></div>`;
 $('#realization').textContent=`Selected implementation: ${c.acquisition.length===1?'identity acquisition':c.acquisition.length+'-tap acquisition FIR'}; ${c.bandpass.length} bandpass SOS at ${number(c.processing_fs)} Hz; ${c.feature.length}-tap smoothing FIR; notch ${c.notch.length?'60 Hz, Q=25':'off'}. Startup exclusion ${c.warmup} s. I keep these delay quantities separate; I haven’t measured end-to-end target latency.`;
 draw();
}
function renderSummary(){
 const rows=[];
 for(const fs of [2000,4000])for(const fm of [2,5]){
  const s=data.summary[`${fs}_multirate`][String(fm)];
  const find=arch=>data.records.find(r=>r.fs===fs&&r.fm===fm&&r.seed===1&&r.name===`${fs}_${arch}`).trial;
  rows.push(`<tr><td>${fs/1000} kHz</td><td>${fm} Hz</td><td>${pct(s.clean_paired_aligned_nrmse.max)}</td><td>${pct(s.paired_aligned_nrmse.mean)} / ${pct(s.paired_aligned_nrmse.max)}</td><td>${(1000*s.calibrated_delay_s.mean).toFixed(2)} ms</td><td>${number(find('full_rate').multiplications_per_s)} → ${number(find('multirate').multiplications_per_s)}</td></tr>`);
 }
 $('#summary-rows').innerHTML=rows.join('');
 $('#headline-error').textContent=pct(data.headline.clean_max);
 const max=data.audit_maxima;
 $('#audit-result').textContent=`I checked alignment across all 400 saved noisy comparisons. The maximum held-out reconstruction NRMSE is ${pct(max.held_out_half_rate_nrmse,6)}; changing the alignment method changes paired NRMSE by at most ${(100*max.paired_nrmse_change).toFixed(8)} percentage points. That gives me a sensitivity check for these recorded cases.`;
 const minimum=Math.min(...data.targeted.digital_decimator_aliasing.cases.map(r=>r.measured_rejection_db));
 $('#alias-result').textContent=`I also tested digital tones that fold into 110 Hz. The acquisition FIR rejects them by ≥${minimum.toFixed(2)} dB, matching its predicted response. I tested ADC folding separately. These are selected cases, not a worst-case broadband bound.`;
 const nominal=data.records.filter(c=>!c.name.includes('notch')).map(c=>c.trial);
 const checks=[['Clean mean bias ≤10%',nominal.every(r=>Math.abs(r.clean_mean_bias_fraction)<=.1)],['Multirate clean paired NRMSE ≤2%',nominal.filter(r=>r.name.endsWith('multirate')).every(r=>r.clean_paired_aligned_nrmse<=.02)],['Small-modulation delay ≤200 ms',nominal.every(r=>r.calibrated_delay_s<=.2)],['No nominal ADC clipping',nominal.every(r=>r.adc_clips===0)]];
 $('#screens').textContent=checks.map(([label,passed])=>`${passed?'PASS':'FAIL'}: ${label}`).join('\n');
}
[$('#feature-chart'),$('#difference-chart')].forEach(el=>el.addEventListener('keydown',e=>{if(!plotState)return;const keys={ArrowLeft:index-1,ArrowRight:index+1,Home:0,End:plotState.t.length-1};if(e.key in keys){e.preventDefault();inspect(keys[e.key]);}}));
fetch('data/pipeline-v3.json').then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}).then(payload=>{
 if(payload.schema!==3||payload.records.length!==400)throw new Error('Unexpected experiment dataset');
 data=payload;
 for(let i=1;i<=20;i++){const o=document.createElement('option');o.value=String(i);o.textContent=String(i);$('#seed').append(o);}
 document.querySelectorAll('.experiment select,.experiment button').forEach(el=>el.disabled=false);
 document.querySelectorAll('.experiment select').forEach(el=>el.addEventListener('change',()=>{index=0;render();}));
 $('#reset').addEventListener('click',resetSelection);
 renderSummary();render();$('#experiment').setAttribute('aria-busy','false');
 const resize=new ResizeObserver(()=>draw());resize.observe($('#feature-chart'));resize.observe($('#difference-chart'));
}).catch(error=>{$('#load-error').hidden=false;$('#record-label').textContent='Recorded data unavailable; see the methods and limits.';console.error(error);});
