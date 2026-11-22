// Optional browser QA; NODE_PATH must point to a Playwright installation.
const {chromium}=require('playwright');
const path=require('path');
const {pathToFileURL}=require('url');
const fs=require('fs');
(async()=>{
  const input=path.resolve(process.argv[2]);
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page=await browser.newPage({viewport:{width:1250,height:1100}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(input).href);
    const count=await page.locator('#select option').count();
    if(count<1)throw Error('No selectable walls');
    await page.selectOption('#select','W03');
    const info=await page.locator('#info').innerText();
    const cmd=await page.locator('#cmd').textContent();
    if(!info.includes('W03')||!cmd.includes('--wall W03'))throw Error('Selection does not update');
    if(!cmd.startsWith('.\\run_local.ps1 '))throw Error('Invalid copied PowerShell command: '+JSON.stringify(cmd));
    await page.locator('#rows tr').first().click();
    if(await page.locator('#select').inputValue()!=='W01')throw Error('Table selection does not update');
    if(errors.length)throw Error(errors.join('\n'));
    await page.screenshot({path:path.join(path.dirname(input),'viewer_qa.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2))throw Error('Mobile horizontal overflow');
    const result={wall_options:count,selection_checked:true,command_checked:true,page_errors:errors,mobile_overflow:false};
    fs.writeFileSync(path.join(path.dirname(input),'viewer_qa.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
