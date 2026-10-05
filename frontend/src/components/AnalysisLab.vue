<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { api, apiUrl, get, fmt } from '../api'
import { ANALYSIS_VARIABLES, EFFECT_STEPS, DEFAULT_RELATION_FIELDS } from '../analysis-options'
import { savedQuickAnalysis, quickAnalysisMatchesScope, quickArtifactUrl } from '../quick-analysis'
import ConditionScene from './ConditionScene.vue'
const props=defineProps({dataset:Object, filters:Object, scope:String, schema:Object, pending:Boolean, active:{type:Boolean,default:true}})
const emit=defineEmits(['locate-record','restore-quick-scope'])
const error=ref(''),busy=ref(false),result=ref(null),history=ref([]),grade=ref(''),variable=ref('rough_thickness'),bins=ref('30, 38, 42, 50'),errorBar=ref('sd')
const conditionData=ref(null),conditionLoading=ref(false),conditionError=ref(''),conditionSelectedId=ref(null)
const conditionExpanded=ref(false),effectStep=ref(1),relationshipFields=ref([])
let conditionSequence=0,runSequence=0
const enabled=reactive({process_time:true,furnace_time:false,width:false,charge_temp:false,thickness:false,rough_thickness:true,rolling_thickness:false,length:false,weight:false})
const controls=reactive({exit_temp:[1180,1220],process_time:[190,230],furnace_time:[180,220],width:[1100,1500],charge_temp:[100,600],thickness:[210,250],rough_thickness:[30,50],rolling_thickness:[1,11],length:[5000,12000],weight:[10000,30000]})
const availableVariables=computed(()=>ANALYSIS_VARIABLES.filter(k=>props.dataset?.available.includes(k)))
const quickMode=computed(()=>Boolean(props.dataset?.frontend_only))
const stale=computed(()=>result.value&&(quickMode.value?!quickAnalysisMatchesScope(result.value,props.filters):result.value.scope_sha256!==props.scope))
const selectionMismatch=computed(()=>!!result.value&&(result.value.parameters.variable!==variable.value||result.value.parameters.steel_grade!==grade.value))
const primaryRelationship=computed(()=>result.value?.relationships?.rows?.find(row=>row.field===result.value.parameters.variable)||null)
const conclusionText=computed(()=>result.value?.relationships?.explanation?.replace('校正表中其他变量后','同时考虑本次其他变量后')||'')
const visibleWarnings=computed(()=>result.value?.warnings.filter(w=>!w.startsWith('脱敏合成演示数据')&&!w.startsWith('模拟数据包含人为设置的关系')&&!w.startsWith('完全独立模拟示例'))||[])
const signed=value=>value==null?'—':(value>=0?'+':'')+fmt(value,2)
const artifactView=name=>quickMode.value?quickArtifactUrl(result.value,name):apiUrl(result.value?.artifacts[name])
const artifact=name=>{
 const url=artifactView(name)
 if(quickMode.value)return url
 return `${url}${url.includes('?')?'&':'?'}download=true`
}
const isIndependentSimulation=source=>source?.source_kind==='simulated'&&source?.release?.data_origin==='independent_simulation'
const sourceLabel=source=>{
 const kind=typeof source==='string'?source:source?.source_kind
 if(isIndependentSimulation(source))return '完全独立模拟示例'
 return ({real:'真实数据',sanitized:'脱敏合成演示',simulated:'模拟数据'}[kind]||'演示数据')
}
function autoBins(){
 const b=props.dataset?.bounds[variable.value]
 if(!b)return
 const presets={rough_thickness:'30, 38, 42, 50',thickness:'190, 225, 235, 260',rolling_thickness:'1, 2.5, 3.5, 6, 11'}
 bins.value=presets[variable.value]||Array.from({length:5},(_,i)=>Math.round((b.min+(b.max-b.min)*i/4)*100)/100).join(', ')
 effectStep.value=EFFECT_STEPS[variable.value]
 if(b.min<Number(bins.value.split(',')[0])||b.max>Number(bins.value.split(',').at(-1)))
   bins.value=Array.from({length:4},(_,i)=>Math.round((b.min+(b.max-b.min)*i/3)*100)/100).join(', ')
}
async function loadHistory(){
 if(quickMode.value)return
 const id=props.dataset?.id;if(!id)return
 try{const data=await get('/analyses?dataset_id='+id);if(props.dataset?.id===id)history.value=data}catch(e){error.value=e.message}
}
function selectHistory(id){
 const selected=history.value.find(item=>item.id===id)||null
 result.value=selected
 if(!selected)return
 const parameters=selected.parameters
 grade.value=parameters.steel_grade
 variable.value=parameters.variable
 bins.value=parameters.bins.join(', ')
 effectStep.value=parameters.effect_step??EFFECT_STEPS[parameters.variable]
 relationshipFields.value=(parameters.relationship_fields??DEFAULT_RELATION_FIELDS).filter(k=>availableVariables.value.includes(k))
 errorBar.value=parameters.error_bar
 for(const key of Object.keys(controls)){
  enabled[key]=Boolean(parameters.controls?.[key])
  if(parameters.controls?.[key])controls[key]=[...parameters.controls[key]]
 }
}
watch(()=>props.dataset?.id,()=>{
 runSequence++;busy.value=false;history.value=[]
 grade.value=props.filters.grades.length===1?props.filters.grades[0]:props.dataset?.grades[0]?.name||''
 variable.value=availableVariables.value[0]||'rough_thickness';autoBins();result.value=null;error.value=''
 relationshipFields.value=DEFAULT_RELATION_FIELDS.filter(k=>props.dataset?.available.includes(k))
 enabled.process_time=props.dataset?.available.includes('process_time')
 for(const k of Object.keys(controls)){const b=props.dataset?.bounds[k];if(b&&k!=='exit_temp')controls[k]=[b.min,b.max]}
 if(props.dataset?.bounds.process_time){const b=props.dataset.bounds.process_time;controls.process_time=b.min<=230&&b.max>=190?[Math.max(b.min,190),Math.min(b.max,230)]:[b.min,b.max]}
 if(props.dataset?.bounds.exit_temp){const b=props.dataset.bounds.exit_temp;controls.exit_temp=b.min<=1220&&b.max>=1180?[Math.max(b.min,1180),Math.min(b.max,1220)]:[b.min,b.max]}
 if(quickMode.value){
  try{const saved=savedQuickAnalysis();history.value=[saved.result];selectHistory(saved.result.id)}catch(e){error.value=e.message}
  return
 }
 loadHistory()
},{immediate:true})
watch(()=>props.filters.grades.join('|'),()=>{
 if(quickMode.value)return
 const selected=props.filters.grades
 if(selected.length===1||selected.length>1&&!selected.includes(grade.value))grade.value=selected[0]
})
const options=()=>({filters:JSON.parse(JSON.stringify(props.filters)),steel_grade:grade.value,variable:variable.value,
 effect_step:Number(effectStep.value),relationship_fields:availableVariables.value.filter(k=>relationshipFields.value.includes(k)||k===variable.value),
 bins:bins.value.split(/[,，\s]+/).filter(Boolean).map(Number),error_bar:errorBar.value,
 controls:Object.fromEntries(Object.entries(controls).filter(([k])=>k!==variable.value&&props.dataset.available.includes(k)&&(k==='exit_temp'||enabled[k])).map(([k,v])=>[k,v.map(x=>x===''||x==null?null:Number(x))]))})
function canonical(value){
 if(Array.isArray(value))return value.map(canonical)
 if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]))
 return value
}
const stable=value=>JSON.stringify(canonical(value))
const experimentDirty=computed(()=>{
 if(!result.value||!props.dataset)return false
 try{return stable(options())!==stable(result.value.parameters)}catch{return true}
})
watch(()=>result.value?.id,async id=>{
 const seq=++conditionSequence
 conditionExpanded.value=false
 conditionData.value=null;conditionSelectedId.value=null;conditionError.value='';conditionLoading.value=false
 if(!id)return
 if(quickMode.value){conditionData.value=savedQuickAnalysis().conditions;return}
 conditionLoading.value=true
 try{
  const data=await get(`/analyses/${id}/conditions`)
  if(seq===conditionSequence&&result.value?.id===id)conditionData.value=data
 }catch(e){if(seq===conditionSequence)conditionError.value=e.message}
 finally{if(seq===conditionSequence)conditionLoading.value=false}
},{immediate:true})
function locateConditionRecord(id){
 if(stale.value||props.pending||busy.value||conditionLoading.value||!conditionData.value?.points.some(p=>p.record_id===id))return
 emit('locate-record',id)
}
async function run(){
 if(quickMode.value)return
 const id=props.dataset.id,seq=++runSequence;busy.value=true;error.value=''
 try{
  const data=await api(`/datasets/${id}/analyses`,options())
  if(props.dataset.id===id&&seq===runSequence){result.value=data;await loadHistory()}
 }catch(e){if(props.dataset.id===id&&seq===runSequence)error.value=e.message}finally{if(seq===runSequence)busy.value=false}
}
async function rerun(){
 if(quickMode.value){emit('restore-quick-scope');return}
 if(!result.value)return;const datasetId=props.dataset.id,seq=++runSequence;busy.value=true;error.value=''
 try{const data=await api(`/analyses/${result.value.id}/rerun`);if(props.dataset.id===datasetId&&seq===runSequence){result.value=data;await loadHistory()}}catch(e){if(props.dataset.id===datasetId&&seq===runSequence)error.value=e.message}finally{if(seq===runSequence)busy.value=false}
}
</script>
<template>
<div class="analysis-layout">
 <section class="panel experiment-form"><div class="panel-title"><div><h2>变量与温降关系</h2></div></div>
  <fieldset class="experiment-fields" :disabled="quickMode" aria-label="分析参数">
  <label>钢种<select v-model="grade" aria-label="分析钢种"><option v-for="g in dataset.grades" :key="g.name" :value="g.name">{{g.name}}（{{fmt(g.count,0)}}）</option></select></label>
  <label>分析变量<select v-model="variable" @change="autoBins" aria-label="分析变量"><option v-for="v in availableVariables" :key="v" :value="v">{{schema[v]?.label}} / {{schema[v]?.unit}}</option></select></label>
  <label title="左闭右开，最后一组包含右端点。">分组边界 / {{schema[variable]?.unit}}<input v-model="bins" aria-label="分组边界" placeholder="30, 38, 42, 50"></label>
  <label>量化增量 / {{schema[variable]?.unit}}<input v-model="effectStep" type="number" min="0.000001" step="any" aria-label="量化增量"></label>
  <details class="relationship-options"><summary>参与量化的变量</summary><div><label v-for="v in availableVariables.filter(k=>k!=='rolling_thickness'||k===variable)" :key="v"><input type="checkbox" :checked="relationshipFields.includes(v)||variable===v" :disabled="variable===v" @change="relationshipFields=$event.target.checked?[...relationshipFields,v]:relationshipFields.filter(k=>k!==v)">{{schema[v]?.label}}</label></div><p>所选控制变量也会纳入校正。</p></details>
  <div class="control-ranges"><h3>控制工况</h3><div v-for="(bounds,key) in controls" :key="key" v-show="key!==variable&&dataset.available.includes(key)&&(key!=='rolling_thickness'||variable==='rolling_thickness')&&(!quickMode||key==='exit_temp'||enabled[key])" class="control-item"><label v-if="key==='exit_temp'">出炉温度 / °C（必填）</label><label v-else><input type="checkbox" v-model="enabled[key]">{{schema[key]?.label}} / {{schema[key]?.unit}}</label><div v-if="key==='exit_temp'||enabled[key]" class="range-inputs"><input v-model="controls[key][0]" type="number" step="any" :aria-label="`控制${schema[key]?.label}下限`" placeholder="下限"><span>—</span><input v-model="controls[key][1]" type="number" step="any" :aria-label="`控制${schema[key]?.label}上限`" placeholder="上限"></div></div></div>
  <label>误差条<select v-model="errorBar" aria-label="误差条统计量"><option value="sd">样本标准差（ddof=1）</option><option value="ci95">均值的 95% t 置信区间</option></select></label>
  <p v-if="errorBar==='ci95'" class="notice">t 区间假设样本独立；首版未校正连续生产记录的时间相关性。</p>
  </fieldset>
  <p v-if="quickMode" class="preset-note" data-testid="quick-parameters-applied">内置实验已应用。自定义参数请在上方选择完整数据集。</p>
  <p v-if="error" class="notice danger" role="alert">{{error}}</p>
  <button v-if="!quickMode" class="primary wide" @click="run" :disabled="busy||pending||!availableVariables.length">{{busy?'正在计算并生成图组…':'运行分析'}}</button>
  
 </section>
 <div class="analysis-content">
  <section v-if="quickMode" class="panel history-bar preset-bar" data-testid="quick-analysis-state"><strong>默认分析已应用</strong><span>图组与报告随网页提供</span></section>
  <section v-else class="panel history-bar"><label>已保存实验<select @change="selectHistory($event.target.value)" :value="result?.id||''" :disabled="busy" aria-label="分析历史"><option value="">选择一份分析结果</option><option v-for="r in history" :key="r.id" :value="r.id">{{new Date(r.created_at).toLocaleString('zh-CN')}} · {{r.parameters.steel_grade}} · {{schema[r.parameters.variable]?.label}} · n={{r.counts.analyzed}}</option></select></label><span>{{history.length}} 次实验</span></section>
  <section v-if="!result||selectionMismatch" class="panel analysis-empty"><div class="empty-icon">∑</div><h2>{{selectionMismatch?'请运行所选变量的分析':'尚无分析结果'}}</h2><p>{{selectionMismatch?'当前选择与已保存实验不同。点击“运行分析”后，这里显示所选变量的分组与结论。':'设置钢种、控制范围和分组边界，点击“运行分析”。'}}</p></section>
  <template v-else>
   <div v-if="stale" class="notice" role="status" data-testid="analysis-scope-notice"><template v-if="quickMode">当前筛选与内置实验不同。以下结果仍来自默认的 1,000 条数据范围，不随筛选重算。</template><template v-else>当前筛选条件已改变。三维视图与报告保留运行时的数据范围，记录表定位暂不可用；可按保存参数复现，或重新运行当前范围。</template><button v-if="quickMode" type="button" class="text-button" @click="rerun">恢复默认分析范围</button></div>
   <div v-else-if="experimentDirty" class="notice" role="status" data-testid="experiment-draft-notice">实验参数已修改。三维视图与报告仍显示保存结果，运行分析后更新。</div>
   <section class="panel report-panel" :data-analysis-id="result.id"><div class="panel-title report-title"><div><h2>{{schema[result.parameters.variable]?.label}}与粗轧温降</h2></div><div class="report-title-actions"><span class="source-badge" :class="result.source_kind">{{sourceLabel(result)}}</span><button type="button" class="secondary report-scene-toggle" :aria-expanded="conditionExpanded" aria-controls="analysis-condition-region" @click="conditionExpanded=!conditionExpanded"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z M4 7.5l8 4.5 8-4.5 M12 12v9"/></svg>{{conditionExpanded?'收起三维工况':'展开三维工况'}}<svg class="toggle-chevron" :class="{expanded:conditionExpanded}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg></button></div></div>
    <div class="report-counts"><div v-if="result.counts.current_scope!==result.counts.analyzed"><small>{{quickMode?'默认数据范围':'工作台范围'}}</small><strong>{{fmt(result.counts.current_scope,0)}}</strong></div><div v-if="result.counts.controlled!==result.counts.analyzed"><small>控制工况后</small><strong>{{fmt(result.counts.controlled,0)}}</strong></div><div><small>实际分组样本</small><strong data-testid="analysis-n">{{fmt(result.counts.analyzed,0)}}</strong></div></div>
    <div class="condition-tags"><span v-for="c in result.conditions" :key="c">{{c}}</span></div>
    <p v-if="result.counts.missing_analysis_values||result.counts.outside_bins" class="notice">未参与分组：字段缺失 {{fmt(result.counts.missing_analysis_values,0)}} 条，区间外 {{fmt(result.counts.outside_bins,0)}} 条。</p>
    <h3 class="research-figure-heading">分组统计与工况检查</h3>
    <img :src="artifactView('figure.png')" class="analysis-figure" alt="平均温降、组内分布、样本量及控制工况检查的科研图组">
    <p class="figure-caption">{{result.error_bar_label}}</p>
    <div class="table-scroll"><table><thead><tr><th>{{schema[result.parameters.variable]?.label}}区间 / {{schema[result.parameters.variable]?.unit}}</th><th>样本量</th><th>平均温降 / °C</th><th>标准差 / °C</th><th>中位数 / °C</th></tr></thead><tbody><tr v-for="g in result.groups" :key="g.index"><td>{{g.label}}</td><td>{{fmt(g.n,0)}}</td><td>{{fmt(g.mean,2)}}</td><td>{{fmt(g.sd,2)}}</td><td>{{fmt(g.median,2)}}</td></tr></tbody></table></div>
    <details class="difference-details"><summary>组间均值差与实际控制工况</summary><div class="table-scroll"><table><thead><tr><th>分组 A</th><th>分组 B</th><th>B − A / °C</th></tr></thead><tbody><tr v-for="(p,i) in result.differences" :key="i"><td>{{p.a}}</td><td>{{p.b}}</td><td>{{fmt(p.mean_difference_b_minus_a,2)}}</td></tr></tbody></table></div><div class="table-scroll"><table><thead><tr><th>变量分组</th><th>控制指标</th><th>均值</th><th>实际范围</th></tr></thead><tbody><template v-for="g in result.groups" :key="g.index"><tr v-for="(c,k) in g.controls" :key="k"><td>{{g.label}}</td><td>{{schema[k]?.label}} / {{schema[k]?.unit}}</td><td>{{fmt(c.mean,2)}}</td><td>{{fmt(c.min,2)}}—{{fmt(c.max,2)}}</td></tr></template></tbody></table></div></details>
    <p class="result-explanation">{{result.explanation}}</p><p v-for="w in visibleWarnings" :key="w" class="notice">{{w}}</p>
    <div v-if="active&&conditionExpanded" id="analysis-condition-region" role="region" aria-label="三维工况探索"><ConditionScene :data="conditionData" :loading="conditionLoading" :error="conditionError" :selected-id="conditionSelectedId" :locate-disabled="stale||pending||busy" :locate-note="stale?'当前工作台筛选与保存实验范围不一致，请按保存分析范围查看记录。':'正在更新数据或分析结果，请稍后定位记录。'" @select="conditionSelectedId=$event" @locate="locateConditionRecord"/></div>
    <section class="analysis-conclusion" aria-labelledby="analysis-conclusion-title" data-testid="relationship-summary">
     <div class="analysis-conclusion-heading"><h3 id="analysis-conclusion-title">结论</h3><span>{{schema[result.parameters.variable]?.label}}与粗轧温降</span></div>
     <template v-if="result.relationships&&primaryRelationship">
      <p class="analysis-conclusion-main" data-testid="relationship-conclusion">{{conclusionText}}</p>
      <p class="analysis-conclusion-scope"><span v-if="primaryRelationship.ci95_low!=null">校正后 95% 区间 {{fmt(primaryRelationship.ci95_low,2)}}—{{fmt(primaryRelationship.ci95_high,2)}} °C · </span>共同完整样本 {{fmt(result.relationships.n,0)}} 条<span v-if="result.relationships.excluded_missing"> · 字段缺失未纳入 {{fmt(result.relationships.excluded_missing,0)}} 条</span></p>
      <p v-if="result.source_kind!=='real'" class="relationship-source">{{isIndependentSimulation(result)?'完全独立模拟示例：关系数值仅用于展示分析流程，不代表真实生产数据或工业结论。':'合成演示数据：关系数值仅展示分析流程，不代表实际工业结论。'}}</p>
      <p class="relationship-method-note">当前工况内的线性关联，不能直接推断因果。95% HC3 区间未校正生产记录的时间相关性。</p>
      <details class="relationship-diagnostics"><summary>所选变量的适用范围与模型检查</summary><p>观测范围：{{fmt(primaryRelationship.range_min,2)}}—{{fmt(primaryRelationship.range_max,2)}} {{primaryRelationship.unit}} · VIF：{{fmt(primaryRelationship.vif,2)}} · 样本内 R²：{{fmt(result.relationships.r2_in_sample,3)}}。拟合度不是测试集预测性能。</p><p>单变量变化：{{signed(primaryRelationship.unadjusted_change)}} °C；校正后变化：{{signed(primaryRelationship.adjusted_change)}} °C。两者使用同一批共同完整记录。</p><p v-for="w in result.relationships.warnings" :key="w">{{w}}</p><p>{{result.relationships.method}}</p></details>
      <details class="relationship-diagnostics"><summary>查看所选变量的校正关系与残差图</summary><img :src="artifactView('relationship.png')" class="relationship-figure" alt="所选变量与温降校正后的线性关系及残差检查"><p>其他变量取样本均值；阴影为均值拟合的 95% HC3 区间，不是单条记录的预测区间。</p><a :href="artifact('relationship.png')" :download="quickMode?'relationship.png':null">PNG</a> · <a :href="artifact('relationship.svg')" :download="quickMode?'relationship.svg':null">SVG</a> · <a :href="artifact('relationship.pdf')" :download="quickMode?'relationship.pdf':null">PDF</a></details>
     </template>
     <p v-else class="notice">这份历史实验尚无量化结论。点击“按保存参数复现”生成。</p>
    </section>
    <div class="download-bar"><a class="primary" :href="artifact('bundle.zip')" :download="quickMode?'bundle.zip':null">下载完整实验包</a><a class="secondary" :href="artifactView('report.html')" target="_blank">查看报告</a><a v-if="result.relationships" class="secondary" :href="artifact('report.html')" :download="quickMode?'report.html':null">下载全部变量关系分析</a><a v-if="result.relationships" :href="artifact('relationships.csv')" :download="quickMode?'relationships.csv':null">关系表 CSV</a><a :href="artifact('figure.png')" :download="quickMode?'figure.png':null">PNG</a><a :href="artifact('figure.svg')" :download="quickMode?'figure.svg':null">SVG</a><a :href="artifact('figure.pdf')" :download="quickMode?'figure.pdf':null">PDF</a><a :href="artifact('statistics.csv')" :download="quickMode?'statistics.csv':null">统计 CSV</a><button v-if="!quickMode" class="secondary" @click="rerun" :disabled="busy">按保存参数复现</button></div>
    <details class="provenance-details"><summary>分析口径与复现信息</summary><p>分组口径：{{result.interval_policy}}</p><p>{{result.limitation}}</p><p v-for="w in result.warnings.filter(w=>!visibleWarnings.includes(w))" :key="w">{{w}}</p><p>数据集：{{result.dataset_name}}</p><p>数据指纹：{{result.dataset_sha256}}</p><p>参数指纹：{{result.parameter_sha256}}</p><p>样本快照指纹：{{result.samples_sha256}}</p><a :href="artifact('samples.csv')" :download="quickMode?'samples.csv':null">下载本次分析样本</a><a :href="artifact('parameters.json')" :download="quickMode?'parameters.json':null">下载参数</a><a :href="artifact('result.json')" :download="quickMode?'result.json':null">下载完整统计</a></details>
   </section>
  </template>
 </div>
</div>
</template>
