<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { PROCESS_DURATION, PROCESS_PLAYBACK_RATE, PROCESS_OVERVIEW, PROCESS_STAGES, advanceProcessTime, processState } from '../process'

defineEmits(['workbench','analysis'])
const time=ref(0),playing=ref(false),mobile=ref(false),selectedStage=ref(-1)
const state=computed(()=>processState(time.value))
const animationStage=computed(()=>PROCESS_STAGES[state.value.stage])
const stage=computed(()=>selectedStage.value<0?PROCESS_OVERVIEW:PROCESS_STAGES[selectedStage.value])
const processTabs=[PROCESS_OVERVIEW,...PROCESS_STAGES]
const zones=['预热','一加','二加','均热']
const finishStands=[1020,1088,1156,1224]
const chargeRollers=[35,62,89,116,143]
const rollers=[590,616,690,717,745,950,978,1266,1294,1322,1350,1378]
const mobileViews=['0 150 280 230','125 35 455 340','550 130 205 250','700 125 335 280','980 130 440 220']
const roughGap=computed(()=>state.value.stage===3?state.value.height:18)
const roughRolls=computed(()=>[{y:268-14-roughGap.value/2-39,r:24},{y:268-14-roughGap.value/2,r:14},{y:268+14+roughGap.value/2,r:14},{y:268+14+roughGap.value/2+39,r:24}])
const finishRolls=computed(()=>{const gap=state.value.stage===4?state.value.height:8;return [268-16-gap/2,268+16+gap/2]})
const viewBox=computed(()=>mobile.value?mobileViews[state.value.stage]:'0 0 1440 455')
let frame=0,last=0,motionQuery,sizeQuery
function tick(now){
 if(!playing.value)return
 if(!document.hidden){time.value=advanceProcessTime(time.value,last?Math.min((now-last)/1000,.1):0);last=now}
 else last=0
 frame=requestAnimationFrame(tick)
}
function stop(){playing.value=false;cancelAnimationFrame(frame);frame=0;last=0}
function play(){if(time.value>=PROCESS_DURATION)time.value=0;playing.value=true;last=0;cancelAnimationFrame(frame);frame=requestAnimationFrame(tick)}
function toggle(){playing.value?stop():play()}
function replay(){time.value=0;play()}
function seek(value){stop();time.value=Number(value)}
function selectStage(index){selectedStage.value=index;time.value=index<0?0:PROCESS_STAGES[index].start;play()}
function visibility(){if(document.hidden)last=0}
function resize(){mobile.value=sizeQuery.matches}
function reducedMotion(){if(motionQuery.matches)stop()}
onMounted(()=>{
 motionQuery=window.matchMedia('(prefers-reduced-motion: reduce)')
 sizeQuery=window.matchMedia('(max-width: 760px)');resize()
 sizeQuery.addEventListener('change',resize);motionQuery.addEventListener('change',reducedMotion)
 document.addEventListener('visibilitychange',visibility)
 if(!motionQuery.matches)play()
})
onBeforeUnmount(()=>{stop();sizeQuery?.removeEventListener('change',resize);motionQuery?.removeEventListener('change',reducedMotion);document.removeEventListener('visibilitychange',visibility)})
</script>

<template>
 <section class="process-home" aria-labelledby="process-title" data-testid="process-home">
  <div class="process-heading"><div><h1 id="process-title">粗轧过程</h1><p>看懂热轧流程，找到粗轧温降的观察区间。</p></div><button class="primary" @click="$emit('workbench')">进入数据工作台 <span aria-hidden="true">↗</span></button></div>
  <div class="process-card" :data-stage="animationStage.key" :data-selected-stage="stage.key" :data-playing="playing" :data-time="time.toFixed(3)">
   <div class="process-toolbar"><div class="process-legend"><span><i class="material-swatch"></i>板坯 / 带钢</span><span><i class="gas-swatch"></i>烟气流向</span></div><div class="process-controls"><button class="secondary" @click="toggle" :aria-label="playing?'暂停工艺动画':'播放工艺动画'" :title="`${PROCESS_PLAYBACK_RATE} 倍速，自动循环`"><span aria-hidden="true">{{playing?'Ⅱ':'▷'}}</span>{{playing?'暂停':state.finished?'再次播放':'播放'}}</button><button class="text-button" @click="replay" aria-label="重播工艺动画">重播 <span aria-hidden="true">↺</span></button></div></div>
   <div class="process-canvas" role="region" aria-label="板坯加热、除鳞、粗轧和精轧的工艺示意">
    <svg :viewBox="viewBox" class="rolling-svg" role="img" aria-labelledby="rolling-title rolling-desc">
     <title id="rolling-title">板坯热轧工艺示意</title><desc id="rolling-desc">板坯按 01 至 05 经过装炉、四区加热、除鳞、粗轧和精轧，厚度逐步减小。烟气在炉内逆向流动，经过余热回收后排出；回收热量用于预热助燃空气，空气返回烧嘴。图中颜色与运动均为示意。</desc>
     <defs>
      <marker id="slab-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 1 9 5 0 9" fill="none" stroke="#9fa58f" stroke-width="1.5"/></marker>
      <marker id="gas-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 10 5 0 10Z" fill="#85946b"/></marker>
      <linearGradient id="furnace-warm" x1="0" x2="1"><stop offset="0" stop-color="#e9e2d7"/><stop offset=".65" stop-color="#f8dec3"/><stop offset="1" stop-color="#f5ceb1"/></linearGradient>
     </defs>
     <!-- A single authored material route; equipment is a generic schematic. -->
     <path class="transport-line" d="M25 268 H1410" marker-end="url(#slab-arrow)"/>
     <g class="conveyor"><g v-for="x in rollers" :key="x"><circle :cx="x" cy="291" r="9"/><path :d="`M${x-5} 291h10`"/></g></g>
     <g class="charging" :class="{'is-current':state.stage===0}">
      <g class="equipment-heading compact" data-step="01" transform="translate(12 227)"><rect width="29" height="27" y="-20" rx="6"/><text class="equipment-number" x="14.5" text-anchor="middle">01</text><text class="equipment-title" x="38">装炉辊道</text></g>
      <g class="charge-rollers" v-for="x in chargeRollers" :key="x"><circle :cx="x" cy="286" r="9"/><path :transform="`rotate(${-state.x*2} ${x} 286)`" :d="`M${x-5} 286h10`"/></g>
      <path class="charge-direction" d="M39 246H116" marker-end="url(#slab-arrow)"/>
     </g>
     <g class="heating" :class="{'is-current':state.stage===1}">
      <g class="equipment-heading" data-step="02" transform="translate(269 145)"><rect width="29" height="27" y="-20" rx="6"/><text class="equipment-number" x="14.5" text-anchor="middle">02</text><text class="equipment-title" x="41">步进式加热炉</text></g>
      <path class="furnace-body" d="M169 172H557Q575 172 575 190V247H566V287H575V312Q575 330 557 330H169Q151 330 151 312V287H160V247H151V190Q151 172 169 172Z"/>
      <g v-for="(name,i) in zones" :key="name" class="furnace-zone" :class="{'zone-current':state.zone===i}">
       <rect :x="160+i*103" y="181" width="99" height="140" rx="10"/><text :x="209+i*103" y="205" text-anchor="middle">{{name}}</text>
       <path class="burner" :d="`M${183+i*103} 218h14v13h-14z M${183+i*103} 308h14v-13h-14z`"/>
       <path class="flame" :opacity="state.stage===1?.55+.35*Math.sin(time*4+i):.25" :d="`M${201+i*103} 225q21 -12 12 0q9 12 -12 0 M${201+i*103} 301q21 -12 12 0q9 12 -12 0`"/>
      </g>
      <path class="walking-beam" :transform="`translate(0 ${state.stage===1?(state.y-268)*.8:0})`" d="M171 287h380 M195 283v8 M295 283v8 M395 283v8 M495 283v8"/>
      <g class="furnace-entry">
       <path class="door-frame" d="M145 247v-43h15v43"/>
       <rect class="raised-door" x="147" y="207" width="11" height="30" rx="2"/>
       <path class="entry-floor" d="M148 287h33"/>
       <text x="145" y="358" text-anchor="middle">装炉口</text>
      </g>
     </g>
     <!-- Static direction cue; heat recovery is explained by the caption. -->
     <g class="furnace-gas">
      <path d="M548 172V84Q548 70 530 70H188Q168 70 168 90V122" marker-end="url(#gas-arrow)"/>
      <text x="357" y="51" text-anchor="middle">烟气逆向 · 余热用于预热助燃空气</text>
     </g>
     <g class="descaler" :class="{'is-current':state.stage===2}">
      <g class="equipment-heading" data-step="03" transform="translate(588 145)"><rect width="29" height="27" y="-20" rx="6"/><text class="equipment-number" x="14.5" text-anchor="middle">03</text><text class="equipment-title" x="41">高压水除鳞</text></g>
      <path class="water-feed" d="M618 177 H704 V197 H618 Z M631 198v9 M650 198v9 M669 198v9 M688 198v9"/>
      <g class="water-jets" :opacity="state.spray?1:.18"><path v-for="x in [631,650,669,688]" :key="x" :d="`M${x} 214l-9 37 M${x} 214l9 37`"/><circle v-if="state.spray" v-for="i in 9" :key="i" :cx="624+(i%4)*20" :cy="218+((time*85+i*13)%39)" r="2"/></g>
      <text class="svg-muted" x="661" y="331" text-anchor="middle">去除氧化铁皮</text>
     </g>
     <g class="rough-mill" :class="{'is-current':state.stage===3}">
      <g class="equipment-heading" data-step="04" transform="translate(799.5 145)"><rect width="29" height="27" y="-20" rx="6"/><text class="equipment-number" x="14.5" text-anchor="middle">04</text><text class="equipment-title" x="41">粗轧</text></g>
      <rect class="mill-frame" x="782" y="165" width="117" height="186" rx="17"/>
      <path class="mill-support" d="M791 182h100 M791 335h100 M797 180v155 M884 180v155"/>
      <g v-for="(r,i) in roughRolls" :key="i" class="mill-roll"><circle cx="841" :cy="r.y" :r="r.r"/><path :transform="`rotate(${state.stage===3?-(state.x-755)*2.4*(i<2?1:-1):0} 841 ${r.y})`" :d="`M${841-r.r*.65} ${r.y}h${r.r*1.3} M841 ${r.y-r.r*.65}v${r.r*1.3}`"/></g>
      <text class="svg-muted" x="841" y="383" text-anchor="middle">多道次压下（示意）</text>
     </g>
     <g class="finish-mill" :class="{'is-current':state.stage===4}">
      <g class="equipment-heading" data-step="05" transform="translate(1059.5 145)"><rect width="29" height="27" y="-20" rx="6"/><text class="equipment-number" x="14.5" text-anchor="middle">05</text><text class="equipment-title" x="41">精轧机组</text></g>
      <g v-for="(x,i) in finishStands" :key="x"><rect class="mill-frame" :x="x-28" y="211" width="56" height="111" rx="9"/><path class="mill-support" :d="`M${x-20} 220v93 M${x+20} 220v93`"/><g v-for="(y,j) in finishRolls" :key="j" class="mill-roll"><circle :cx="x" :cy="y" r="16"/><path :transform="`rotate(${state.stage===4?-state.rollAngle*(j?-1:1)+i*30:0} ${x} ${y})`" :d="`M${x-9} ${y}h18 M${x} ${y-9}v18`"/></g></g>
      <text class="svg-muted" x="1122" y="351" text-anchor="middle">连续压下</text>
     </g>
     <g class="output"><text x="1350" y="211" text-anchor="middle">带钢</text><path d="M1307 225h83"/></g>
     <g class="process-material" :transform="`translate(${state.x} ${state.y})`" :data-x="state.x.toFixed(3)" :data-thickness="state.height.toFixed(3)">
      <rect class="material-halo" x="-44" y="-17" width="88" height="34" rx="10" :opacity="state.stage===1?state.heat*.2:0"/>
      <g :transform="`scale(${state.width/72} ${state.height/18})`"><rect x="-36" y="-9" width="72" height="18" rx="3" :fill="state.color"/><path d="M-30 -4H30" stroke="#ffffff" stroke-opacity=".45" stroke-width="1.5"/></g>
     </g>
     <g class="temperature-observation"><path d="M591 332v73h356v-73"/><circle cx="591" cy="332" r="3"/><circle cx="947" cy="332" r="3"/><text x="769" y="428" text-anchor="middle">粗轧温降 = 出炉温度 − 粗轧后温度</text></g>
    </svg>
   </div>
   <p class="mobile-temperature-formula">粗轧温降 = 出炉温度 − 粗轧后温度</p>
   <div class="process-timeline"><input type="range" min="0" :max="PROCESS_DURATION" step=".01" :value="time" @input="seek($event.target.value)" aria-label="工艺动画进度" :aria-valuetext="animationStage.name" :style="{'--progress':`${state.progress*100}%`}"></div>
   <div class="process-steps" role="group" aria-label="选择工艺阶段"><button v-for="(item,i) in processTabs" :key="item.key" :class="{selected:selectedStage===i-1}" :aria-pressed="selectedStage===i-1" @click="selectStage(i-1)"><span v-if="i>0">{{String(i).padStart(2,'0')}}</span><span v-else aria-hidden="true">◎</span>{{item.name}}<i v-if="selectedStage===i-1" aria-hidden="true">→</i></button></div>
   <div class="process-explanation"><div><h2><span v-if="selectedStage>=0" class="explanation-number" aria-hidden="true">{{String(selectedStage+1).padStart(2,'0')}}</span>{{stage.title}}</h2><p>{{stage.body}}</p></div><div class="process-fields"><span>相关记录字段</span><div><b v-for="field in stage.fields" :key="field">{{field}}</b></div></div></div>
  </div>
  <div class="process-bottom"><p>工艺示意：颜色、尺寸、设备数量与播放节拍不代表实际生产工况。</p><button class="text-button" @click="$emit('analysis')">进入厚度与温降分析 <span aria-hidden="true">→</span></button></div>
  <details class="process-sources"><summary>工艺说明与资料依据</summary><p>依据项目技术附件与结题汇报梳理：步进式炉的预热、一加、二加、均热四区；烟气余热回收与助燃空气预热；炉后输送与高压水除鳞；出炉温度与粗轧后带钢温度的差值口径。烟气箭头只表示逆向流动，余热利用用文字说明，未绘制回收设备或换向结构。图中的轧机结构、道次与机架数量为通用示意，未按实际产线布局复刻。</p><p>参考材料：《宝钢1880 技术附件：融合数据智能的1880加热炉》《结题汇报：轧钢加热炉》。精轧展示只用于交代工艺衔接，当前分析重点为粗轧温降。</p></details>
 </section>
</template>

<style scoped>
.process-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin:4px 0 24px}.process-heading p{font-size:14px;color:var(--muted);margin-top:10px}.process-card{background:var(--surface);border:1px solid #d7dbce;border-radius:20px;overflow:hidden}.process-toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:16px 24px 0}.process-legend{display:flex;flex-wrap:wrap;gap:10px 22px;color:#6e7663;font-size:13px}.process-legend span{display:flex;align-items:center;gap:8px}.process-legend i{display:block;width:22px;height:3px;background:#85946b}.process-legend i.material-swatch{height:9px;border-radius:3px;background:#ea8855}.process-controls{display:flex;align-items:center;gap:18px}.process-controls button{font-size:13px}.process-controls .secondary{min-width:86px}.process-canvas{padding:0 22px 24px;overflow:hidden}.rolling-svg{display:block;width:100%;height:auto;overflow:visible}.rolling-svg text{font-family:inherit;font-size:18px;fill:#535c4b}.rolling-svg .equipment-title{font-size:21px;font-weight:650;fill:#3e4937}.equipment-heading rect{fill:#7e8e6c;stroke:none}.rolling-svg .equipment-number{font-size:14px;font-weight:700;fill:#fffefa;stroke:none}.equipment-heading.compact .equipment-title{font-size:18px}.rolling-svg .svg-muted{font-size:16px;fill:#7b826f}.transport-line{fill:none;stroke:#d4d7c9;stroke-width:2;stroke-dasharray:4 8}.conveyor{fill:#f1f2ea;stroke:#b8beaa;stroke-width:1.6}.charging text{font-weight:550}.charge-rollers{fill:#f1f2ea;stroke:#aab49e;stroke-width:1.6}.charge-direction{fill:none;stroke:#a5ad98;stroke-width:1.8}.charging.is-current .charge-rollers{fill:#ece6ef;stroke:#8c7893}.furnace-gas{fill:none;stroke:#85946b;stroke-width:2}.furnace-gas text{stroke:none;fill:#788568;font-size:17px}.furnace-body{fill:url(#furnace-warm);stroke:#8b907f;stroke-width:2}.furnace-zone rect{fill:#fffaf1;fill-opacity:.6;stroke:none}.furnace-zone.zone-current rect{fill:#ffca9a;fill-opacity:.7}.burner{fill:#929886;stroke:none}.flame{fill:#f8955d;stroke:none}.walking-beam{fill:none;stroke:#8e907f;stroke-width:2}.door-frame{fill:none;stroke:#8b907f;stroke-width:2;stroke-linejoin:round}.raised-door{fill:#adb59e;stroke:#8b907f;stroke-width:1.5}.entry-floor{fill:none;stroke:#8e907f;stroke-width:2}.furnace-entry text{font-size:16px;fill:#7b826f}.heating.is-current .furnace-body{stroke:#cf8756;stroke-width:2.5}.water-feed{fill:#e7eeed;stroke:#74959c;stroke-width:2}.water-jets{fill:#679aa8;stroke:#81aeb8;stroke-width:1.8}.descaler.is-current .water-feed{stroke:#41656e;fill:#d8e8e7}.mill-frame{fill:#eef0e6;stroke:#8f9a82;stroke-width:2}.mill-support{fill:none;stroke:#b2baa6;stroke-width:1.5}.mill-roll circle{fill:var(--surface);stroke:#768368;stroke-width:2}.mill-roll path{fill:none;stroke:#b6bfaa;stroke-width:1.5}.rough-mill.is-current .mill-frame,.finish-mill.is-current .mill-frame{fill:#f5e4d1;stroke:#d0895b}.rough-mill.is-current .mill-roll circle,.finish-mill.is-current .mill-roll circle{stroke:#a66a44}.output{fill:none;stroke:#bdc2b0;stroke-width:1.6}.output text{stroke:none}.process-material rect{stroke:none}.material-halo{fill:#eea168}.temperature-observation{fill:#b7795c;stroke:#bc967e;stroke-width:1.5}.temperature-observation path{fill:none;stroke-dasharray:5 5}.temperature-observation text{stroke:none;fill:#a36c4a;font-size:17px}.process-timeline{padding:0 24px}.process-timeline input{display:block;width:100%;height:18px;min-height:18px;padding:0;cursor:pointer;appearance:none;-webkit-appearance:none;border:0;border-radius:0;background:transparent}.process-timeline input::-webkit-slider-runnable-track{height:3px;border-radius:3px;background:linear-gradient(to right,#ee8c64 var(--progress),#e7e9df var(--progress))}.process-timeline input::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;width:12px;height:12px;margin-top:-4.5px;border:2px solid #fffefa;border-radius:50%;background:#d66b43;box-shadow:0 0 0 1px #d66b43}.process-timeline input::-moz-range-track{height:3px;background:#e7e9df}.process-timeline input::-moz-range-progress{height:3px;background:#ee8c64}.process-timeline input::-moz-range-thumb{width:10px;height:10px;border:2px solid #fffefa;background:#d66b43;border-radius:50%}.process-steps{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;padding:12px 24px 20px}.process-steps button{display:flex;align-items:center;gap:10px;border:1px solid transparent;border-radius:10px;background:#f0f1e9;color:#5f6a53;padding:11px 14px;font-weight:600;min-height:44px;text-align:left;white-space:nowrap}.process-steps button span{font-size:12px;color:#929983;font-variant-numeric:tabular-nums}.process-steps button i{margin-left:auto;font-style:normal;color:#9aa388}.process-steps button:hover{background:#e7eddb}.process-steps button.selected{background:#e5edda;border-color:#adc190;color:#3e5a28}.process-steps button.selected span{color:#6c8a4b}.process-explanation{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:30px;border-top:1px solid #e6e8dc;background:#f7f8f1;padding:20px 24px;min-height:126px}.process-explanation h2{display:flex;align-items:center;gap:10px;font-size:18px;margin-bottom:8px}.explanation-number{display:inline-flex;align-items:center;justify-content:center;flex:none;width:27px;height:25px;border-radius:6px;background:#7e8e6c;color:#fffefa;font-size:13px;font-weight:700;font-variant-numeric:tabular-nums}.process-explanation p{color:#65705a;font-size:14px;line-height:1.8;max-width:850px}.process-fields{border-left:1px solid #dfe4d2;padding-left:24px}.process-fields>span{font-size:12px;color:#828b76}.process-fields>div{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.process-fields b{font-size:12px;font-weight:500;color:#667653;border:1px solid #dfe6d2;background:#edf2e4;padding:4px 9px;border-radius:6px}.process-bottom{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:16px 2px}.process-bottom p{font-size:12px;color:#838877}.process-bottom button{color:#7d5945;flex:none}.process-sources{font-size:12px;color:#7a826d}.process-sources summary{width:fit-content;padding:4px 0}.process-sources p{margin-top:10px;line-height:1.8;max-width:1000px}
.mobile-temperature-formula{display:none}
@media(min-width:1800px){.process-canvas{max-width:1500px;margin:auto}}
@media(max-width:1000px){.process-steps{grid-template-columns:repeat(3,minmax(0,1fr))}.process-explanation{grid-template-columns:1fr;gap:14px}.process-fields{padding-left:0;border:0}.process-fields>span{display:none}.process-fields>div{margin-top:0}.process-steps button{padding:10px 8px;gap:6px}.process-steps button i{display:none}}
@media(max-width:760px){.mobile-temperature-formula{display:block;text-align:center;font-size:12px;color:#a36c4a;padding:4px 12px 12px}.temperature-observation{display:none}.process-card[data-stage='charge'] .heating .equipment-heading{visibility:hidden}.process-card:not([data-stage='heat']) .furnace-gas{visibility:hidden}.process-card[data-stage='heat'] .charging,.process-card[data-stage='heat'] .descaler{visibility:hidden}.process-card[data-stage='rough'] .descaler,.process-card[data-stage='rough'] .heating,.process-card[data-stage='rough'] .finish-mill,.process-card[data-stage='finish'] .rough-mill,.process-card[data-stage='descale'] .heating,.process-card[data-stage='descale'] .rough-mill{visibility:hidden}.process-heading{display:block;margin-bottom:18px}.process-heading .primary{margin-top:16px}.process-heading p{font-size:13px}.process-card{border-radius:16px}.process-toolbar{padding:14px 16px 0;gap:10px;flex-wrap:wrap}.process-legend{font-size:11px;gap:14px}.process-controls{gap:14px;margin-left:auto}.process-controls button{font-size:12px}.process-controls .secondary{min-height:36px;min-width:75px;padding:8px 10px}.process-canvas{height:320px;display:flex;align-items:center;padding:12px 16px 0}.rolling-svg{height:100%;overflow:hidden}.process-timeline{padding:0 16px}.process-steps{grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;padding:12px 16px 16px}.process-steps button{font-size:12px;min-height:42px;gap:7px}.process-explanation{padding:18px 16px;min-height:184px}.process-explanation h2{font-size:17px}.process-explanation p{font-size:13px}.process-bottom{flex-direction:column;align-items:flex-start;gap:4px;padding:14px 2px}.process-bottom p{font-size:11px}.process-sources{font-size:11px}}
</style>
