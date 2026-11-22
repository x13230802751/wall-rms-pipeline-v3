# 生成带墙面真值的随机房间，并加入噪声、缺陷、遮挡和杂物。
"""Truth-first random rooms. No discovery/fitting function from the tested code."""
import hashlib
import numpy as np
from .metrics import reference_plane

CONDITIONS=['clean','noise_05','noise_2','sparse25','sparse10','occlusion_center','bulge25','bulge60',
            'recess25','near_clutter','cabinet_floor','density_gradient','mixed','split_wall','l_room']


def generate(seed,condition):
    if condition not in CONDITIONS:raise ValueError('Unknown condition')
    rng=np.random.default_rng(seed);L=rng.uniform(3.2,4.4);W=rng.uniform(2.6,3.5);H=rng.uniform(2.5,3.2)
    step=.045;vertices=np.array([[0,0],[L,0],[L,W],[0,W]])
    if condition=='l_room':vertices=np.array([[0,0],[L,0],[L,W*.55],[L*.6,W*.55],[L*.6,W],[0,W]])
    target_choices=[0.,.5,1.,1.8,3.,5.];parts=[];ids=[];semantic=[];uvparts=[];edge=[];defects=[];fullrefs={}
    target_rms=[]
    for j,start in enumerate(vertices):
        end=vertices[(j+1)%len(vertices)];direction=end-start;length=np.linalg.norm(direction);t=direction/length
        normal=np.array([-t[1],t[0],0.]);s,z=np.meshgrid(np.arange(.02,length-.02,step),np.arange(.02,H-.02,step))
        u=s.ravel();v=z.ravel();design=np.c_[np.ones(len(u)),u,v]
        phase=rng.uniform(0,6.28,3)
        shape=np.sin(u/length*2*np.pi+phase[0])*np.cos(v/H*2*np.pi+phase[1])+.3*np.cos(4*np.pi*u/length+phase[2])
        shape-=design@np.linalg.lstsq(design,shape,rcond=None)[0]
        rms=target_choices[(seed+j)%len(target_choices)];target_rms.append(rms)
        d=shape*(rms/1000)/np.sqrt(np.mean(shape**2));defect=np.zeros(len(u),bool)
        if j==0 and condition in ('bulge25','bulge60','recess25','mixed'):
            defect=(u>length*.28)&(u<length*.53)&(v>H*.34)&(v<H*.60)
            height={'bulge25':.025,'bulge60':.060,'recess25':-.025,'mixed':.025}[condition]
            d[defect]+=height
        p=np.c_[start[0]+t[0]*u,start[1]+t[1]*u,v]+d[:,None]*normal
        fullrefs[j+1]=reference_plane(p)['rms_mm']
        parts.append(p);ids.extend([j+1]*len(p));semantic.extend([2]*len(p));uvparts.append(np.c_[u,v])
        edge.extend((np.minimum.reduce([u,length-u,v,H-v])<=.1).tolist());defects.extend(defect.tolist())
    xx,yy=np.meshgrid(np.arange(.02,L-.02,step),np.arange(.02,W-.02,step))
    mask=np.ones(xx.size,bool)
    if condition=='l_room':mask=~((xx.ravel()>L*.6)&(yy.ravel()>W*.55))
    for height,label in [(0.,1),(H,0)]:
        p=np.c_[xx.ravel()[mask],yy.ravel()[mask],np.full(mask.sum(),height)]
        parts.append(p);ids.extend([0]*len(p));semantic.extend([label]*len(p));uvparts.append(np.zeros((len(p),2)))
        edge.extend([False]*len(p));defects.extend([False]*len(p))
    if condition in ('near_clutter','mixed','cabinet_floor'):
        s,z=np.meshgrid(np.arange(L*.25,L*.55,step),np.arange(.6,H*.65,step))
        y=.03
        if condition=='cabinet_floor':
            s,z=np.meshgrid(np.arange(L*.25,L*.65,step),np.arange(.02,2.1,step));y=.5
        p=np.c_[s.ravel(),np.full(s.size,y),z.ravel()]
        parts.append(p);ids.extend([0]*len(p));semantic.extend([12]*len(p));uvparts.append(np.zeros((len(p),2)))
        edge.extend([False]*len(p));defects.extend([False]*len(p))
    clean=np.vstack(parts);truth=np.array(ids);labels=np.array(semantic);uv=np.vstack(uvparts)
    boundary=np.array(edge);defect=np.array(defects);keep=np.ones(len(clean),bool)
    # Acquisition randomness is separate from geometry RNG.
    obs_rng=np.random.default_rng(seed+90000)
    if condition in ('sparse25','sparse10'):keep=obs_rng.random(len(clean))<(.25 if condition=='sparse25' else .10)
    if condition in ('occlusion_center','mixed'):
        keep &= ~((truth==1)&(uv[:,0]>L*.22)&(uv[:,0]<L*.65)&(uv[:,1]>H*.28)&(uv[:,1]<H*.72))
    if condition=='split_wall':keep &= ~((truth==1)&(uv[:,0]>L*.40)&(uv[:,0]<L*.60))
    if condition=='density_gradient':keep &= obs_rng.random(len(clean))<np.clip(.10+.90*clean[:,0]/L,.1,1.)
    clean,truth,labels,uv,boundary,defect=[a[keep] for a in (clean,truth,labels,uv,boundary,defect)]
    sigma={'noise_05':.0005,'noise_2':.002,'mixed':.001}.get(condition,0.)
    observed=clean+obs_rng.normal(0,sigma,clean.shape)
    yaw=rng.uniform(-np.pi,np.pi);tilt=rng.uniform(-.14,.14)
    rz=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]])
    rx=np.array([[1,0,0],[0,np.cos(tilt),-np.sin(tilt)],[0,np.sin(tilt),np.cos(tilt)]])
    rotation=rz@rx;offset=rng.uniform(-12,12,3)
    observed=observed@rotation.T+offset;clean=clean@rotation.T+offset
    return dict(seed=seed,condition=condition,points=observed,clean=clean,instances=truth,labels=labels,
                uv=uv,boundary=boundary,defect=defect,full_refs=fullrefs,up=tuple(rotation[:,2]),
                nominal_rms_mm=target_rms,noise_sigma_mm=sigma*1000,
                input_sha256=hashlib.sha256(observed.tobytes()).hexdigest(),
                truth_sha256=hashlib.sha256(truth.tobytes()).hexdigest())
