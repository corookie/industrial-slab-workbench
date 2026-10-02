// Illustration clock only: these timings are not production residence times.
export const PROCESS_DURATION = 32
export const PROCESS_PLAYBACK_RATE = 1.5
// Preserve overflow at the cycle boundary so every loop uses the same clock.
export function advanceProcessTime(time,elapsed){
 return (time+Math.max(0,elapsed)*PROCESS_PLAYBACK_RATE)%PROCESS_DURATION
}
export const PROCESS_OVERVIEW = {
 key:'overview',name:'总览',title:'加热与轧制流程',
 body:'板坯装炉后依次经过预热、一加、二加和均热；出炉后通过高压水除鳞，再经粗轧形成中间坯、精轧形成带钢。本图展示到精轧出口，后续还有冷却与卷取。粗轧温降关注出炉至粗轧后的温度变化。',
 fields:['板坯尺寸','出炉温度','粗轧厚度','粗轧温降']
}
export const PROCESS_STAGES = [
 { key:'charge', name:'装炉', start:0, end:3, title:'板坯装炉', body:'板坯进入步进式加热炉，为后续热轧准备。装炉温度与在炉时间是加热工况的一部分。', fields:['装炉温度','在炉时间'] },
 { key:'heat', name:'加热', start:3, end:15, title:'四区加热与均热', body:'板坯依次经过预热、一加、二加、均热区，步进机构向出炉端输送。烟气在炉内逆向流动，余热用于预热助燃空气，回收后烟气排出。预热空气送回烧嘴助燃，均热区改善板坯温度的均匀性。', fields:['装炉温度','在炉时间','出炉温度'] },
 { key:'descale', name:'出炉与除鳞', start:15, end:19, title:'出炉输送与高压水除鳞', body:'出炉后的板坯经辊道输送，高压水去除表面氧化铁皮。输送与水冷换热会带来温度变化，是观察粗轧温降时需要考虑的过程。', fields:['出炉温度','粗轧过程时间'] },
 { key:'rough', name:'粗轧', start:19, end:25, title:'粗轧压下，形成中间坯', body:'通过多道次压下减小厚度、延长板坯。工作台比较相近钢种、出炉温度和过程时间范围内，不同粗轧厚度对应的温降差异。', fields:['粗轧厚度','粗轧过程时间','粗轧温降'] },
 { key:'finish', name:'精轧', start:25, end:32, title:'精轧，形成带钢', body:'中间坯进入精轧机组，连续压下至后续产品所需厚度。精轧之后还有冷却与卷取，本图展示到精轧出口。', fields:['轧制厚度','精轧温度（若有）'] }
]
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v))
const lerp=(a,b,p)=>a+(b-a)*p
const ease=p=>p*p*(3-2*p)
const thermalColor=p=>{
 const a=[113,100,123],b=[247,123,66]
 return `rgb(${a.map((v,i)=>Math.round(lerp(v,b[i],clamp(p)))).join(',')})`
}
// Pure time -> state makes pause, seek, reverse seek and replay agree.
export function processState(time){
 const t=clamp(Number.isFinite(time)?time:0,0,PROCESS_DURATION)
 const index=PROCESS_STAGES.findIndex(s=>t<s.end)
 const stage=Math.max(0,index<0?PROCESS_STAGES.length-1:index)
 let x=60,y=268,width=72,height=18,heat=0,zone=-1
 if(t<3)x=lerp(60,195,ease(t/3))
 else if(t<15){
  const p=(t-3)/12,step=p*12,whole=Math.floor(step),fraction=step-whole
  x=195+(whole+ease(fraction))*355/12
  y-=Math.sin(Math.PI*fraction)*5
  heat=p;zone=Math.min(3,Math.floor(p*4))
 }else if(t<19){
  const p=(t-15)/4
  x=p<.4?lerp(550,650,ease(p/.4)):p<.6?650:lerp(650,755,ease((p-.6)/.4))
  heat=lerp(1,.82,p)
 }else if(t<25){
  const p=(t-19)/6
  // A generic reversing-pass illustration, not the actual mill pass schedule.
  const waypoints=[755,890,750,900,945],segment=Math.min(3,Math.floor(p*4)),f=p*4-segment
  x=lerp(waypoints[segment],waypoints[segment+1],ease(f))
  width=lerp(72,136,p);height=lerp(18,8,p);heat=lerp(.82,.67,p)
 }else{
  const p=(t-25)/7
  x=lerp(945,1340,ease(p));width=lerp(136,166,p);height=lerp(8,3.5,p);heat=lerp(.67,.52,p)
 }
 return {time:t,stage,x,y,width,height,color:thermalColor(heat),heat,zone,
  spray:t>=16.2&&t<18.3,rollAngle:(t>=19?t-19:0)*160,
  progress:t/PROCESS_DURATION,finished:t===PROCESS_DURATION}
}
