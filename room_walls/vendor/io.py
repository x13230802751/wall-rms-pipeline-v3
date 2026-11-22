# 提供复用的 PCD、CSV 和 ZIP 点云读取及内容哈希计算。
"""Read XYZ without discarding original row indices or modifying source files."""
from pathlib import Path
import io,zipfile,hashlib
import numpy as np

def source_bytes(source):
    if '::' in source:
        archive,member=source.split('::',1)
        with zipfile.ZipFile(archive) as z:
            info=z.getinfo(member)
            if info.file_size>2_000_000_000:raise ValueError('Point cloud exceeds 2 GB reader limit')
            return z.read(member),Path(member).suffix.lower()
    p=Path(source)
    if p.stat().st_size>2_000_000_000:raise ValueError('Point cloud exceeds 2 GB reader limit')
    return p.read_bytes(),p.suffix.lower()

def read_pcd(data):
    f=io.BytesIO(data);header={}
    while True:
        line=f.readline()
        if not line:raise ValueError('Missing PCD DATA header')
        if len(line)>10000:raise ValueError('Invalid PCD header line')
        try:parts=line.decode('ascii').strip().split()
        except UnicodeDecodeError as e:raise ValueError('Invalid PCD header encoding') from e
        if not parts or parts[0].startswith('#'):continue
        header[parts[0].upper()]=parts[1:]
        if parts[0].upper()=='DATA':break
    try:
        fields=header['FIELDS'];sizes=list(map(int,header['SIZE']));types=header['TYPE'];counts=list(map(int,header.get('COUNT',['1']*len(fields))))
        n=int(header['POINTS'][0]);mode=header['DATA'][0]
        if len(set(fields))!=len(fields) or not len(fields)==len(sizes)==len(types)==len(counts):raise ValueError('Inconsistent PCD fields')
        if n<0 or any(c<1 for c in counts):raise ValueError('Invalid PCD point count')
        if 'WIDTH' in header and 'HEIGHT' in header and int(header['WIDTH'][0])*int(header['HEIGHT'][0])!=n:raise ValueError('PCD dimensions do not match POINTS')
        if not all(k in fields and counts[fields.index(k)]==1 for k in ('x','y','z')):raise ValueError('PCD needs scalar x y z')
        type_map={('F',4):'<f4',('F',8):'<f8',('I',1):'i1',('I',2):'<i2',('I',4):'<i4',('I',8):'<i8',('U',1):'u1',('U',2):'<u2',('U',4):'<u4',('U',8):'<u8'}
        dtype=np.dtype([(k,type_map[(t,s)],(c,)) for k,s,t,c in zip(fields,sizes,types,counts)])
        body=f.read()
        if mode=='binary':
            if len(body)!=n*dtype.itemsize:raise ValueError('Truncated or oversized PCD binary payload')
            a=np.frombuffer(body,dtype=dtype,count=n)
            return np.column_stack([a[k][:,0] for k in ('x','y','z')]).astype(np.float64)
        if mode=='ascii':
            a=np.loadtxt(io.BytesIO(body),ndmin=2)
            if a.shape!=(n,sum(counts)):raise ValueError('PCD ASCII count mismatch')
            offsets=np.cumsum([0]+counts[:-1]);return a[:,[offsets[fields.index(k)] for k in ('x','y','z')]]
        raise ValueError(f'Unsupported PCD DATA {mode}; use binary or ascii')
    except (KeyError,IndexError) as e:raise ValueError(f'Malformed or unsupported PCD header: {e}') from e

def read_cloud(source,with_hash=False):
    data,suffix=source_bytes(str(source))
    if suffix=='.pcd':points=read_pcd(data)
    elif suffix=='.csv':
        a=np.genfromtxt(io.BytesIO(data),names=True,delimiter=',',encoding='utf-8-sig',ndmin=1)
        if not a.dtype.names or not all(k in a.dtype.names for k in ('x','y','z')):raise ValueError('CSV header must include x,y,z')
        points=np.column_stack([a[k] for k in ('x','y','z')]).astype(float)
    else:raise ValueError('Supported inputs: .pcd or .csv, optionally archive.zip::member.pcd')
    return (points,hashlib.sha256(data).hexdigest()) if with_hash else points
