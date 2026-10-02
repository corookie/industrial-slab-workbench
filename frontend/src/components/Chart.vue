<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([BarChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])
const props = defineProps({ option: Object, label: String })
const emit = defineEmits(['pick'])
const el=ref(null)
let chart, observer
function renderSized(){
  if(!el.value?.clientWidth||!el.value?.clientHeight)return
  if(chart){chart.resize();return}
  chart=echarts.init(el.value, null, {renderer:'canvas'})
  chart.setOption(props.option, {notMerge:true})
  chart.on('click', event=>emit('pick', event))
}
onMounted(()=>{
  // The process homepage keeps the workbench hidden until opened.
  // Initialize at a real size, and retain charts when navigating back.
  observer=new ResizeObserver(renderSized)
  observer.observe(el.value)
  renderSized()
})
watch(()=>props.option, value=>chart?.setOption(value,{notMerge:true}), {deep:true})
onBeforeUnmount(()=>{observer?.disconnect(); chart?.dispose();chart=null})
</script>
<template><div ref="el" class="chart" role="img" :aria-label="label"></div></template>
