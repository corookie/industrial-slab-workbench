<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { slabGeometry, colorFor } from '../slab'
import { fmt } from '../api'
const props=defineProps({record:Object, scales:Object})
const host=ref(null),failure=ref(''),metric=ref('temp_drop'),enlarge=ref(true)
const geometry=computed(()=>slabGeometry(props.record,enlarge.value?4:1))
const scale=computed(()=>props.scales?.[metric.value])
const color=computed(()=>colorFor(props.record?.[metric.value],scale.value))
const label=computed(()=>metric.value==='temp_drop'?'粗轧温降':'出炉温度')
const fallbackLabels=computed(()=>geometry.value.fallback.map(k=>({length:'长度',width:'宽度',thickness:'厚度'})[k]))
let renderer,scene,camera,controls,mesh,outline,observer,frame,disposed=false
function reset(){
  if(!camera||!controls)return
  const g=geometry.value,radius=Math.sqrt(g.x*g.x+g.y*g.y+g.z*g.z)/2
  const vertical=THREE.MathUtils.degToRad(camera.fov)/2
  const halfAngle=Math.min(vertical,Math.atan(Math.tan(vertical)*camera.aspect))
  const distance=radius/Math.sin(halfAngle)*1.2
  controls.target.set(0,g.y/2,0)
  camera.position.copy(new THREE.Vector3(1,.7,1.1).normalize().multiplyScalar(distance).add(controls.target))
  controls.update()
}
function update(){
  if(!mesh)return
  const g=geometry.value
  mesh.visible=!!props.record;outline.visible=!!props.record
  mesh.geometry.dispose();outline.geometry.dispose()
  mesh.geometry=new THREE.BoxGeometry(g.x,g.y,g.z)
  mesh.position.y=g.y/2+.04
  mesh.material.color.set(color.value)
  outline.geometry=new THREE.EdgesGeometry(mesh.geometry)
  outline.position.copy(mesh.position)
  reset()
}
function resize(){
  if(!renderer||!host.value)return
  const w=host.value.clientWidth,h=host.value.clientHeight
  if(!w||!h)return
  renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix()
}
onMounted(()=>{
  try {
    scene=new THREE.Scene();scene.background=new THREE.Color('#1b231b')
    camera=new THREE.PerspectiveCamera(38,1,.01,5000)
    renderer=new THREE.WebGLRenderer({antialias:true})
    renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace
    host.value.appendChild(renderer.domElement)
    controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enablePan=false;controls.minDistance=1;controls.maxDistance=2000
    scene.add(new THREE.HemisphereLight('#ffffff','#748298',1.2))
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1
    const light=new THREE.DirectionalLight('#ffffff',1.8);light.position.set(4,8,5);scene.add(light)
    const grid=new THREE.GridHelper(20,20,'#60714f','#34442b');scene.add(grid)
    mesh=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({color:color.value,roughness:.65,metalness:.12}));scene.add(mesh)
    outline=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),new THREE.LineBasicMaterial({color:'#f7d19f',transparent:true,opacity:.65}));scene.add(outline)
    const axes=new THREE.AxesHelper(2.2);axes.position.set(-6,.02,4);scene.add(axes)
    observer=new ResizeObserver(resize);observer.observe(host.value)
    resize();update()
    function render(){if(disposed)return;controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(render)}render()
  } catch(e){failure.value='三维视图暂不可用，请使用支持 WebGL 的浏览器。记录详情仍可查看。';console.error('WebGL initialization',e)}
})
watch([()=>props.record,color,enlarge],update)
onBeforeUnmount(()=>{
  disposed=true;cancelAnimationFrame(frame);observer?.disconnect();controls?.dispose()
  scene?.traverse(o=>{o.geometry?.dispose();if(o.material){(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose())}})
  renderer?.dispose();renderer?.domElement.remove()
})
</script>
<template>
  <section class="slab-visual" :data-record-id="record?.record_id" :data-length="geometry.values.length" :data-width="geometry.values.width" :data-thickness="geometry.values.thickness" :data-color="color">
    <div class="slab-toolbar"><span>板坯三维视图</span><button @click="reset" class="dark-button" aria-label="重置三维视角">重置视角</button></div>
    <div ref="host" class="scene-host"><div v-if="failure" class="scene-empty">{{failure}}</div></div>
    <div v-if="!record" class="scene-overlay">当前筛选范围没有记录</div>
    <div class="scene-caption">拖动旋转 · 滚轮缩放</div>
    <div class="slab-tools"><label><input type="checkbox" v-model="enlarge">厚度显示放大 ×4</label><select v-model="metric" aria-label="三维颜色指标"><option value="temp_drop">粗轧温降</option><option value="exit_temp">出炉温度</option></select></div>
    <div class="color-scale"><span>{{label}} · °C</span><div class="color-gradient"></div><div class="scale-ticks"><span>{{fmt(scale?.min)}}</span><span>{{fmt(scale?.max)}}</span></div></div>
    <div class="geometry-note"><span>尺寸：{{fmt(geometry.values.length,0)}} × {{fmt(geometry.values.width,0)}} × {{fmt(geometry.values.thickness,0)}} mm</span><span v-if="fallbackLabels.length">{{fallbackLabels.join('、')}}为示意值</span><span>{{enlarge?'仅显示厚度放大，原始数据不变':'按实际尺寸比例展示'}}；{{record?.[metric]==null?'指标缺失，显示灰色':'颜色不表示表面温度场'}}</span></div>
  </section>
</template>
