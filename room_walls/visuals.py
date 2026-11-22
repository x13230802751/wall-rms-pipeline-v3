# 生成墙面识别预览、测量偏差图和离线交互查看页面。
"""Local review artifacts, no CDN, no data upload, no fabricated unseen points."""
import json
import os
from pathlib import Path
import numpy as np
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.mplcache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS=['#2677c9','#e66a2c','#1a9977','#a34bc0','#cb3659','#8d6f3f','#577ca8','#6f9634']


def sample_ids(ids,n):return ids[::max(1,int(np.ceil(len(ids)/n)))]


def horizontal_frame(up):
    up=np.array(up);axis=np.eye(3)[np.argmin(np.abs(up))]
    u=np.cross(axis,up);u/=np.linalg.norm(u);v=np.cross(up,u)
    return np.stack([u,v],axis=1)


def catalog_plots(points,result,out):
    finite=np.flatnonzero(np.isfinite(points).all(1));bg=sample_ids(finite,25000)
    basis=horizontal_frame(result['config']['up']);xy=points[bg]@basis
    fig,ax=plt.subplots(figsize=(9,8));ax.scatter(xy[:,0],xy[:,1],c='#cccccc',s=.35)
    for j,w in enumerate(result['walls']):
        s=points[sample_ids(w['expanded_indices'],15000)]@basis;c=np.array(w['plane_center_m'])@basis
        ax.scatter(s[:,0],s[:,1],s=.65,c=COLORS[j%len(COLORS)])
        ax.text(*c,w['id'],bbox=dict(facecolor='white',alpha=.85,edgecolor='none'),fontsize=11)
    ax.set_aspect('equal');ax.set_xlabel('Horizontal U (m)');ax.set_ylabel('Horizontal V (m)')
    ax.set_title('Candidate wall IDs - review before selecting\n'+result['mode'])
    fig.tight_layout();fig.savefig(out/'overview.png',dpi=160);plt.close(fig)
    cols=2;rows=int(np.ceil(len(result['walls'])/cols));fig,axs=plt.subplots(rows,cols,figsize=(12,4.5*rows),squeeze=False)
    for j,w in enumerate(result['walls']):
        ax=axs.flat[j];p=points[sample_ids(w['expanded_indices'],20000)]-np.array(w['plane_center_m'])
        d=np.abs(p@np.asarray(w['plane_normal']))*1000
        im=ax.scatter(p@np.array(w['u']),p@np.array(w['v']),c=d,s=1,cmap='turbo',vmin=0,vmax=max(1,float(np.percentile(d,99))))
        ax.set_aspect('equal');ax.set_title(f"{w['id']} | expanded N={len(w['expanded_indices'])} | discovery-plane residual")
        ax.set_xlabel('Wall U (m)');ax.set_ylabel('Wall V (m)');fig.colorbar(im,ax=ax,label='Absolute distance (mm)')
    for ax in list(axs.flat)[len(result['walls']):]:ax.set_visible(False)
    fig.tight_layout();fig.savefig(out/'wall_elevations.png',dpi=130);plt.close(fig)


def measurement_plots(r,out):
    ix=sample_ids(np.arange(len(r['indices'])),60000);uv=r['uv_m'][ix];d=r['signed_mm'][ix]
    vmax=max(1,float(np.percentile(np.abs(d),99)))
    fig,ax=plt.subplots(figsize=(9,6));im=ax.scatter(uv[:,0],uv[:,1],c=d,cmap='coolwarm',s=1,vmin=-vmax,vmax=vmax)
    ax.set_aspect('equal');ax.set_xlabel('Wall U (m)');ax.set_ylabel('Wall V (m)')
    ax.set_title(f"{r['wall_id']} | {r['mode']} | RMS {r['rms_mm']:.4f} mm | N={r['n_selected']}\nColor scale P99 only; RMS includes every selected point")
    fig.colorbar(im,ax=ax,label='Signed distance to fitted plane (mm)');fig.tight_layout();fig.savefig(out/'deviation.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4));ax.hist(r['signed_mm'],bins=90,color='#2677c9')
    ax.set_xlabel('Signed distance (mm)');ax.set_ylabel('Point count');ax.set_title('All selected points; no residual clipping')
    fig.tight_layout();fig.savefig(out/'histogram.png',dpi=140);plt.close(fig)


def viewer(points,result,out):
    basis=horizontal_frame(result['config']['up']);items=[]
    for j,w in enumerate(result['walls']):
        ids=sample_ids(w['expanded_indices'],4500);p=points[ids];c=np.array(w['plane_center_m'])
        items.append(dict(id=w['id'],color=COLORS[j%len(COLORS)],n=len(w['expanded_indices']),
                          center=np.round(c,4).tolist(),size=[round(w['width_m'],3),round(w['height_m'],3)],
                          xy=np.round(p@basis,4).tolist(),uv=np.round(np.c_[(p-c)@np.array(w['u']),(p-c)@np.array(w['v'])],4).tolist()))
    payload=json.dumps(items,ensure_ascii=True,separators=(',',':')).replace('<','\\u003c')
    html=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>墙面候选目录</title><style>body{font:16px system-ui;background:#f4f6f9;color:#162334;margin:24px auto;max-width:1100px;padding:0 18px}h1{font-size:28px}p{line-height:1.7}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}canvas{width:100%;background:white;border:1px solid #d9e0e8;border-radius:10px}button,select{font:inherit;padding:10px;border:1px solid #aab8c7;border-radius:6px;background:white}pre{padding:16px;background:#e8edf3;white-space:pre-wrap;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}tr{cursor:pointer}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style>
<h1>选择要测量的墙面</h1><p>先核对俯视位置和墙面投影，再选择墙号。这里展示的是候选墙面；几何识别可能包含柜体、附属物或不完整墙面。点图仅为显示抽样，正式计算使用全部选中点。单位：m。</p>
<label>墙面 <select id="select"></select></label> <span id="info"></span>
<div class="grid"><section><h2>房间俯视图</h2><canvas id="plan" width="700" height="620"></canvas></section><section><h2>选中墙面投影</h2><canvas id="wall" width="700" height="620"></canvas></section></div>
<p>在项目目录打开终端，复制下面的命令。若输出目录已存在，请换一个新名字；移动数据后需重新指定目录。</p><pre id="cmd"></pre>
<p><a href="catalog.json">完整目录与参数</a> · <a href="walls.csv">候选墙表</a> · <a href="wall_elevations.png">墙面偏差概览</a></p><table><thead><tr><th>墙号</th><th>测量点数</th><th>宽 × 高 / m</th><th>中心 XYZ / m</th></tr></thead><tbody id="rows"></tbody></table>
<script>const data=PAYLOAD;const catalogPath=CATALOG_PATH;const select=document.getElementById('select');
function draw(name,groups){const c=document.getElementById(name),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity;for(const g of groups)for(const p of g.pts){minx=Math.min(minx,p[0]);maxx=Math.max(maxx,p[0]);miny=Math.min(miny,p[1]);maxy=Math.max(maxy,p[1]);}let s=Math.min((c.width-90)/Math.max(.01,maxx-minx),(c.height-90)/Math.max(.01,maxy-miny));for(const g of groups){ctx.fillStyle=g.color;ctx.globalAlpha=g.alpha;for(const p of g.pts)ctx.fillRect(45+(p[0]-minx)*s,c.height-45-(p[1]-miny)*s,2.2,2.2);}ctx.globalAlpha=1;ctx.fillStyle='#334';ctx.font='15px sans-serif';ctx.fillText('U / m',c.width-65,c.height-15);ctx.fillText('V / m',15,25);ctx.fillText(minx.toFixed(2),40,c.height-20);ctx.fillText(maxx.toFixed(2),c.width-110,c.height-20);}
function update(){const w=data.find(x=>x.id===select.value);draw('plan',data.map(x=>({pts:x.xy,color:x.color,alpha:x.id===w.id?1:.23})));draw('wall',[{pts:w.uv,color:w.color,alpha:.85}]);document.getElementById('info').textContent=' '+w.id+' · '+w.n+' 个原始点';document.getElementById('cmd').textContent='.\\run_local.ps1 measure --catalog "'+catalogPath+'" --wall '+w.id+' --out "outputs/'+w.id+'_measurement"';}
for(const w of data){const o=document.createElement('option');o.value=w.id;o.textContent=w.id;select.append(o);const tr=document.createElement('tr');for(const x of [w.id,w.n,w.size.join(' × '),w.center.join(', ')]){const td=document.createElement('td');td.textContent=x;tr.append(td);}tr.onclick=()=>{select.value=w.id;update();};document.getElementById('rows').append(tr);}select.onchange=update;update();</script></html>'''
    (out/'index.html').write_text(html.replace('PAYLOAD',payload).replace('CATALOG_PATH',json.dumps(str((out/'catalog.json').resolve()),ensure_ascii=True)),encoding='utf-8')
