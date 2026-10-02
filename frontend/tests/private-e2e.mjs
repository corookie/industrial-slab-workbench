import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const base=process.env.WORKBENCH_URL||'http://127.0.0.1:8765'
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']})
const page=await browser.newPage({viewport:{width:1600,height:1050}})
const errors=[]
page.on('pageerror',error=>errors.push(error.message))
async function checkRealSourceDetails(){
 assert.equal(await page.getByTestId('real-data-notice').isVisible(),false)
 await page.getByText('数据质量与字段',{exact:true}).click()
 await page.getByTestId('real-data-notice').waitFor()
 await page.getByText('数据质量与字段',{exact:true}).click()
}
try{
 await page.goto(base)
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'数据工作台',exact:true}).click()
 await page.getByTestId('sample-count').waitFor()
 const health=await (await page.request.get(base+'/api/health')).json()
 assert.equal(health.mode,'private_local')
 const datasets=await (await page.request.get(base+'/api/datasets')).json()
 const real=datasets.find(d=>d.selection?.kind==='top_five_original')
 const demo=datasets.find(d=>d.source_kind==='sanitized')
 assert.ok(real&&demo)
 assert.ok(datasets.length>=2,'原始前五与脱敏副本应同时可用，允许另行上传的数据集')
 assert.equal(real.grades.length,5)
 assert.equal(await page.getByLabel('当前数据集',{exact:true}).inputValue(),real.id)
 await checkRealSourceDetails()
 assert.equal(await page.getByLabel('筛选钢种',{exact:true}).locator('option').count(),6)
 assert.equal(Number((await page.getByTestId('sample-count').textContent()).replaceAll(',','')),real.rows-real.quality.invalid_rows)
 const q=await (await page.request.post(base+`/api/datasets/${real.id}/query`,{data:{}})).json()
 assert.equal(q.total,q.grades.reduce((n,g)=>n+g.value,0))
 assert.equal(q.total,q.histograms.temp_drop.valid_n)
 assert.ok(q.scatter.every(p=>real.selection.grades.includes(p[3])))
 const row=q.records[1]
 await page.locator(`tr[data-id="${row.record_id}"]`).click()
 await page.locator(`.record-details[data-selected-id="${row.record_id}"]`).waitFor()
 await page.getByRole('button',{name:'查看三维示意',exact:true}).click()
 assert.equal(await page.locator('.slab-visual').getAttribute('data-record-id'),row.record_id)
 assert.equal(Number(await page.locator('.slab-visual').getAttribute('data-length')),row.length)
 await page.getByLabel('当前数据集',{exact:true}).selectOption(demo.id)
 await page.getByTestId('privacy-notice').waitFor()
 await page.waitForFunction(()=>document.querySelector('[data-testid="sample-count"]')?.textContent.replaceAll(',','')==='10000')
 await page.getByLabel('当前数据集',{exact:true}).selectOption(real.id)
 await checkRealSourceDetails()
 await page.waitForFunction(n=>document.querySelector('[data-testid="sample-count"]')?.textContent.replaceAll(',','')===String(n),real.rows-real.quality.invalid_rows)
 assert.deepEqual(errors,[])
 console.log(JSON.stringify({mode:health.mode,datasets:datasets.length,original_grades:real.grades.length,rows:real.rows,valid_rows:q.total,checks:['原始前五与脱敏副本同时出现在下拉列表','初始计数、图表、表格及三维一致','两份数据可以切换且标识正确'],errors},null,2))
}finally{await browser.close()}
