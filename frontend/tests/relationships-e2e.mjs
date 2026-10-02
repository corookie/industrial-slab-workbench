import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {resolve} from 'node:path'
import {writeFile,mkdir} from 'node:fs/promises'
import {ANALYSIS_VARIABLES,EFFECT_STEPS} from '../src/analysis-options.js'
const base=process.env.WORKBENCH_URL||'http://127.0.0.1:8766',root=resolve('..'),screens=resolve(root,'docs/screens')
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
const context=await browser.newContext({viewport:{width:1600,height:1050},timezoneId:'Asia/Shanghai'})
const page=await context.newPage(),errors=[],checks=[]
page.on('pageerror',e=>errors.push(e.message))
async function run(){
 const response=page.waitForResponse(r=>r.url().endsWith('/analyses')&&r.request().method()==='POST')
 await page.getByRole('button',{name:'运行分析',exact:true}).click()
 const r=await response
 assert.equal(r.status(),200,await r.text())
 const result=await r.json()
 await page.locator(`.report-panel[data-analysis-id="${result.id}"]`).waitFor()
 return result
}
try{
 await mkdir(screens,{recursive:true})
 await page.goto(base)
 assert.equal((await (await page.request.get(base+'/api/health')).json()).mode,'public_demo')
 const [dataset]=await (await page.request.get(base+'/api/datasets')).json()
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'分析实验',exact:true}).click()
 await page.getByLabel('分析钢种',{exact:true}).selectOption('G01')
 const variables=await page.getByLabel('分析变量',{exact:true}).locator('option').evaluateAll(nodes=>nodes.map(n=>n.value))
 assert.deepEqual(variables,ANALYSIS_VARIABLES.filter(k=>dataset.available.includes(k)))
 assert.ok(variables.includes('process_time')&&variables.includes('exit_temp')&&variables.includes('furnace_time'))
 let first
 for(const variable of ['rough_thickness','process_time','exit_temp']){
  await page.getByLabel('分析变量',{exact:true}).selectOption(variable)
  if(variable!=='rough_thickness'){
   await page.getByRole('heading',{name:'请运行所选变量的分析'}).waitFor()
   assert.equal(await page.locator('.report-panel').count(),0)
  }
  assert.equal(Number(await page.getByLabel('量化增量',{exact:true}).inputValue()),EFFECT_STEPS[variable])
  if(variable!=='exit_temp'){
   await page.getByLabel('控制出炉温度下限',{exact:true}).fill('1000')
   await page.getByLabel('控制出炉温度上限',{exact:true}).fill('1400')
  }
  if(variable!=='process_time'){
   await page.getByLabel('控制粗轧过程时间下限',{exact:true}).fill('100')
   await page.getByLabel('控制粗轧过程时间上限',{exact:true}).fill('600')
  }
  const b=dataset.bounds[variable]
  await page.getByLabel('分组边界',{exact:true}).fill([b.min,(b.min+b.max)/2,b.max].join(','))
  const result=await run()
  assert.equal(result.parameters.variable,variable)
  assert.equal(result.counts.analyzed,result.groups.reduce((n,g)=>n+g.n,0))
  assert.ok(result.relationships.n<=result.counts.analyzed)
  const card=page.getByTestId('relationship-summary')
  const primary=result.relationships.rows.find(row=>row.field===variable)
  assert.ok(primary)
  assert.equal(await card.getByRole('heading',{name:'结论',exact:true}).count(),1)
  assert.equal(await card.locator('table').count(),0)
  assert.equal(await card.getByTestId('relationship-conclusion').textContent(),result.relationships.explanation.replace('校正表中其他变量后','同时考虑本次其他变量后'))
  assert.ok((await card.textContent()).includes(primary.label))
  if(primary.ci95_low!=null){
   assert.ok((await card.textContent()).includes(`${Math.round(primary.ci95_low*100)/100}`))
  }
  const order=await page.locator('.report-panel').evaluate(panel=>[
   [...panel.querySelectorAll('h3')].find(node=>node.textContent==='分组统计与工况检查'),
   panel.querySelector('[data-testid="relationship-summary"]')
  ].map(node=>[...panel.querySelectorAll('*')].indexOf(node)))
  assert.ok(order[0]>=0&&order[1]>order[0])
  const conditions=await (await page.request.get(base+`/api/analyses/${result.id}/conditions`)).json()
  assert.equal(conditions.counts.analyzed,result.counts.analyzed)
  const report=await (await page.request.get(base+result.artifacts['report.html'])).text()
  assert.ok(report.includes('变量与温降的数值关系')&&report.includes('脱敏合成'))
  assert.equal((await page.request.get(base+result.artifacts['relationships.csv'])).status(),200)
  assert.equal(await page.getByRole('link',{name:'下载全部变量关系分析'}).count(),1)
  if(variable==='rough_thickness'){
   first=result
   await page.getByTestId('relationship-summary').screenshot({path:resolve(screens,'relationships-table.png')})
   await page.screenshot({path:resolve(screens,'relationships-desktop.png'),fullPage:true})
  }
  if(variable==='process_time')await page.screenshot({path:resolve(screens,'relationships-time.png'),fullPage:true})
  if(variable==='exit_temp'){
   await page.getByText('查看所选变量的校正关系与残差图',{exact:true}).click()
   await page.locator('.relationship-figure').evaluate(img=>img.decode())
   const img=await page.request.get(base+result.artifacts['relationship.png'])
   await writeFile(resolve(screens,'relationships-figure.png'),await img.body())
  }
 }
 checks.push('分析变量包括粗轧时间、出炉温度与其他已有工况；三种变量运行成功，单位和增量随变量更新')
 const before=await page.getByTestId('relationship-conclusion').textContent()
 await page.getByLabel('量化增量',{exact:true}).fill('5')
 await page.getByTestId('experiment-draft-notice').waitFor()
 assert.equal(await page.getByTestId('relationship-conclusion').textContent(),before)
 await page.getByLabel('分析历史',{exact:true}).selectOption(first.id)
 assert.equal(await page.getByLabel('分析变量',{exact:true}).inputValue(),'rough_thickness')
 const rerunResponse=page.waitForResponse(r=>r.url().endsWith('/rerun')&&r.request().method()==='POST')
 await page.getByRole('button',{name:'按保存参数复现',exact:true}).click()
 const again=await (await rerunResponse).json()
 assert.deepEqual(again.relationships,first.relationships)
 const download=page.waitForEvent('download')
 await page.getByRole('link',{name:'关系表 CSV',exact:true}).click()
 assert.equal((await download).suggestedFilename(),'relationships.csv')
 const reportDownload=page.waitForEvent('download')
 await page.getByRole('link',{name:'下载全部变量关系分析'}).click()
 assert.equal((await reportDownload).suggestedFilename(),'report.html')
 checks.push('分组图在前、单变量结论在后；结论与 API 数值一致，完整多变量分析可下载；历史参数复现一致')
 await page.setViewportSize({width:390,height:844})
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
 await page.screenshot({path:resolve(screens,'relationships-mobile.png'),fullPage:true})
 checks.push('390px 手机布局无整页横向溢出')
 assert.deepEqual(errors,[])
 await writeFile(resolve(root,'docs/relationships-validation.json'),JSON.stringify({mode:'public_demo',checks,errors},null,2))
 console.log(JSON.stringify({checks,errors},null,2))
}finally{await browser.close()}
