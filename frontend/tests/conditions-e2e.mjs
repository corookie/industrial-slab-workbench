import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here=dirname(fileURLToPath(import.meta.url))
const root=resolve(here,'../..')
const base=process.env.WORKBENCH_URL||'http://127.0.0.1:8766'
const baseOrigin=new URL(base).origin
const screens=resolve(root,'docs/screens')
const validationPath=resolve(root,'docs/conditions-validation.json')
const chrome=process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const captureOnly=process.argv.includes('--capture-only')
const errors=[],checks=[]
const expectedPointKeys=['record_id','slab_id','source_row','steel_grade','exit_temp','process_time','rough_thickness','temp_drop','group_index','produced_at'].sort()
const bins=[20,38,42,100]
const mobileCaptureStyle='.topbar { position: static !important; }'

const numberIn=text=>{
 const match=String(text).replace(/,/g,'').match(/-?\d+(?:\.\d+)?/)
 assert.ok(match,`Expected a number in ${JSON.stringify(text)}`)
 return Number(match[0])
}
const closeTo=(actual,expected,field)=>assert.ok(Math.abs(actual-expected)<=.11,`${field}: expected ${expected}, got ${actual}`)
const pointGroup=thickness=>{
 for(let index=0;index<bins.length-1;index++){
  const upper=index===bins.length-2
  if(thickness>=bins[index]&&(thickness<bins[index+1]||(upper&&thickness<=bins[index+1])))return index
 }
 return null
}
const pointTitle=point=>point.slab_id||(point.source_row!=null?`记录 ${point.source_row}`:`记录 ${point.record_id??'—'}`)

const browser=await chromium.launch({
 executablePath:chrome,
 headless:true,
 args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']
})
const context=await browser.newContext({viewport:{width:1600,height:1050},deviceScaleFactor:2,timezoneId:'Asia/Shanghai'})
const page=await context.newPage()
page.on('pageerror',error=>errors.push(error.message))

async function responseJson(action,{method='POST',path}){
 const responsePromise=page.waitForResponse(response=>{
  const url=new URL(response.url())
  return url.origin===baseOrigin&&url.pathname===path&&response.request().method()===method&&response.status()===200
 })
 await action()
 return (await responsePromise).json()
}

async function waitForScene(scene,analysisId){
 await scene.waitFor({state:'visible'})
 await page.waitForFunction(({selector,id})=>document.querySelector(selector)?.getAttribute('data-analysis-id')===id,{selector:'.condition-scene',id:analysisId})
}

async function expandNewExperiment(analysisId){
 const toggle=page.getByRole('button',{name:'展开三维工况',exact:true})
 await toggle.waitFor({state:'visible'})
 assert.equal(await toggle.getAttribute('aria-expanded'),'false','新实验应默认折叠三维工况')
 assert.equal(await page.locator('.condition-scene').count(),0,'折叠状态不挂载三维场景')
 assert.equal(await page.locator('.analysis-figure').isVisible(),true,'默认直接展示科研图组')
 await toggle.click()
 assert.equal(await page.getByRole('button',{name:'收起三维工况',exact:true}).getAttribute('aria-expanded'),'true')
 await waitForScene(page.locator('.condition-scene'),analysisId)
}

async function conditionsFor(analysisId){
 const response=await page.request.get(`${base}/api/analyses/${encodeURIComponent(analysisId)}/conditions`)
 assert.equal(response.status(),200,'工况点接口应可读取已保存分析快照')
 return response.json()
}

async function assertSelectionDetails(selection,point){
 const selectionText=await selection.textContent()
 assert.ok(selectionText.includes(`记录标识：${point.record_id}`))
 assert.ok(selectionText.includes(point.steel_grade))
 assert.ok(selectionText.includes(point.source_row==null?'来源行 —':`来源行 ${point.source_row}`))
 if(point.slab_id!=null)assert.ok((await selection.locator('h4').textContent()).includes(point.slab_id))
 for(const [field,testId] of Object.entries({exit_temp:'condition-selected-exit-temp',process_time:'condition-selected-process-time',rough_thickness:'condition-selected-rough-thickness',temp_drop:'condition-selected-temp-drop'})){
  closeTo(numberIn(await selection.getByTestId(testId).textContent()),point[field],field)
 }
}

async function waitForAnimationFrames(){
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))
}

async function assertCanvasSizing(canvas){
 const sizing=await canvas.evaluate(node=>{
  const canvasBox=node.getBoundingClientRect()
  const hostBox=node.parentElement?.getBoundingClientRect()
  return {
   cssWidth:canvasBox.width,
   cssHeight:canvasBox.height,
   hostWidth:hostBox?.width,
   hostHeight:hostBox?.height,
   bufferWidth:node.width,
   bufferHeight:node.height,
   devicePixelRatio:window.devicePixelRatio
  }
 })
 assert.equal(sizing.devicePixelRatio,2,'专项场景应在 DPR 2 下验证')
 assert.ok(Math.abs(sizing.cssWidth-sizing.hostWidth)<=1&&Math.abs(sizing.cssHeight-sizing.hostHeight)<=1,'canvas CSS 尺寸应与场景宿主一致')
 assert.ok(Math.abs(sizing.bufferWidth-sizing.cssWidth*2)<=3&&Math.abs(sizing.bufferHeight-sizing.cssHeight*2)<=3,'DPR 2 下 canvas 绘图缓冲区应约为 CSS 尺寸两倍')
}

async function hoverAndSelectCanvasPoint(scene,canvas,points){
 await canvas.scrollIntoViewIfNeeded()
 const box=await canvas.boundingBox()
 assert.ok(box?.width>0&&box?.height>0,'工况 canvas 应有可点击面积')
 const tooltip=scene.locator('.point-tooltip')
 const grids=[
  {columns:6,rows:8,left:.28,right:.72,top:.2,bottom:.82},
  {columns:18,rows:20,left:.28,right:.72,top:.2,bottom:.82}
 ]
 for(const grid of grids){
  for(let row=0;row<grid.rows;row++){
   for(let column=0;column<grid.columns;column++){
    const x=box.x+box.width*(grid.left+(grid.right-grid.left)*((column+.5)/grid.columns))
    const y=box.y+box.height*(grid.top+(grid.bottom-grid.top)*((row+.5)/grid.rows))
    await page.mouse.move(x,y)
    await waitForAnimationFrames()
    if(!await tooltip.isVisible())continue
    const hoverTitle=(await tooltip.locator('strong').textContent()).trim()
    await page.mouse.click(x,y)
    await waitForAnimationFrames()
    const selectedId=await scene.getAttribute('data-selected-id')
    const point=points.find(candidate=>candidate.record_id===selectedId)
    assert.ok(point,'画布点击应选择工况接口中存在的记录')
    assert.equal(hoverTitle,pointTitle(point),'悬停标题与点击选择的记录应一致')
    return point
   }
  }
 }
 throw new Error('未在中心 6 × 8 网格及密集回退网格内命中可悬停的工况点')
}

function assertConditionsSnapshot(snapshot,analysis,dataset){
 assert.equal(snapshot.analysis_id,analysis.id)
 assert.equal(snapshot.dataset_id,dataset.id)
 assert.equal(snapshot.samples_sha256,analysis.samples_sha256)
 assert.equal(snapshot.source_kind,'sanitized')
 assert.equal(snapshot.counts.analyzed,analysis.counts.analyzed)
 assert.equal(snapshot.counts.eligible+snapshot.counts.missing_coordinates,snapshot.counts.analyzed)
 assert.equal(snapshot.counts.rendered,snapshot.points.length)
 assert.ok(snapshot.counts.rendered>0,'G01 指定工况应有可渲染样本')
 assert.ok(snapshot.counts.rendered<=snapshot.counts.eligible)
 assert.ok(Array.isArray(snapshot.conditions)&&snapshot.conditions.some(condition=>condition.includes('G01')))
 assert.ok(snapshot.sampling,'接口应说明取点策略')
 for(const field of ['exit_temp','process_time','rough_thickness']){
  const bound=snapshot.bounds?.[field]
  assert.ok(Number.isFinite(bound?.min)&&Number.isFinite(bound?.max)&&bound.min<=bound.max,`${field} 坐标范围应完整`)
 }
 assert.ok(Number.isFinite(snapshot.color_scale?.min)&&Number.isFinite(snapshot.color_scale?.max)&&snapshot.color_scale.min<=snapshot.color_scale.max,'温降色标范围应完整')
 for(const point of snapshot.points){
  assert.deepEqual(Object.keys(point).sort(),expectedPointKeys,'公开工况点仅返回约定字段')
  assert.ok(typeof point.record_id==='string'&&point.record_id.length>0)
  assert.ok(point.source_row==null||Number.isFinite(Number(point.source_row)))
  assert.ok(typeof point.steel_grade==='string'&&point.steel_grade.length>0)
  for(const field of ['exit_temp','process_time','rough_thickness','temp_drop']){
   assert.ok(Number.isFinite(point[field]),`${field} 应为有限数值`)
  }
  assert.equal(point.group_index,pointGroup(point.rough_thickness),'工况点厚度分组应与保存边界一致')
  assert.ok(point.exit_temp>=snapshot.bounds.exit_temp.min&&point.exit_temp<=snapshot.bounds.exit_temp.max)
  assert.ok(point.process_time>=snapshot.bounds.process_time.min&&point.process_time<=snapshot.bounds.process_time.max)
  assert.ok(point.rough_thickness>=snapshot.bounds.rough_thickness.min&&point.rough_thickness<=snapshot.bounds.rough_thickness.max)
 }
}

async function run(){
try{
 await page.goto(base,{waitUntil:'domcontentloaded'})
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'数据工作台',exact:true}).click()
 await page.getByTestId('sample-count').waitFor()
 const healthResponse=await page.request.get(`${base}/api/health`)
 assert.equal(healthResponse.status(),200)
 const health=await healthResponse.json()
 assert.equal(health.mode,'public_demo','conditions 验证仅能在公开演示模式运行')
 const datasetsResponse=await page.request.get(`${base}/api/datasets`)
 assert.equal(datasetsResponse.status(),200)
 const datasets=await datasetsResponse.json()
 assert.equal(datasets.length,1)
 const dataset=datasets[0]
 assert.equal(dataset.source_kind,'sanitized')
 assert.ok(datasets.every(item=>item.source_kind!=='real'),'公开模式不得暴露原始数据集')
 await mkdir(screens,{recursive:true})

 if(captureOnly){
  const historyResponse=await page.request.get(`${base}/api/analyses?dataset_id=${encodeURIComponent(dataset.id)}`)
  assert.equal(historyResponse.status(),200)
  const history=await historyResponse.json()
  const saved=history.find(item=>item.source_kind==='sanitized')
  assert.ok(saved,'公开演示模式需要已有脱敏分析快照以刷新场景截图')
  await page.getByRole('button',{name:'分析实验',exact:true}).click()
  await page.getByLabel('分析历史',{exact:true}).waitFor()
  await page.waitForFunction(id=>[...document.querySelector('[aria-label="分析历史"]')?.options||[]].some(option=>option.value===id),saved.id)
  await page.getByLabel('分析历史',{exact:true}).selectOption(saved.id)
  const scene=page.locator('.condition-scene')
  await page.getByRole('button',{name:'展开三维工况',exact:true}).waitFor({state:'visible'})
  await page.locator('.report-panel .report-title').screenshot({path:resolve(screens,'conditions-toggle.png'),style:mobileCaptureStyle})
  await expandNewExperiment(saved.id)
  const canvas=scene.locator('.condition-canvas-host canvas')
  await canvas.waitFor({state:'visible'})
  await assertCanvasSizing(canvas)
  await canvas.scrollIntoViewIfNeeded()
  await waitForAnimationFrames()
  await scene.screenshot({path:resolve(screens,'conditions.png')})
  await page.setViewportSize({width:390,height:844})
  await scene.scrollIntoViewIfNeeded()
  await waitForAnimationFrames()
  await scene.screenshot({path:resolve(screens,'conditions-mobile.png'),style:mobileCaptureStyle})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'390px 宽度不应出现横向溢出')
  assert.deepEqual(errors,[],'浏览器不应出现 JavaScript 错误')
  console.log(JSON.stringify({analysis_id:saved.id,capture_only:true,screens:['conditions.png','conditions-mobile.png'],errors},null,2))
  return
 }

 await page.getByRole('button',{name:'分析实验',exact:true}).click()
 await page.getByLabel('分析钢种',{exact:true}).selectOption('G01')
 await page.getByLabel('分组边界',{exact:true}).fill('20, 38, 42, 100')
 await page.getByLabel('控制出炉温度下限',{exact:true}).fill('1100')
 await page.getByLabel('控制出炉温度上限',{exact:true}).fill('1300')
 const processControl=page.locator('.control-item').filter({hasText:'粗轧过程时间'}).locator('input[type="checkbox"]')
 if(await processControl.count()){
  if(!await processControl.isChecked())await processControl.check()
 }
 await page.getByLabel('控制粗轧过程时间下限',{exact:true}).fill('180')
 await page.getByLabel('控制粗轧过程时间上限',{exact:true}).fill('240')
 const first=await responseJson(
  ()=>page.getByRole('button',{name:'运行分析',exact:true}).click(),
  {path:`/api/datasets/${encodeURIComponent(dataset.id)}/analyses`}
 )
 assert.equal(first.source_kind,'sanitized')
 assert.deepEqual(first.parameters.bins,bins)
 assert.deepEqual(first.parameters.controls.exit_temp,[1100,1300])
 assert.deepEqual(first.parameters.controls.process_time,[180,240])
 const firstConditions=await conditionsFor(first.id)
 assertConditionsSnapshot(firstConditions,first,dataset)
 const scene=page.locator('.condition-scene')
 await page.getByRole('button',{name:'展开三维工况',exact:true}).waitFor({state:'visible'})
 await page.locator('.analysis-figure').waitFor({state:'visible'})
 await page.locator('.analysis-figure').evaluate(node=>node.decode())
 await page.locator('.report-panel .report-title').screenshot({path:resolve(screens,'conditions-toggle.png'),style:mobileCaptureStyle})
 await page.locator('.report-panel').screenshot({path:resolve(screens,'conditions-collapsed.png'),style:mobileCaptureStyle})
 await expandNewExperiment(first.id)
 assert.equal(Number(await scene.getAttribute('data-rendered-n')),firstConditions.counts.rendered)
 const canvas=scene.locator('.condition-canvas-host canvas')
 await canvas.waitFor({state:'visible'})
 await assertCanvasSizing(canvas)
 assert.equal(await canvas.evaluate(node=>{
  const box=node.getBoundingClientRect()
  return node.width>0&&node.height>0&&box.width>0&&box.height>0&&Boolean(node.getContext('webgl2')||node.getContext('webgl'))
 }),true,'工况场景应创建可用的 WebGL canvas')
 for(const [name,view] of [['从 X 轴正视','x'],['从 Y 轴正视','y'],['从 Z 轴正视','z']]){
  await scene.getByRole('button',{name,exact:true}).click()
  await page.waitForFunction(({selector,view})=>document.querySelector(selector)?.getAttribute('data-camera-view')===view,{selector:'.condition-scene',view})
 }
 await scene.getByRole('button',{name:'重置三维工况视角',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('.condition-scene')?.getAttribute('data-camera-view')==='perspective')
 checks.push('G01 分析快照的公开工况接口、分组、坐标范围和温降色标一致；DPR 2 下 Three.js canvas CSS/缓冲区尺寸一致，三轴正视/重置可用')

 let selectedPoint=firstConditions.points.find(point=>point.slab_id&&point.source_row!=null)||firstConditions.points[0]
 const search=scene.getByLabel('搜索三维样本',{exact:true})
 await search.fill(selectedPoint.record_id)
 await search.press('Enter')
 await page.waitForFunction(({selector,id})=>document.querySelector(selector)?.getAttribute('data-selected-id')===id,{selector:'.condition-scene',id:selectedPoint.record_id})
 const selection=scene.locator('.condition-selection')
 await selection.waitFor({state:'visible'})
 await assertSelectionDetails(selection,selectedPoint)
 await page.getByRole('button',{name:'收起三维工况',exact:true}).click()
 assert.equal(await scene.count(),0,'收起后释放三维场景')
 await expandNewExperiment(first.id)
 assert.equal(await scene.getAttribute('data-selected-id'),selectedPoint.record_id,'同一实验收起再展开应保留选中记录')
 await assertSelectionDetails(selection,selectedPoint)
 checks.push('分析结果标题右侧按钮默认折叠，科研图组直接可见；展开/收起状态正确，重新展开保留已选记录')
 selectedPoint=await hoverAndSelectCanvasPoint(scene,canvas,firstConditions.points)
 await assertSelectionDetails(selection,selectedPoint)
 const locate=scene.getByRole('button',{name:'在记录表中查看',exact:true})
 assert.equal(await locate.isDisabled(),false)
 await locate.click()
 await page.waitForFunction(id=>document.querySelector('.record-details')?.getAttribute('data-selected-id')===id,selectedPoint.record_id)
 await page.waitForFunction(id=>[...document.querySelectorAll('.records-panel tbody tr[data-id]')].some(row=>row.dataset.id===id&&row.getAttribute('aria-selected')==='true'),selectedPoint.record_id)
 await page.getByRole('button',{name:'分析实验',exact:true}).click()
 await waitForScene(scene,first.id)
 assert.equal(await scene.getAttribute('data-selected-id'),selectedPoint.record_id)
 checks.push('键盘搜索/Enter 与 canvas 实际悬停点击均能选点；详情与接口点值一致，且可定位到工作台中同一记录并返回分析结果')
 await scene.locator('.condition-canvas-host canvas').waitFor({state:'visible'})
 await scene.screenshot({path:resolve(screens,'conditions.png')})

 const savedAnalysisId=first.id
 await page.getByLabel('控制粗轧过程时间下限',{exact:true}).fill('181')
 assert.equal(await scene.getAttribute('data-analysis-id'),savedAnalysisId,'编辑实验草稿不得改写已保存场景')
 assert.equal(await locate.isDisabled(),false)
 await page.getByTestId('experiment-draft-notice').waitFor({state:'visible'})
 const second=await responseJson(
  ()=>page.getByRole('button',{name:'运行分析',exact:true}).click(),
  {path:`/api/datasets/${encodeURIComponent(dataset.id)}/analyses`}
 )
 assert.notEqual(second.id,savedAnalysisId,'再次运行应保存新实验快照')
 assert.equal(second.parameters.controls.process_time[0],181)
 await expandNewExperiment(second.id)
 const secondConditions=await conditionsFor(second.id)
 assertConditionsSnapshot(secondConditions,second,dataset)
 assert.equal(Number(await scene.getAttribute('data-rendered-n')),secondConditions.counts.rendered)
 const rerun=await responseJson(
  ()=>page.getByRole('button',{name:'按保存参数复现',exact:true}).click(),
  {path:`/api/analyses/${encodeURIComponent(second.id)}/rerun`}
 )
 assert.equal(rerun.samples_sha256,second.samples_sha256,'复现应使用相同分析样本快照')
 await expandNewExperiment(rerun.id)
 const rerunConditions=await conditionsFor(rerun.id)
 assertConditionsSnapshot(rerunConditions,rerun,dataset)
 assert.equal(rerunConditions.samples_sha256,secondConditions.samples_sha256)
 const rerunPoint=rerunConditions.points.find(point=>point.record_id===selectedPoint.record_id)||rerunConditions.points[0]
 const rerunSearch=scene.getByLabel('搜索三维样本',{exact:true})
 await rerunSearch.fill(rerunPoint.record_id)
 await rerunSearch.press('Enter')
 await page.waitForFunction(({selector,id})=>document.querySelector(selector)?.getAttribute('data-selected-id')===id,{selector:'.condition-scene',id:rerunPoint.record_id})
 const rerunLocate=scene.getByRole('button',{name:'在记录表中查看',exact:true})
 assert.equal(await rerunLocate.isDisabled(),false)
 checks.push('修改实验控制条件只更新草稿；运行后切换到新快照，按保存参数复现保持样本 SHA 一致')

 await page.getByLabel('分析历史',{exact:true}).selectOption(first.id)
 await page.getByRole('button',{name:'展开三维工况',exact:true}).waitFor({state:'visible'})
 assert.equal(await scene.count(),0,'切换历史实验应恢复折叠')
 await page.getByLabel('分析历史',{exact:true}).selectOption(rerun.id)
 await expandNewExperiment(rerun.id)
 await rerunSearch.fill(rerunPoint.record_id)
 await rerunSearch.press('Enter')
 checks.push('重新运行、按保存参数复现、切换历史实验均恢复三维折叠状态')

 await page.getByLabel('筛选钢种',{exact:true}).selectOption('G02')
 await responseJson(
  ()=>page.getByRole('button',{name:'应用筛选',exact:true}).click(),
  {path:`/api/datasets/${encodeURIComponent(dataset.id)}/query`}
 )
 await waitForScene(scene,rerun.id)
 assert.equal(Number(await scene.getAttribute('data-rendered-n')),rerunConditions.counts.rendered,'顶部筛选改变后历史场景仍使用保存快照')
 assert.equal(await rerunLocate.isDisabled(),true,'当前工作台范围与保存分析不一致时不得定位记录')
 assert.equal(await rerunLocate.getAttribute('aria-describedby'),'condition-locate-note')
 await page.locator('#condition-locate-note').waitFor({state:'visible'})
 checks.push('顶部筛选变化后，历史工况点仍保留原分析范围，并禁用跨范围的记录定位')

 await page.setViewportSize({width:390,height:844})
 await page.getByRole('button',{name:'收起三维工况',exact:true}).click()
 await page.locator('.report-panel .report-title').screenshot({path:resolve(screens,'conditions-collapsed-mobile.png'),style:mobileCaptureStyle})
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'折叠状态的手机标题与按钮不应横向溢出')
 await expandNewExperiment(rerun.id)
 await scene.scrollIntoViewIfNeeded()
 await scene.screenshot({path:resolve(screens,'conditions-mobile.png'),style:mobileCaptureStyle})
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'390px 宽度不应出现横向溢出')
 assert.deepEqual(errors,[],'浏览器不应出现 JavaScript 错误')
 const validation={
  mode:health.mode,
  dataset_id:dataset.id,
  analysis_id:rerun.id,
  samples_sha256:rerun.samples_sha256,
  counts:rerunConditions.counts,
  conditions:rerunConditions.conditions,
  checks,
  errors
 }
 await writeFile(validationPath,JSON.stringify(validation,null,2))
 console.log(JSON.stringify({analysis_id:rerun.id,checks,errors},null,2))
}finally{
 await context.close()
 await browser.close()
}
}

await run()
