import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const base=process.env.WORKBENCH_URL||'http://127.0.0.1:8766'
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']})
const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[],checks=[]
page.on('pageerror',error=>errors.push(error.message))
let queries=0
page.on('request',r=>{if(r.url().endsWith('/query'))queries++})
async function post(action){
 const response=page.waitForResponse(r=>r.url().endsWith('/query')&&r.request().method()==='POST'&&r.status()===200)
 await action();const data=await(await response).json()
 await page.waitForFunction(n=>document.querySelector('.page-position')?.textContent.trim().startsWith(n+' /'),data.page)
 return data
}
async function jump(number,enter=false){
 await page.getByLabel('跳转页码',{exact:true}).fill(String(number))
 return post(()=>enter?page.getByLabel('跳转页码',{exact:true}).press('Enter'):page.getByRole('button',{name:'跳转',exact:true}).click())
}
try{
 await page.goto(base)
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'数据工作台',exact:true}).click()
 await page.getByTestId('sample-count').waitFor()
 assert.equal((await(await page.request.get(base+'/api/health')).json()).mode,'public_demo')
 const meta=(await(await page.request.get(base+'/api/datasets')).json())[0]
 assert.equal(await page.locator('.filters-sidebar').count(),0)
 const filters=await page.getByRole('form',{name:'顶部样本筛选'}).boundingBox()
 const charts=await page.locator('.overview-charts').boundingBox()
 assert.ok(filters.width>1200&&filters.y+filters.height<charts.y)
 const boxes=await page.locator('.overview-charts>.panel').evaluateAll(nodes=>nodes.map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,height:b.height}}))
 assert.equal(boxes.length,3)
 assert.ok(boxes.every(b=>Math.abs(b.y-boxes[0].y)<1&&Math.abs(b.height-boxes[0].height)<1),'三图同一行、卡片同高')
 assert.ok(boxes[0].x<boxes[1].x&&boxes[1].x<boxes[2].x)
 await page.waitForFunction(()=>document.querySelectorAll('.chart canvas').length===3)
 await page.locator('.charts-section').screenshot({path:resolve('../docs/screens/charts-single-row.png')})
 checks.push('钢种、数值与变量关系三图在桌面端同一行、卡片同高')
 assert.equal(await page.locator('#advanced-filters').isVisible(),false)
 assert.equal(await page.locator('.slab-visual').count(),0)
 checks.push('常用条件与可折叠高级筛选位于页面顶部；三维默认收起')
 const twelfth=await jump(12)
 assert.equal(twelfth.page,12)
 await page.locator(`.records-panel tbody tr[data-id="${twelfth.records[0].record_id}"]`).waitFor()
 assert.equal((await page.locator('.records-panel tbody tr').first().getAttribute('data-id')),twelfth.records[0].record_id)
 assert.equal((await jump(3,true)).page,3)
 await page.route('**/query',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({detail:'跳页测试：请求暂时失败'})}),{times:1})
 await page.getByLabel('跳转页码',{exact:true}).fill('4')
 await page.getByRole('button',{name:'跳转',exact:true}).click()
 await page.getByRole('alert').filter({hasText:'请求暂时失败'}).waitFor()
 assert.ok((await page.locator('.page-position').textContent()).startsWith('3 /'))
 assert.equal(await page.getByLabel('跳转页码',{exact:true}).inputValue(),'3')
 await page.getByRole('button',{name:'关闭错误信息'}).click()
 for(const bad of ['0','1.5','9999','abc']){
  const before=queries
  await page.getByLabel('跳转页码',{exact:true}).fill(bad)
  await page.getByRole('button',{name:'跳转',exact:true}).click()
  await page.locator('.page-error').waitFor()
  assert.match(await page.locator('.page-error').textContent(),/整数页码/)
  assert.equal(queries,before)
  assert.ok((await page.locator('.page-position').textContent()).startsWith('3 /'))
 }
 const last=await jump(Math.ceil(meta.rows/30))
 assert.equal(last.records.length,meta.rows%30||30)
 assert.equal(await page.getByRole('button',{name:'下一页',exact:true}).isDisabled(),true)
 checks.push('按钮/Enter 跳页、实际表格页内容、无效页码、请求失败回退与末页边界验证通过')
 await page.getByRole('button',{name:'高级筛选',exact:true}).click()
 assert.equal(await page.locator('#advanced-filters').isVisible(),true)
 await page.getByLabel('筛选板坯宽度下限').fill(String(meta.bounds.width.max+1))
 const empty=await post(()=>page.getByRole('button',{name:'应用筛选',exact:true}).click())
 assert.equal(empty.total,0)
 assert.equal(await page.getByRole('button',{name:'跳转',exact:true}).isDisabled(),true)
 assert.equal(await page.getByLabel('跳转页码',{exact:true}).inputValue(),'1')
 await post(()=>page.getByRole('button',{name:'重置筛选',exact:true}).click())
 assert.equal(await page.getByLabel('跳转页码',{exact:true}).inputValue(),'1')
 await page.getByRole('button',{name:'收起高级筛选',exact:true}).click()
 await page.getByRole('button',{name:'查看三维示意',exact:true}).click()
 await page.locator('.slab-visual canvas').waitFor()
 await page.getByRole('button',{name:'收起三维示意',exact:true}).click()
 assert.equal(await page.locator('.slab-visual').count(),0)
 checks.push('高级条件仍参与统一筛选；空范围/重置同步页码；三维可以按需展开/收起')
 await page.evaluate(()=>window.scrollTo(0,0))
 await page.screenshot({path:resolve('../docs/screens/workbench.png'),fullPage:true})
 for(const width of [1280,1024,768]){
  await page.setViewportSize({width,height:900})
  await page.waitForFunction(()=>[...document.querySelectorAll('.chart canvas')].every(n=>Math.abs(n.getBoundingClientRect().width-n.closest('.chart').getBoundingClientRect().width)<1))
  const row=await page.locator('.overview-charts>.panel').evaluateAll(nodes=>nodes.map(n=>{const b=n.getBoundingClientRect();return {y:b.y,height:b.height}}))
  assert.ok(row.every(b=>Math.abs(b.y-row[0].y)<1&&Math.abs(b.height-row[0].height)<1),`${width}px 三图仍在同一行且同高`)
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
 }
 checks.push('1280 / 1024 / 768px 三图并排，画布随卡片调整；390px 无整页横向溢出')
 await page.setViewportSize({width:390,height:844})
 await page.evaluate(()=>window.scrollTo(0,0))
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
 await page.screenshot({path:resolve('../docs/screens/mobile.png'),fullPage:true})
 assert.deepEqual(errors,[])
 await writeFile(resolve('../docs/layout-validation.json'),JSON.stringify({checks,errors},null,2))
 console.log(JSON.stringify({checks,errors},null,2))
}finally{await browser.close()}
