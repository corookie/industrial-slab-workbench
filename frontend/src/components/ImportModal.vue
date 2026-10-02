<script setup>
import { ref, computed } from 'vue'
import { api, fmt } from '../api'
const props=defineProps({schema:Object})
const emit=defineEmits(['close','imported'])
const files=ref(null),header=ref(1),tables=ref([]),busy=ref(false),error=ref(''),name=ref(''),confirmed=ref(false),sourceKind=ref('real'),expanded=ref(0)
const fields=computed(()=>Object.entries(props.schema))
const included=computed(()=>tables.value.filter(t=>t.role!=='ignore'))
const selected=computed(()=>tables.value[expanded.value])
const numericUnits=unit=>({mm:['mm','cm','m'],'°C':['°C','K'],s:['s','min'],min:['min','s'],kg:['kg','t']})[unit]||[]
async function preview(){
  if(!files.value?.files?.length)return
  error.value='';busy.value=true;confirmed.value=false
  try{
    const data=new FormData()
    for(const file of files.value.files)data.append('files',file)
    data.append('header_row',Number(header.value)-1)
    const uploads=await api('/uploads',data)
    tables.value=uploads.flatMap(u=>u.tables.map(t=>({...t,upload_id:u.id,filename:u.filename,header_row:Number(header.value)-1,role:'ignore',mapping:{...t.mapping},units:{...t.units}})))
    if(tables.value.length)tables.value[0].role='main'
    expanded.value=0;name.value=uploads[0].filename.replace(/\.[^.]+$/,'')
  }catch(e){error.value=e.message}finally{busy.value=false}
}
async function doImport(){
  error.value='';busy.value=true
  try{
    const body={name:name.value,source_kind:sourceKind.value,units_confirmed:confirmed.value,tables:included.value.map(t=>({upload_id:t.upload_id,sheet:t.sheet,header_row:t.header_row,role:t.role,
      mapping:Object.fromEntries(Object.entries(t.mapping).filter(([,v])=>v)),
      units:Object.fromEntries(Object.entries(props.schema).filter(([k,s])=>s.kind==='number'&&t.mapping[k]).map(([k,s])=>[k,t.units[k]||s.unit]))}))}
    const result=await api('/datasets/import',body)
    emit('imported',result)
  }catch(e){error.value=e.message}finally{busy.value=false}
}
function missing(t,key){const c=t.columns.find(c=>c.name===t.mapping[key]);return c?`${fmt(c.missing,0)} / ${fmt(t.rows,0)}`:'未映射'}
</script>
<template>
<div class="modal-backdrop" @click.self="!busy&&emit('close')"><section class="import-modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
  <header class="modal-header"><div><h2 id="import-title">导入生产数据</h2></div><button class="icon-button" @click="emit('close')" :disabled="busy" aria-label="关闭导入窗口">×</button></header>
  <div class="modal-body">
    <div class="upload-row"><label class="file-zone"><span>选择 Excel / CSV 文件</span><input ref="files" type="file" accept=".xlsx,.csv" multiple aria-label="上传生产数据文件"></label><label>表头在第几行<input v-model="header" type="number" min="1" max="31" aria-label="表头行号"></label><button class="primary" @click="preview" :disabled="busy">{{busy?'正在处理…':'预览字段'}}</button></div>
    <p v-if="error" class="notice danger" role="alert">{{error}}</p>
    <template v-if="tables.length">
      <div class="table-selector"><div v-for="(t,i) in tables" :key="i" class="source-table" :class="{active:expanded===i}"><button @click="expanded=i"><strong>{{t.filename}}</strong><small>{{t.sheet}} · {{fmt(t.rows,0)}} 条记录</small></button><select v-model="t.role" :aria-label="`${t.sheet}整理方式`"><option value="main">主表</option><option value="ignore">不导入</option><option value="append">按行追加</option><option value="join">按板坯编号关联</option></select></div></div>
      <p v-if="included.length>1" class="notice">关联表要求板坯编号完整且唯一；只填充主表缺失字段，冲突保留主表并记录。按行追加适用于相同记录口径的不同月份，不会按钢种关联。</p>
      <div v-if="selected" class="preview-block"><h3>{{selected.sheet}} 原始字段预览</h3><div class="table-scroll"><table><thead><tr><th v-for="c in selected.columns" :key="c.name">{{c.name}}</th></tr></thead><tbody><tr v-for="(row,i) in selected.preview" :key="i"><td v-for="c in selected.columns" :key="c.name">{{row[c.name]??'—'}}</td></tr></tbody></table></div>
        <h3>字段映射与输入单位</h3><div class="mapping-scroll"><table class="mapping-table"><thead><tr><th>工作台字段</th><th>原始字段</th><th>输入单位</th><th>缺失值 / 总行数</th></tr></thead><tbody><tr v-for="[key,field] in fields" :key="key"><td>{{field.label}}</td><td><select v-model="selected.mapping[key]" :aria-label="`映射${field.label}`"><option value="">未提供</option><option v-for="c in selected.columns" :value="c.name" :key="c.name">{{c.name}}</option></select></td><td><select v-if="field.kind==='number'&&selected.mapping[key]" v-model="selected.units[key]" :aria-label="`${field.label}单位`"><option v-for="u in numericUnits(field.unit)" :value="u" :key="u">{{u}}</option></select><span v-else>—</span></td><td>{{missing(selected,key)}}</td></tr></tbody></table></div>
      </div>
      <div class="import-options"><label>数据集名称<input v-model="name" maxlength="120"></label><label>数据性质<select v-model="sourceKind" aria-label="数据性质"><option value="real">真实生产数据</option><option value="simulated">模拟示例数据</option></select></label></div>
      <label class="confirm-units"><input type="checkbox" v-model="confirmed">我已确认所选表的字段含义、输入单位和整理方式</label>
      <details class="import-rules"><summary>导入规则</summary><p>没有板坯编号时，使用原始行号和记录标识。导入后单位统一为：尺寸 mm、温度 °C、过程时间 s、在炉时间 min。</p></details>
    </template>
  </div>
  <footer class="modal-footer"><span>{{included.length}} 个表参与导入</span><button class="secondary" @click="emit('close')" :disabled="busy">取消</button><button class="primary" @click="doImport" :disabled="busy||!confirmed||!name.trim()||!included.length">确认并导入</button></footer>
</section></div>
</template>
