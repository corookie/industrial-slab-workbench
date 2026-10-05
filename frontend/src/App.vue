<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Chart from './components/Chart.vue'
import SlabScene from './components/SlabScene.vue'
import ImportModal from './components/ImportModal.vue'
import AnalysisLab from './components/AnalysisLab.vue'
import ProcessOverview from './components/ProcessOverview.vue'
import { api, get, fmt, htmlEscape, downloadScope } from './api'
import { quickSchema, quickDataset, quickQuery, quickRecord, downloadQuickScope } from './quick-demo'

const datasets=ref([quickDataset]),dataset=ref(quickDataset),schema=ref(quickSchema),q=ref(null),selected=ref(null),view=ref('process'),uploadOpen=ref(false),loading=ref(false),error=ref(''),selecting=ref(false)
const connecting=ref(true),connectionError=ref('')
let initializationSequence=0
const publicMode=ref(true)
function navigate(target){view.value=target;window.scrollTo({top:0,behavior:'instant'})}
const isIndependentSimulation=source=>source?.source_kind==='simulated'&&source?.release?.data_origin==='independent_simulation'
const sourceLabel=source=>{
 const kind=typeof source==='string'?source:source?.source_kind
 if(isIndependentSimulation(source))return '完全独立模拟示例'
 return ({real:'真实生产数据',sanitized:'脱敏合成演示',simulated:'模拟示例'}[kind]||'演示数据')
}
const datasetOptionName=source=>`${source.frontend_only?'内置模拟示例':isIndependentSimulation(source)?'完整模拟示例':source.name} · ${fmt(source.rows,0)} 条`
const xField=ref('rough_thickness'),histField=ref('temp_drop'),page=ref(1)
const advancedOpen=ref(false),threeOpen=ref(false),jumpPage=ref('1'),pageError=ref('')
const draft=reactive({grade:'',date_start:'',date_end:'',exclude_invalid:true,ranges:{}})
const activeFilters=ref({grades:[],ranges:{},date_start:null,date_end:null,exclude_invalid:true})
let querySequence=0,selectionSequence=0
const fields=['rough_thickness','width','exit_temp','temp_drop','process_time','furnace_time','length','thickness','rolling_thickness','charge_temp']
const visibleFields=computed(()=>fields.filter(k=>dataset.value?.available.includes(k)))
const basicFields=computed(()=>['rough_thickness','exit_temp','process_time'].filter(k=>visibleFields.value.includes(k)))
const advancedFields=computed(()=>visibleFields.value.filter(k=>!basicFields.value.includes(k)))
const relationFields=computed(()=>['rough_thickness','thickness','rolling_thickness','exit_temp','process_time'].filter(k=>dataset.value?.available.includes(k)))
const histFields=computed(()=>['temp_drop','rough_thickness','thickness','rolling_thickness','exit_temp'].filter(k=>dataset.value?.available.includes(k)))
const filtersFromDraft=()=>({grades:draft.grade?[draft.grade]:[],ranges:Object.fromEntries(Object.entries(draft.ranges).filter(([,r])=>r.some(v=>v!==''&&v!=null)).map(([k,r])=>[k,r.map(v=>v===''||v==null?null:Number(v))])),date_start:draft.date_start||null,date_end:draft.date_end||null,exclude_invalid:draft.exclude_invalid})
const dirty=computed(()=>JSON.stringify(filtersFromDraft())!==JSON.stringify(activeFilters.value))
const scopeTags=computed(()=>{
 const f=activeFilters.value,t=[]
 if(f.grades.length)t.push('钢种 '+f.grades.join(', '))
 for(const [k,r] of Object.entries(f.ranges))t.push(`${schema.value[k]?.label} ${r[0]??'不限'}—${r[1]??'不限'} ${schema.value[k]?.unit}`)
 if(f.date_start||f.date_end)t.push(`${f.date_start||'不限'} 至 ${f.date_end||'不限'}`)
 if(t.length||!f.exclude_invalid||dirty.value)t.push(f.exclude_invalid?'排除异常记录':'包含异常记录')
 return t
})
function resetDraft(){
 draft.grade='';draft.date_start='';draft.date_end='';draft.exclude_invalid=true
 draft.ranges=Object.fromEntries(fields.map(k=>[k,['','']]))
}
async function loadQuery(locate=false,id=selected.value?.record_id,filters=activeFilters.value){
 if(!dataset.value)return
 const seq=++querySequence, dsid=dataset.value.id;selectionSequence++;selecting.value=false;loading.value=true;error.value=''
 try{
  const request={filters,page:page.value,page_size:30,x_field:xField.value,selected_id:id||null,locate_selected:locate}
  const result=dataset.value.frontend_only?quickQuery(request):await api(`/datasets/${dsid}/query`,request)
  if(seq!==querySequence||dsid!==dataset.value?.id)return
  q.value=result;activeFilters.value=result.filters;selected.value=result.selected;page.value=result.page;jumpPage.value=String(result.page);pageError.value=''
 }catch(e){if(seq===querySequence){error.value=e.message;if(q.value?.dataset_id===dsid){page.value=q.value.page;jumpPage.value=String(q.value.page)}}}finally{if(seq===querySequence)loading.value=false}
}
async function selectDataset(id){
 const found=datasets.value.find(x=>x.id===id)
 if(!found)return
 dataset.value=found;q.value=null;selected.value=null;page.value=1;threeOpen.value=false;pageError.value='';resetDraft();activeFilters.value=filtersFromDraft()
 xField.value=relationFields.value[0]||'rough_thickness';histField.value=histFields.value[0]||'temp_drop'
 await loadQuery()
}
async function apply(){page.value=1;await loadQuery(false,selected.value?.record_id,filtersFromDraft())}
async function clearFilters(){resetDraft();await apply()}
async function choose(id,fromScatter=false){
 if(loading.value||!q.value)return
 if(fromScatter){await loadQuery(true,id);return}
 const seq=++selectionSequence,dsid=dataset.value.id,scope=q.value.scope;selecting.value=true
 try{
  const record=dataset.value.frontend_only?quickRecord(id,activeFilters.value):await api(`/datasets/${dsid}/records/${encodeURIComponent(id)}`,activeFilters.value)
  if(seq===selectionSequence&&scope===q.value?.scope&&dsid===dataset.value?.id)selected.value=record
 }catch(e){error.value=e.message}finally{if(seq===selectionSequence)selecting.value=false}
}
async function locateAnalysisRecord(id){
 await choose(id,true)
 if(selected.value?.record_id===id){view.value='workbench';threeOpen.value=false}
}
async function demo(){
 loading.value=true
 try{const meta=await api('/datasets/demo');datasets.value=[quickDataset,...await get('/datasets')];await selectDataset(meta.id)}catch(e){error.value=e.message;loading.value=false}
}
async function imported(meta){uploadOpen.value=false;view.value='workbench';datasets.value=[quickDataset,...await get('/datasets')];await selectDataset(meta.id)}
async function exportRows(){try{if(dataset.value.frontend_only)downloadQuickScope(activeFilters.value);else await downloadScope(dataset.value.id,activeFilters.value)}catch(e){error.value=e.message}}
async function initialize(){
 const sequence=++initializationSequence
 connecting.value=true;connectionError.value=''
 try{
  let result
  for(let attempt=0;attempt<3;attempt++){
   try{
    result=await Promise.all(['/schema','/datasets','/health'].map(path=>get(path,{timeoutMs:90000})))
    break
   }catch(e){
    if(attempt===2||!(e.retryable||[502,503,504].includes(e.status)))throw e
    await new Promise(resolve=>setTimeout(resolve,1500*(attempt+1)))
   }
  }
  if(sequence!==initializationSequence)return
  schema.value=result[0];publicMode.value=result[2].mode==='public_demo'
  let remote=result[1]
  if(!remote.length)remote=[await api('/datasets/demo')]
  if(sequence!==initializationSequence)return
  // Readiness updates the choices only. The currently viewed dataset never changes.
  datasets.value=[quickDataset,...remote]
 }catch(e){if(sequence===initializationSequence)connectionError.value=e.message}
 finally{if(sequence===initializationSequence)connecting.value=false}
}
resetDraft();activeFilters.value=filtersFromDraft()
q.value=quickQuery();selected.value=q.value.selected
onMounted(initialize)

const axis={axisLine:{lineStyle:{color:'#cdd3c1'}},axisLabel:{color:'#707a62',fontSize:12},splitLine:{lineStyle:{color:'#edf0e5'}}}
const base={animation:false,textStyle:{fontFamily:'system-ui',color:'#4b593d'},tooltip:{confine:true},grid:{left:50,right:16,top:35,bottom:46}}
const gradeChart=computed(()=>{
 const all=q.value?.grades||[],visible=all.slice(0,10).map(x=>({...x}))
 if(all.length>10)visible.push({name:'其他钢种',value:all.slice(10).reduce((n,x)=>n+x.value,0)})
 return {...base,grid:{left:16,right:36,top:8,bottom:27,containLabel:true},tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},xAxis:{...axis,type:'value',splitNumber:3},yAxis:{...axis,type:'category',inverse:true,data:visible.map(g=>g.name),axisLabel:{color:'#4b593d',fontSize:12},axisTick:{show:false},axisLine:{show:false}},series:[{type:'bar',data:visible.map(g=>({name:g.name,value:g.value})),barMaxWidth:22,itemStyle:{color:'#708f46',borderRadius:[0,3,3,0]},label:{show:true,position:'right',fontSize:11,color:'#707a62'}}]}
})
const distribution=computed(()=>{
 const h=q.value?.histograms[histField.value],labels=h?h.counts.map((_,i)=>`${h.edges[i].toFixed(1)}–${h.edges[i+1].toFixed(1)}`):[]
 return {...base,grid:{left:12,right:12,top:34,bottom:20,containLabel:true},tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},xAxis:{...axis,type:'category',data:labels,axisLabel:{fontSize:11,rotate:25,color:'#707a62',interval:Math.max(0,Math.ceil(labels.length/3)-1)}},yAxis:{...axis,type:'value',name:'记录数',splitNumber:4},series:[{type:'bar',data:h?.counts||[],barCategoryGap:'8%',itemStyle:{color:'#f48055'}}]}
})
const scatterChart=computed(()=>({
 ...base,grid:{left:16,right:20,top:36,bottom:68,containLabel:true},
 tooltip:{confine:true,formatter:p=>{const v=p.data.value;return `${htmlEscape(v[3])}<br>${htmlEscape(schema.value[xField.value]?.label)}：${fmt(v[0],3)} ${schema.value[xField.value]?.unit}<br>粗轧温降：${fmt(v[1],2)} °C<br>记录：${htmlEscape(v[2])}`}},
 xAxis:{...axis,type:'value',name:`${schema.value[xField.value]?.label||'厚度'} / ${schema.value[xField.value]?.unit||'mm'}`,nameLocation:'middle',nameGap:31,scale:true,splitNumber:3},
 yAxis:{...axis,type:'value',name:'粗轧温降 / °C',scale:true,splitNumber:4},
 dataZoom:[{type:'inside',xAxisIndex:0},{type:'slider',xAxisIndex:0,height:15,bottom:8,showDetail:false,borderColor:'#d7dec9',fillerColor:'rgba(112,143,70,.18)',dataBackground:{lineStyle:{color:'#9cad7f'},areaStyle:{color:'#e0e8d0'}},selectedDataBackground:{lineStyle:{color:'#708f46'},areaStyle:{color:'#cfdeb7'}},moveHandleStyle:{color:'#a9bd8a'}}],
 series:[{type:'scatter',symbolSize:5,large:false,data:(q.value?.scatter||[]).map(v=>({value:v,itemStyle:{color:v[2]===selected.value?.record_id?'#e54b23':'#708f46',opacity:v[2]===selected.value?.record_id?1:.55},symbolSize:v[2]===selected.value?.record_id?11:5}))}]
}))
function pickGrade(e){if(e.data?.name&&e.data.name!=='其他钢种'){draft.grade=e.data.name;apply()}}
const pageCount=computed(()=>Math.max(1,Math.ceil((q.value?.total||0)/30)))
watch(page,value=>{jumpPage.value=String(value)})
async function goPage(target){
 if(loading.value||!q.value?.total)return
 if(!Number.isInteger(target)||target<1||target>pageCount.value){pageError.value=`请输入 1—${pageCount.value} 之间的整数页码`;return}
 page.value=target;pageError.value='';await loadQuery()
}
async function jump(){await goPage(/^\d+$/.test(jumpPage.value.trim())?Number(jumpPage.value):NaN)}
const selectedLabel=computed(()=>selected.value?.slab_id||`记录 ${selected.value?.source_row??'—'}`)
</script>

<template>
<div class="app-shell">
 <header class="topbar"><div class="brand"><div class="brand-mark"><i></i><i></i><i></i></div><div><strong>SLAB LAB</strong><span>工业工艺分析工作台</span></div></div><nav aria-label="主导航"><button :class="{active:view==='process'}" :aria-current="view==='process'?'page':undefined" @click="navigate('process')">工艺概览</button><button :class="{active:view==='workbench'}" :aria-current="view==='workbench'?'page':undefined" @click="navigate('workbench')">数据工作台</button><button :class="{active:view==='analysis'}" :aria-current="view==='analysis'?'page':undefined" @click="navigate('analysis')">分析实验</button></nav><div v-if="!publicMode" class="top-actions"><button class="primary" @click="uploadOpen=true">导入数据</button></div></header>
 <div v-if="error&&q" class="global-error" role="alert">{{error}}<button @click="error=''" aria-label="关闭错误信息">×</button></div>
 <main class="main-area workspace-page" :aria-busy="loading">
  <ProcessOverview v-if="view==='process'" @workbench="navigate('workbench')" @analysis="navigate('analysis')"/>
  <div v-show="view!=='process'">
  <div class="workspace-heading"><div><h1>{{view==='workbench'?'粗轧温降分析':'相近工况下的温降比较'}}</h1></div><span v-if="loading&&q" class="loading-label">正在更新数据…</span></div>
  <section v-if="dataset" class="source-strip" aria-label="数据来源">
   <label class="dataset-select">当前数据集<select :value="dataset?.id" @change="selectDataset($event.target.value)" aria-label="当前数据集"><option v-for="d in datasets" :key="d.id" :value="d.id">{{datasetOptionName(d)}}</option></select></label>
   <div class="dataset-meta"><span class="source-badge" :class="dataset?.source_kind">{{sourceLabel(dataset)}}</span><span>{{fmt(dataset?.rows,0)}} 条源记录</span></div>
   <div v-if="dataset?.frontend_only" class="service-status" role="status" aria-live="polite" data-testid="quick-demo-status"><span v-if="connecting">完整数据连接中…</span><template v-else-if="connectionError"><span>完整数据暂未连接</span><button type="button" class="text-button" @click="initialize">重新连接</button></template><span v-else>完整数据已就绪，可在下拉框选择。</span></div>
   <div class="source-actions"><button v-if="!publicMode" class="text-button" @click="demo" :disabled="loading">模拟示例</button><details v-if="dataset" class="quality-summary"><summary>数据质量与字段</summary><div class="quality-popover"><p v-if="dataset.source_kind==='real'" data-testid="real-data-notice">真实生产数据，仅供本地分析。{{dataset.selection?.kind==='top_five_original'?'仅保留数量最多的五个钢种，数值与生产时间未修改。':'数值与来源保留原样。'}}</p><p v-if="isIndependentSimulation(dataset)">完全独立模拟示例：该数据集由独立设定的模拟参数生成，未从生产数据、钢种编码、记录编号、生产时间或统计特征重建。</p><p v-else-if="dataset.source_kind==='sanitized'">G01—G05 为匿名钢种，编号、日期、样本量及数值已重建；下载内容同为合成数据。</p><p>异常记录 {{fmt(dataset.quality.invalid_rows,0)}} 条，原值保留。</p><p v-if="!dataset.available.includes('slab_id')">未提供板坯编号，使用原始行号和稳定记录标识。</p><p v-if="dataset.quality.duplicate_slab_ids">重复板坯编号 {{dataset.quality.duplicate_slab_ids}} 条，按记录分别保留。</p><p v-for="w in dataset.warnings" :key="w">{{w}}</p><div v-for="(n,k) in dataset.quality.missing" :key="k" class="quality-field"><span>{{schema[k]?.label}}</span><span>{{n===dataset.rows?'未提供':`缺失 ${n}`}}</span></div><p v-for="(p,i) in dataset.provenance" :key="i">{{p.file}} · {{p.sheet}} · {{p.rows}} 行 · {{p.role}}</p><pre v-if="dataset.joins.length">{{JSON.stringify(dataset.joins,null,2)}}</pre></div></details></div>
  </section>
  <div v-if="dataset?.source_kind==='simulated'" class="notice simulated-note">{{isIndependentSimulation(dataset)?'当前为完全独立模拟示例，未使用任何真实生产数据或其统计特征；分析结果仅用于演示系统能力。':'当前为模拟数据，分析结果不代表真实工业结论。'}}</div>
  <div v-if="dataset?.source_kind==='sanitized'" class="notice sanitized-note" data-testid="privacy-notice">合成演示数据，不代表真实生产记录或工业结论。</div>
  
  <form v-if="dataset&&!(dataset.frontend_only&&view==='analysis')" @submit.prevent="apply" class="top-filter-panel" aria-label="顶部样本筛选">
   <div class="filter-panel-heading"><div><h2>样本筛选</h2></div><button type="button" class="secondary" @click="advancedOpen=!advancedOpen" :aria-expanded="advancedOpen" aria-controls="advanced-filters">{{advancedOpen?'收起高级筛选':'高级筛选'}}</button></div>
   <div class="basic-filter-grid"><label>钢种<select v-model="draft.grade" aria-label="筛选钢种"><option value="">全部钢种</option><option v-for="g in dataset.grades" :key="g.name" :value="g.name">{{g.name}}（{{fmt(g.count,0)}}）</option></select></label><div v-for="key in basicFields" :key="key" class="filter-range"><label>{{schema[key]?.label}} / {{schema[key]?.unit}}</label><div class="range-inputs"><input v-model="draft.ranges[key][0]" type="number" step="any" :aria-label="`筛选${schema[key]?.label}下限`" placeholder="下限"><span>—</span><input v-model="draft.ranges[key][1]" type="number" step="any" :aria-label="`筛选${schema[key]?.label}上限`" placeholder="上限"></div></div></div>
   <div v-show="advancedOpen" id="advanced-filters" class="advanced-filter-grid"><div v-for="key in advancedFields" :key="key" class="filter-range"><label>{{schema[key]?.label}} / {{schema[key]?.unit}}</label><div class="range-inputs"><input v-model="draft.ranges[key][0]" type="number" step="any" :aria-label="`筛选${schema[key]?.label}下限`" placeholder="下限"><span>—</span><input v-model="draft.ranges[key][1]" type="number" step="any" :aria-label="`筛选${schema[key]?.label}上限`" placeholder="上限"></div></div><div v-if="dataset.available.includes('produced_at')" class="date-filter"><label>生产时间</label><div class="range-inputs"><input type="date" v-model="draft.date_start" aria-label="生产起始日期"><span>—</span><input type="date" v-model="draft.date_end" aria-label="生产结束日期"></div></div></div>
   <div class="filter-panel-footer"><label class="checkbox-label"><input type="checkbox" v-model="draft.exclude_invalid">排除异常记录</label><span v-if="dirty" class="draft-note">条件已修改，应用后更新结果。</span><div class="filter-buttons"><button type="button" class="secondary" @click="clearFilters" :disabled="loading">重置筛选</button><button type="submit" class="primary" :disabled="loading">{{loading?'正在更新…':'应用筛选'}}</button></div></div>
  </form>
  <div v-if="scopeTags.length&&!(dataset?.frontend_only&&view==='analysis')" class="condition-tags applied-conditions"><span class="condition-label">已应用</span><span v-for="tag in scopeTags" :key="tag">{{tag}}</span></div>
  <template v-if="dataset&&q">
   <div v-show="view==='workbench'">
    <section class="workbench-section overview-section" aria-labelledby="overview-title"><div class="section-heading"><h2 id="overview-title">样本概览</h2></div>
    <div class="kpi-grid" :class="{'has-missing':q.histograms.temp_drop?.missing_n>0}"><div class="kpi"><span>筛选后样本</span><strong data-testid="sample-count">{{fmt(q.total,0)}}</strong></div><div class="kpi"><span>当前钢种</span><strong>{{q.grades.length}}</strong></div><div v-if="q.histograms.temp_drop?.missing_n>0" class="kpi"><span>温降缺失</span><strong class="warm">{{fmt(q.histograms.temp_drop.missing_n,0)}}</strong></div><div class="kpi"><span>源数据异常记录</span><strong class="warm">{{fmt(q.invalid_in_dataset,0)}}</strong><small v-if="!activeFilters.exclude_invalid">当前范围 {{q.invalid_in_scope}} 条</small></div></div>
    </section>
    <section class="workbench-section charts-section" aria-labelledby="charts-title"><div class="section-heading"><h2 id="charts-title">统计视图</h2></div>
    <div class="charts-row overview-charts">
     <section class="panel mini-chart"><div class="panel-title"><h2 title="点击钢种可筛选">钢种数量分布</h2></div><Chart :option="gradeChart" label="钢种数量分布" @pick="pickGrade"/></section>
     <section class="panel mini-chart"><div class="panel-title"><h2>数值分布</h2><select v-model="histField" aria-label="分布指标"><option v-for="f in histFields" :key="f" :value="f">{{schema[f]?.label}} / {{schema[f]?.unit}}</option></select></div><Chart :option="distribution" :label="schema[histField]?.label+'数值分布'"/><p v-if="q.histograms[histField]?.missing_n>0" class="chart-note">缺失 {{fmt(q.histograms[histField].missing_n,0)}} 条，未参与分布统计</p></section>
     <section class="panel scatter-panel"><div class="panel-title"><h2>变量关系</h2><select v-model="xField" @change="loadQuery()" aria-label="关系图横轴"><option v-for="f in relationFields" :key="f" :value="f">{{schema[f]?.label}}</option></select></div><Chart :option="scatterChart" label="厚度等变量与粗轧温降关系散点图" @pick="e=>choose(e.data.value[2],true)"/><p v-if="q.scatter_valid_n>q.scatter.length" class="chart-note" title="按记录顺序等距抽样；统计使用全部样本。点击点可定位记录。">抽样显示 {{fmt(q.scatter.length,0)}} / {{fmt(q.scatter_valid_n,0)}} 个点</p></section>
    </div>
    </section>
    <div class="workbench-grid records-layout">
     <section class="panel records-panel"><div class="panel-title"><div><h2>板坯记录</h2></div><button class="secondary" @click="exportRows">导出当前范围</button></div><div class="table-scroll records-scroll"><table><thead><tr><th>板坯 / 记录</th><th>钢种</th><th>粗轧厚度<br>mm</th><th>出炉温度<br>°C</th><th>粗轧温降<br>°C</th><th>板坯尺寸<br>mm</th></tr></thead><tbody><tr v-for="r in q.records" :key="r.record_id" :data-id="r.record_id" :class="{selected:r.record_id===selected?.record_id}" @click="choose(r.record_id)" @keydown.enter="choose(r.record_id)" tabindex="0" :aria-selected="r.record_id===selected?.record_id"><td><strong>{{r.slab_id||'记录 '+r.source_row}}</strong><small v-if="r.slab_id">{{r.source_sheet}} · 第 {{r.source_row}} 行</small></td><td>{{r.steel_grade}}<small v-if="r.invalid" class="warning-text">{{r.quality_note}}</small></td><td>{{fmt(r.rough_thickness,2)}}</td><td>{{fmt(r.exit_temp,1)}}</td><td>{{fmt(r.temp_drop,1)}}</td><td>{{fmt(r.length,0)}} × {{fmt(r.width,0)}} × {{fmt(r.thickness,0)}}</td></tr><tr v-if="!q.records.length"><td colspan="6" class="empty-table">没有符合条件的记录，请调整筛选。</td></tr></tbody></table></div>
      <div class="pagination"><span class="pagination-total">共 {{fmt(q.total,0)}} 条 · 每页 30 条</span><div class="page-controls"><button @click="goPage(page-1)" :disabled="page<=1||loading" aria-label="上一页">‹</button><span class="page-position" aria-live="polite">{{page}} / {{pageCount}}</span><button @click="goPage(page+1)" :disabled="page>=pageCount||loading" aria-label="下一页">›</button><form class="page-jump" @submit.prevent="jump" novalidate><label>跳至<input v-model="jumpPage" type="text" inputmode="numeric" aria-label="跳转页码" :disabled="loading||!q.total" aria-describedby="page-error">页</label><button type="submit" class="secondary" :disabled="loading||!q.total">跳转</button></form></div></div><p v-if="pageError" id="page-error" class="page-error" role="alert">{{pageError}}</p>
     </section>
     <aside class="selected-column record-sidebar"><section class="panel record-details" :data-selected-id="selected?.record_id"><div class="panel-title"><div><span class="eyebrow">当前选中记录</span><h2 data-testid="selected-label">{{selectedLabel}}</h2></div><span v-if="selecting">更新中…</span></div><template v-if="selected"><p class="selected-grade">{{selected.steel_grade}}<span v-if="selected.furnace">炉号 {{selected.furnace}}</span></p><p class="record-time">{{selected.produced_at?.replace('T',' ')||'未提供生产时间'}}</p><div class="detail-metrics"><div v-for="k in ['exit_temp','temp_drop','rough_thickness','process_time','furnace_time','charge_temp']" :key="k"><span>{{schema[k]?.label}}</span><strong>{{fmt(selected[k],2)}} <small>{{schema[k]?.unit}}</small></strong></div></div><p class="record-dimensions">板坯尺寸 {{fmt(selected.length,0)}} × {{fmt(selected.width,0)}} × {{fmt(selected.thickness,0)}} mm</p><p v-if="selected.invalid" class="notice danger">需复核：{{selected.quality_note}}</p><details><summary>记录来源</summary><p>{{selected.source_file}} · {{selected.source_sheet}} · 第 {{selected.source_row}} 行</p><p v-if="!selected.slab_id">原文件没有板坯编号，记录标识不等同于真实板坯编号。</p><p class="record-id">{{selected.record_id}}</p></details><button class="secondary geometry-toggle" @click="threeOpen=!threeOpen" :aria-expanded="threeOpen">{{threeOpen?'收起三维示意':'查看三维示意'}}</button></template><p v-else class="muted">筛选范围为空。</p></section><SlabScene v-if="threeOpen" :record="selected" :scales="q.color_scales"/></aside>
    </div>
   </div>
   <AnalysisLab v-show="view==='analysis'" :dataset="dataset" :filters="activeFilters" :scope="q.scope" :schema="schema" :pending="loading" :active="view==='analysis'" @locate-record="locateAnalysisRecord" @restore-quick-scope="clearFilters"/>
  </template>
  <section v-else class="initial-loading" data-testid="initial-state" :role="error?'alert':'status'" aria-live="polite">
   <template v-if="loading"><progress aria-label="数据加载进度"></progress><h2>正在加载板坯记录…</h2></template>
   <template v-else-if="error"><h2>数据暂时未能加载</h2><p>{{error}}</p><button class="primary" @click="loadQuery()">重新加载数据</button><button class="text-button" @click="selectDataset(quickDataset.id)">使用快速示例</button></template>
   <template v-else><h2>尚未选择数据集</h2><button class="primary" @click="initialize">加载示例数据</button></template>
  </section>
  </div>
 </main>
 <ImportModal v-if="uploadOpen" :schema="schema" @close="uploadOpen=false" @imported="imported"/>
</div>
</template>
