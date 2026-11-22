# 根据已完成的实验记录生成墙面选择与 RMS 准确性 Word 报告。
"""Chinese technical report, generated only from completed experiment records."""
from pathlib import Path
import csv
import json
import shutil
import numpy as np
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from room_walls.artifacts import dump
from room_walls.visuals import plt
from .scenes import CONDITIONS

ROOT=Path(__file__).resolve().parents[1];STUDY=ROOT/'outputs/accuracy_study_v3';REAL=ROOT/'outputs/accuracy_real_stability_refresh'
OUT=ROOT/'docs';QA=ROOT/'outputs/accuracy_report_qa';QA.mkdir(parents=True,exist_ok=True)
S=json.loads((STUDY/'condition_summary.json').read_text());P=json.loads((STUDY/'paired_comparison.json').read_text())
A=json.loads((STUDY/'affected_wall_summary.json').read_text());AUDIT=json.loads((STUDY/'audit.json').read_text())
R=json.loads((REAL/'records.json').read_text())
NAMES={'clean':'干净墙','noise_05':'噪声 0.5 mm','noise_2':'噪声 2 mm','sparse25':'保留 25% 点','sparse10':'保留 10% 点',
       'occlusion_center':'中央遮挡','bulge25':'鼓包 25 mm','bulge60':'鼓包 60 mm','recess25':'凹陷 25 mm',
       'near_clutter':'贴墙杂物','cabinet_floor':'接地柜板','density_gradient':'密度梯度','mixed':'组合干扰',
       'split_wall':'墙面中间断开','l_room':'L 形六面墙'}
def get(condition,mode='expanded',source='geometry'):
    return next(r for r in S if (r['condition'],r['mode'],r['source'])==(condition,mode,source))
def f(x,d=3):
    if x is None:return '—'
    if abs(x)<1e-6:return '≈0' if x!=0 else '0'
    if abs(x)<.0005:return f'{x:.2g}'
    return f'{x:.{d}f}'
def pct(x):return '—' if x is None else f'{100*x:.1f}%'
def ci(x):return '—' if x is None else '['+', '.join(f(v) for v in x)+']'


def charts():
    conditions=['clean','bulge25','bulge60','near_clutter','cabinet_floor','density_gradient','split_wall','l_room']
    fig,ax=plt.subplots(figsize=(10,4.8));x=np.arange(len(conditions))
    for i,mode in enumerate(['expanded','paper']):
        ax.bar(x+(i-.5)*.36,[get(c,mode)['room_joint_success'] for c in conditions],width=.36,label=mode,color=['#245a81','#ba7547'][i])
    ax.set_xticks(x,conditions,rotation=25,ha='right');ax.set_ylim(0,1.12);ax.set_ylabel('Whole-room joint success')
    ax.set_title('All walls must pass; extra/missed instances fail the room (20 rooms / condition)');ax.legend();fig.tight_layout()
    fig.savefig(QA/'room_success.png',dpi=180);plt.close(fig)
    conditions=['bulge25','bulge60','recess25','near_clutter','mixed','split_wall'];fig,ax=plt.subplots(figsize=(10,4.4));x=np.arange(len(conditions))
    for i,mode in enumerate(['expanded','paper']):
        vals=[next(r['mae_selection_mm'] for r in A if (r['condition'],r['source'],r['mode'])==(c,'geometry',mode)) for c in conditions]
        ax.bar(x+(i-.5)*.36,vals,width=.36,label=mode,color=['#245a81','#ba7547'][i])
    ax.set_xticks(x,conditions);ax.set_ylabel('Affected-wall MAE (mm)');ax.set_title('Only perturbed wall 1; unaffected walls do not dilute the error');ax.legend();fig.tight_layout()
    fig.savefig(QA/'affected_mae.png',dpi=180);plt.close(fig)


d=Document();sec=d.sections[0];sec.page_width=Cm(21.59);sec.page_height=Cm(27.94)
sec.top_margin=Cm(1.65);sec.bottom_margin=Cm(1.65);sec.left_margin=Cm(1.8);sec.right_margin=Cm(1.8)
for style,size in [('Normal',10.5),('Title',23),('Subtitle',11),('Heading 1',16),('Heading 2',12)]:
    st=d.styles[style];st.font.name='Calibri';st.font.size=Pt(size);st.font.color.rgb=RGBColor(0,0,0)
    st._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'微软雅黑')
    st.paragraph_format.space_after=Pt(6);st.paragraph_format.line_spacing=1.15
    if style.startswith('Heading'):st.paragraph_format.keep_with_next=True
header=sec.header.paragraphs[0];header.text='CIVL 7023  ·  墙面识别与测量评测';header.style='Caption'
for run in header.runs:run.font.color.rgb=RGBColor(0,0,0)
d.styles['Subtitle'].font.italic=False
for border in list(d.styles.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
footer=sec.footer.paragraphs[0];footer.alignment=2;footer.add_run('2026-11-22  |  ')
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
for el in list(d.styles.element.iter(qn('w:color'))):
    for attr in ['themeColor','themeTint','themeShade']:el.attrib.pop(qn('w:'+attr),None)

def p(text):return d.add_paragraph(text)
def h(text):return d.add_paragraph(text.replace('：',' ').replace('，',' ').replace('、',' '),'Heading 1')
def page(text):d.add_page_break();h(text)
def sub(text):return d.add_paragraph(text.replace('：',' ').replace('A.','A').replace('B.','B').replace('C.','C'),'Heading 2')
def table(headers,rows,widths=None):
    t=d.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths=widths or [17.99/len(headers)]*len(headers)
    for col,w in zip(t.columns,widths):col.width=Cm(w)
    for c,text in zip(t.rows[0].cells,headers):c.text=str(text)
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        for c,text in zip(t.add_row().cells,row):c.text=str(text)
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    t._tbl.tblPr.append(borders)
    for i,row in enumerate(t.rows):
        cant=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(cant)
        for j,(c,w) in enumerate(zip(row.cells,widths)):
            c.width=Cm(w);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'26465B' if i==0 else ('F2F5F7' if i%2==0 else 'FFFFFF'));c._tc.get_or_add_tcPr().append(shade)
            margins=OxmlElement('w:tcMar')
            for edge,value in [('top',65),('bottom',65),('left',80),('right',80)]:
                item=OxmlElement('w:'+edge);item.set(qn('w:w'),str(value));item.set(qn('w:type'),'dxa');margins.append(item)
            c._tc.get_or_add_tcPr().append(margins)
            for para in c.paragraphs:
                para.paragraph_format.space_after=Pt(2);para.paragraph_format.space_before=Pt(2);para.paragraph_format.line_spacing=1.05
                para.alignment=0 if j==0 else 1
                for run in para.runs:
                    run.font.size=Pt(9);run.font.name='Calibri';run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'微软雅黑')
                    run.font.color.rgb=RGBColor(255,255,255) if i==0 else RGBColor(0,0,0);run.bold=i==0
    d.add_paragraph().paragraph_format.space_after=Pt(0)
    return t
def mr(text):
    r=OxmlElement('m:r');t=OxmlElement('m:t');t.text=text;r.append(t);return r
def ms(base,subscript):
    s=OxmlElement('m:sSub');e=OxmlElement('m:e');e.append(mr(base));s.append(e);sub=OxmlElement('m:sub');sub.append(mr(subscript));s.append(sub);return s
def eq(elements):
    para=d.add_paragraph();om=OxmlElement('m:oMathPara');m=OxmlElement('m:oMath')
    for e in elements:m.append(e)
    om.append(m);para._p.append(om)
def rms_equation():
    rad=OxmlElement('m:rad');pr=OxmlElement('m:radPr');hide=OxmlElement('m:degHide');hide.set(qn('m:val'),'1');pr.append(hide);rad.append(pr);rad.append(OxmlElement('m:deg'))
    e=OxmlElement('m:e');frac=OxmlElement('m:f');num=OxmlElement('m:num');num.append(mr('1'));den=OxmlElement('m:den');den.append(mr('N'));frac.extend([num,den]);e.append(frac)
    summ=OxmlElement('m:nary');npr=OxmlElement('m:naryPr');ch=OxmlElement('m:chr');ch.set(qn('m:val'),'∑');npr.append(ch);summ.append(npr)
    lo=OxmlElement('m:sub');lo.append(mr('i=1'));hi=OxmlElement('m:sup');hi.append(mr('N'));body=OxmlElement('m:e')
    sq=OxmlElement('m:sSup');base=OxmlElement('m:e');base.append(ms('d','i'));sup=OxmlElement('m:sup');sup.append(mr('2'));sq.extend([base,sup]);body.append(sq);summ.extend([lo,hi,body]);e.append(summ);rad.append(e)
    eq([mr('RMS = '),rad])
def link(text,url):
    para=d.add_paragraph();hyper=OxmlElement('w:hyperlink');hyper.set(qn('r:id'),para.part.relate_to(url,RT.HYPERLINK,is_external=True))
    run=OxmlElement('w:r');props=OxmlElement('w:rPr');color=OxmlElement('w:color');color.set(qn('w:val'),'174D79');props.append(color);run.append(props)
    txt=OxmlElement('w:t');txt.text=text;run.append(txt);hyper.append(run);para._p.append(hyper)


def build():
    charts();d.add_paragraph('墙面选择与 RMS\n准确性评测方案及实验报告','Title')
    d.add_paragraph('整房间点云 → 墙面实例 → 指定墙面测量\n报告修订与实验复跑 / 重建版源码哈希见实验协议 / 2026年11月22日','Subtitle')
    h('结论与使用范围')
    p('当前方法能在受控、较完整的房间点云中识别墙面并正确计算所选点的 RMS；主要风险来自选点范围、缺陷截断、非墙物体和可见性，而非 RMS 公式。不能给出脱离场景和参考定义的单一“准确率”。')
    table(['本次证据','完成量','可支持的结论'],[
        ['新合成场景','20 个随机房间 × 15 条件 = 300 场景，本次重新运行','墙实例和点级真值明确；评估受控条件'],
        ['两种选点模式及语义上界','720 组评价 / 2,960 条目标墙记录','比较 expanded、paper 与正确语义标签'],
        ['真实点云稳定性','M26、M04 各 7 组设置','随机性和厚度敏感性；不是实体真值误差'],
        ['独立数值核对','最大差 '+f(AUDIT['max_oracle_numerical_error_mm'])+' mm','固定点集计算一致性'],
        ['真实墙面独立准确性','尚无同口径独立实体参考','不宣称现场毫米级精度已被证明']],[4.2,5.4,8.39])
    p('关键发现：25 mm 鼓包可被 expanded 保留；60 mm 鼓包超出默认恢复厚度，缺陷点被漏掉。贴墙杂物显著增加 RMS，接地柜板可能被误识别为额外墙面。降低 RMS 不能作为选择参数或区域的依据。')
    p('本报告的 0.2/0.5/1.0 mm 误差目标、IoU 门槛与联合成功条件均为项目评测约定，不是课程评分线或工程验收规范。当前识别采用几何规则，未训练 Point Transformer V3 或双头模型。')

    page('1 评价对象与参考答案层级')
    p('评价对象是完整链路：整房间点云输入，自动生成墙面候选和编号，再计算指定墙面区域的点加权最佳拟合平面 RMS。输入文件、单位、向上方向和目标墙的范围必须固定。')
    table(['层级','参考来源','可以评价','不能据此宣称'],[
        ['A','独立校准的实体测量','同测区、同定义的物理测量误差','未提供口径与不确定度时不能直接比较'],
        ['B','盲法人工标注原始扫描','墙识别、选点和该次扫描上的 RMS','消除扫描仪噪声或证明实体真值'],
        ['C','真值先行的合成房间','已知缺陷、噪声和可见性条件下的表现','代表所有真实房间和扫描设备'],
        ['D','独立算法复算／重复运行','数值正确性、重复性、参数敏感性','选区一定正确或物理测量准确']],[1.2,4.0,6.0,6.79])
    p('本次重新执行 C 类合成评测和 D 类真实点云稳定性检查。针对 B 提供标注规范、元数据模板和可执行评价入口；针对 A 给出补采协议。未把默认算法输出当作真实标签，也没有把人工扫描上选点的 RMS 等同于独立实体参考。')
    sub('已有官方参考怎样使用')
    p('官方说明给出 M26 指定墙 1.0 mm、M04 图片指定墙 1.8 mm。但精确测区、人工采样和拟合方法、不确定度未完整确认。不得把数值套到所有墙，也不得选择“最接近 1.0/1.8”的预测墙来建立匹配。现阶段只把它们作为待确认参考。')
    sub('数据划分与避免泄漏')
    p('被测生产算法冻结；新实验种子为 2001–2020，没有依据正式结果修改阈值。相同种子的不同扰动共享基础房间，属于相关配对。若以后训练模型，必须按物理房间／模块划分训练、验证和测试，不能把同一房间的邻近点随机拆分后称为独立测试。两个真实房间不足以证明广泛现场泛化。')

    page('2 墙面选择准确性：先匹配，再计分')
    p('“找到四面墙”只说明数量可能一致，并不说明墙的位置、点集合或身份正确。用原始点 ID 计算预测墙集合与参考墙集合的 IoU，在门槛内作一对一匹配。先最大化有效配对数，再最大化这些配对的 IoU，避免一个预测同时算作多面墙。')
    eq([mr('IoU = '),mr('|P ∩ G| / |P ∪ G|')])
    p('主门槛 IoU ≥ 0.50；辅助门槛 0.25、0.75。没有匹配到的真实墙记 FN，没有匹配到真实墙的预测记 FP。未达到匹配门槛的预测不会强行算作正确墙面。')
    table(['指标','含义','为什么需要'],[
        ['实例 Precision / Recall / F1','TP/(TP+FP)、TP/(TP+FN) 及调和均值','同时看到漏墙和把柜板当墙'],
        ['逐墙点 Precision','选中点中实际属于目标墙的比例','量化杂物污染'],
        ['逐墙点 Recall / IoU','参考墙点被保留的比例／交并比','量化漏选及区域偏移'],
        ['全墙二分类 IoU','不区分墙号的墙／非墙点集合 IoU','检查前景选择，不能替代实例区分'],
        ['所有参考墙 best-IoU 均值','每面墙最佳重叠，没预测记 0','避免只统计成功匹配的墙'],
        ['缺陷、边缘与网格覆盖','缺陷点召回、100 mm 边缘带召回、100 mm 可见网格覆盖','防止大面积正常点掩盖局部鼓包漏失']],[4.0,7.0,6.99])
    p('不报告由大背景主导的整体点 accuracy，也不把没有置信度排序的 F1 称为 mAP。ScanNet 等实例评测采用基于掩码重叠的评价思路；本项目定义自己的墙实例任务，不宣称获得 ScanNet 官方分数。[2]')
    p('拆分／合并诊断另行保存：一面参考墙与多个预测有显著交集，或一个预测覆盖多面参考墙时，提示过分割或欠分割。正常墙面的高分不能抵消缺陷点的漏选。')

    page('3 RMS 准确性：把误差来源拆开')
    rms_equation();p('dᵢ 为点到该点集最佳拟合平面的正交距离。所有结果按点加权、单位 mm；不等同于直尺法、最小区域法或设计平面偏差。测量定义属于参考可比性的一部分。[3]')
    table(['符号','参考定义'],[
        ['Rfull','完整无噪离散参考墙的 RMS，包含生成的真实缺陷'],
        ['Rvisible','经采样或遮挡后，剩余真实墙点的无噪 RMS'],
        ['Robs','同一批可见真实墙点加入观测噪声后的独立 RMS'],
        ['Rpred','算法自动选择点集得到的 RMS']],[3.0,14.99])
    eq([ms('e','selection'),mr(' = '),ms('R','pred'),mr(' − '),ms('R','obs')])
    eq([ms('e','noise'),mr(' = '),ms('R','obs'),mr(' − '),ms('R','visible')])
    eq([ms('e','visibility'),mr(' = '),ms('R','visible'),mr(' − '),ms('R','full')])
    eq([ms('e','total'),mr(' = '),ms('e','selection'),mr(' + '),ms('e','noise'),mr(' + '),ms('e','visibility')])
    p('主指标相对 Robs 统计 bias、MAE、RMSE、MedAE、P95AE 和最大 AE；相对 Rfull 的误差作为完整表面恢复能力诊断。逐条记录核对上面的恒等式。未成功匹配的墙没有合法 RMS 误差，记为空，不能赋 0。')
    p('另报告法向角误差和参考墙质心处的法向偏移。参考为 0 时相对误差无定义；接近 0 时比例会不稳定，正文以毫米绝对误差为主。噪声场景即使 e_selection 接近零，也可能有明显 e_noise，不能据此声称恢复了无噪实体表面。')
    p('数值验证使用真实墙点掩码直接调用被测 SVD，再与独立协方差特征向量求面和残差 RMS 比较。这个小误差只证明计算一致性，不代表扫描仪精度。')

    page('4 固定实验矩阵与对照')
    p('20 个随机房间改变长宽高、姿态、位置和基础粗糙度。每面墙从 0、0.5、1、1.8、3、5 mm 中取基础值；生成真实曲面后才加入观测扰动。默认 Config 原样使用，仅提供正确 up。基础采样约 45 mm，明显不同于官方点云的 10 mm 体素间隔。')
    table(['条件','施加变化','主要检验'],[
        [NAMES[c],text,purpose] for c,text,purpose in [
        ('clean','完整无噪房间','基线与数值一致性'),('noise_05','XYZ 独立高斯噪声 σ=0.5 mm','低噪声影响'),('noise_2','σ=2 mm','噪声与真实粗糙度区分'),
        ('sparse25','随机保留 25%','邻域／连通失效'),('sparse10','随机保留 10%','极稀疏失败'),('occlusion_center','墙1中央区域不可见','完整墙与可见墙差异'),
        ('bulge25','墙1局部 +25 mm','是否保留缺陷'),('bulge60','墙1局部 +60 mm','厚度截断'),('recess25','墙1局部 −25 mm','凹陷保留'),
        ('near_clutter','墙前 30 mm 非墙表面','杂物污染'),('cabinet_floor','接地柜板','假墙误检'),('density_gradient','空间变化采样密度','局部缺失和权重变化'),
        ('mixed','遮挡＋噪声＋贴墙杂物','组合失效'),('split_wall','遮挡贯穿墙中部竖带','连通块只保留一侧'),('l_room','六面墙的 L 形平面','非四墙房型')]], [3.4,6.7,7.89])
    p('expanded 与 paper 在同一发现结果上配对比较。paper 只代表严格内点消融，不是论文深度学习复现。near_clutter、cabinet_floor、mixed 额外用正确语义标签作上界对照，共 60 次额外发现；标签来自合成真值，不能当成模型分割成绩。')

    page('5 统计口径与成功标准')
    p('同时报告“有结果的墙测得怎样”和“所有应测墙中有多少真正完成任务”。仅列成功样本 MAE 会遗漏整面墙检不出的风险。所有失败都保留在成功率分母。')
    table(['层次','定义'],[
        ['有效结果率','IoU≥0.50 成功匹配并得到有效 RMS 的墙数 / 全部目标墙数'],
        ['误差目标成功率','成功匹配且 |e_selection|≤0.2 / 0.5 / 1.0 mm 的比例'],
        ['严格逐墙联合成功','IoU≥0.75、点精确率≥0.95、点召回≥0.95、AE≤0.2 mm 同时成立'],
        ['缺陷联合成功','严格逐墙联合条件，再加可见缺陷点召回≥0.95'],
        ['整房间联合成功','无多余墙／漏墙，而且每面墙都满足严格逐墙联合条件']],[4.3,13.69])
    p('最后两类补充诊断防止三面正常墙掩盖一面严重失效，也防止真实墙测量很好但多识别一个柜板仍被称为整房间成功。阈值是项目约定，实际工程应用必须按正式测量定义和需求重新确定。')
    sub('区间与配对比较')
    p('每个条件以 20 个随机生成房间为抽样单元，房间内所有墙共同重采样，做 2,000 次 percentile bootstrap，给出 95% 区间。expanded−paper 在共同匹配的同一参考墙上计算配对 MAE 差，并列出不共同匹配的数量；成功率比较保留所有目标墙。[4]')
    p('20 个簇仍有限。全部成功／失败时 bootstrap 区间会退化，不能解释为没有不确定性。因此整房间二项结果额外报告 Clopper-Pearson 精确区间：20/20 对应约 [83.2%,100%]，0/20 对应约 [0%,16.8%]。此补充在汇总阶段加入，没有改变任何实验设置。')
    p('上述区间只描述本合成生成分布，不是现场总体置信区间。两个真实房间只做描述性分析。不能把 2,960 条相关墙记录或数百万点当成独立实体样本。')

    page('6 实际结果：墙面选择准确性')
    p('下表为默认几何识别＋expanded。每组 20 个房间；普通房间每组 80 面目标墙，L 形每组 120 面。F1 主门槛为 IoU≥0.50；best-IoU 均值对全部参考墙计分，漏检取 0。')
    table(['条件','TP/FP/FN','实例 F1','best-IoU','整房间成功'],[
        [NAMES[c],'/'.join(str(get(c)['instance_0.5'][k]) for k in ['tp','fp','fn']),f(get(c)['instance_0.5']['f1']),f(get(c)['best_iou_mean']),pct(get(c)['room_joint_success'])] for c in CONDITIONS],[4.0,3.8,2.4,2.8,4.99])
    p('接地柜板：每个房间多识别一面假墙，实例精确率为 80%，即使四面真墙的 RMS 很准，整房间仍失败。密度梯度：每个房间平均漏一面墙。中间断开：IoU≥0.50 仍能配对，但点召回不足，严格联合失败。')
    p('25% 和 10% 稀疏条件下，默认固定邻域参数均未发现可靠地面。该结果针对本实验 45 mm 基础网格再稀疏的输入，不能表述成“任何点云减少到 25% 都必然失败”。')

    page('7 实际结果：RMS 准确性与分母')
    p('MAE 是有效匹配墙相对 Robs 的条件误差；“≤0.2 mm”成功率分母包含全部目标墙。整墙无结果用“—”，不算作零误差。这里的小误差不包含实体测量噪声影响。')
    table(['条件','有效/应测','MAE exp.\nmm','MAE paper\nmm','exp. ≤0.2','exp. 对完整墙\nMAE / mm'],[
        [NAMES[c],f"{get(c)['n_valid']}/{get(c)['n_target_walls']}",f(get(c)['mae_selection_mm']),f(get(c,'paper')['mae_selection_mm']),pct(get(c)['success_02']),f(get(c)['mae_total_mm'])] for c in CONDITIONS],
        [3.6,2.6,2.7,2.7,2.7,3.69])
    p('噪声 2 mm 条件中，expanded 对已观测真实墙点的选点误差接近零，但相对完整无噪墙的 MAE 为 '+f(get('noise_2')['mae_total_mm'])+' mm。算法算对了带噪点云的 RMS，不等于消除了噪声。')
    p('bulge60 的全部墙平均 MAE 为 '+f(get('bulge60')['mae_selection_mm'])+' mm，但只有墙1带缺陷；应同时看下一页受影响墙子集，避免另外三面墙稀释严重失效。')

    page('8 局部缺陷和杂物：重点看受影响的墙')
    affected=['bulge25','bulge60','recess25','near_clutter','mixed','split_wall']
    def ag(c,m):return next(r for r in A if (r['condition'],r['source'],r['mode'])==(c,'geometry',m))
    table(['条件（各20面）','exp. MAE mm','paper MAE mm','exp. 最大 AE mm'],[
        [NAMES[c],f(ag(c,'expanded')['mae_selection_mm']),f(ag(c,'paper')['mae_selection_mm']),f(ag(c,'expanded')['maxae_selection_mm'])] for c in affected],[5.6,4.0,4.0,4.39])
    d.add_picture(str(QA/'affected_mae.png'),width=Cm(17.2))
    p('25 mm 鼓包：expanded 的缺陷点召回率 100%，paper 为 0%。60 mm 鼓包：两种模式均为 0%，因为超过默认 50 mm 恢复半厚度。贴墙杂物：expanded 保留更多点的同时也保留了非墙点，因此受影响墙 MAE 约 8.072 mm。')
    p('不存在“选择 RMS 更小的模式就更正确”的规则：paper 可以排掉杂物，也可以排掉真实缺陷。正确语义标签对照能排除合成杂物，使对应 expanded 误差恢复到数值精度；这只是说明可靠语义信息有价值，不证明当前已经具备这种自动语义能力。')

    page('9 区间、模式差异与数值检查')
    selected=['bulge60','near_clutter','cabinet_floor','density_gradient','mixed','split_wall','l_room']
    table(['条件','exp. MAE mm','房间 bootstrap 95% 区间','exp.−paper MAE mm'],[
        [NAMES[c],f(get(c)['mae_selection_mm']),ci(get(c)['ci95']['mae_selection_mm']),f(next(r for r in P if r['condition']==c and r['source']=='geometry')['delta_mae_expanded_minus_paper_mm'])] for c in selected],[3.8,3.6,6.0,4.59])
    p('差值为正表示 expanded 的条件 MAE 更大，为负表示更小；表中配对比较只使用双方共同匹配的参考墙。所有记录都同时保存共同／不共同匹配墙数和成功率差值，不能只看条件 MAE 的符号。')
    d.add_picture(str(QA/'room_success.png'),width=Cm(17.2))
    p('独立数值检查：正确墙点掩码上的被测 SVD 与协方差特征向量求解，最大 RMS 差为 '+f"{AUDIT['max_oracle_numerical_error_mm']:.3g}"+' mm。这仅验证浮点数计算。每条已匹配记录的误差拆解恒等式均经程序检查；合成点云和真值数组可用种子与哈希复现。')

    page('10 官方房间：稳定性和厚度敏感性')
    rows=[]
    for room in ['M26','M04']:
        roomrecords=[r for r in R if r['room']==room];base=next(r for r in roomrecords if r['setting']=='seed_7023')
        for w in base['rows']:
            wid=w['baseline_wall'];seedvals=[next(x['rms_mm'] for x in rr['rows'] if x['baseline_wall']==wid) for rr in roomrecords if rr['setting'].startswith('seed_')]
            low=next(x['rms_mm'] for rr in roomrecords if rr['setting']=='recovery_20.0mm' for x in rr['rows'] if x['baseline_wall']==wid)
            high=next(x['rms_mm'] for rr in roomrecords if rr['setting']=='recovery_100.0mm' for x in rr['rows'] if x['baseline_wall']==wid)
            rows.append([room+' '+wid,f(w['baseline_rms_mm']),f(float(np.std(seedvals,ddof=1))),f(max(seedvals)-min(seedvals)),f(low),f(high)])
    table(['房间/墙号','默认 RMS','种子标准差','种子极差','厚度20 mm','厚度100 mm'],rows,[3.6,2.7,2.9,2.9,2.9,2.99])
    p('表内数值均为 mm。5 个种子为 7023、11、29、47、101。恢复厚度是法向半厚度，默认 50 mm；20/100 mm 仅用于敏感性检查，不是按官方参考值调优。不同运行按原始点 IoU 与默认目录配对，不依赖墙号始终相同。')
    p('种子变化相对小，不代表选区正确；厚度变化对某些墙影响很大。例：M04 W02 默认约 12.689 mm，改半厚度 20 mm 后约 2.899 mm，改 100 mm 后约 23.530 mm。此变化可能来自边缘、杂物和实际表面变化混合，不能仅凭较小数值认定更准确。')
    p('本页默认自动点集只是稳定性配对基准，不是人工标注，也不是物理真值。因此不计算“官方准确率”，不对两个房间作现场总体置信区间。')

    page('11 补齐真实准确性的实施方案')
    sub('A. 盲法墙面标注：先证明选点准确')
    p('两名标注者各自查看原始点云／颜色，不显示算法墙号、残差色图和目标 RMS。标注每面墙的原始点：0=非墙、−1=争议/未知、1..K=墙实例。统一墙面、门框、电气盒、真实鼓包与开口的规则；真实缺陷仍属于墙。')
    p('冻结文件哈希、单位和点序。先报告标注者间实例匹配与 IoU，再裁决争议；保留被忽略点比例和边界敏感性。不得把自动候选直接复制成 GT。输出审定 NPY 和元数据后，可调用 evaluation.manual_reference，评价非忽略域上的识别与扫描 RMS。')
    sub('B. 独立物理测量：再证明测量准确')
    p('为每面墙固定测区、坐标基准、参考面定义及采样规则；独立校准设备测量相同物理区域。记录测量点位置、遮挡、采样密度、证书与不确定度、环境、重复测量和配准误差。直尺读数不能直接作为最佳拟合平面 RMS 真值。')
    p('按明确的测量模型识别不确定度分量：重复观测的统计分量、仪器校准／分辨率、基准和配准、区域标记与采样。组合时保留相关性或协方差；不要把同一墙的所有点当独立读数来人为缩小不确定度。报告覆盖因子及其依据，不自动把误差与不确定度混为一谈。[3][5]')
    sub('C. 验收用判据应事先确定')
    p('若项目要求最大允许测量误差 T，应在实验前固定 T 和决策规则。需要同时考虑参考不确定度；不能用本报告暂定 0.2 mm 工作目标代替课程或工程规范。新增房间应覆盖不同墙材、开口、杂物和扫描条件，并按物理房间保留独立测试集。')
    p('当前最优先补充的是独立墙实例标注和同测区物理参考，而不是继续增加同一房间的随机点数。未完成这些工作前，应把结果定位为受控实验与实际点云可行性证据。')

    page('12 复现入口、证据和使用结论')
    p('正式实验期间生产 room_walls 源码哈希保持不变。评测新增了指标单元测试、参考先行的场景生成器、逐实例误差分解、分组汇总、房间层区间与实际点云稳定性检查。PowerShell 启动脚本仅修复参数透传，未改变识别或 RMS 算法。')
    table(['文件/命令','用途'],[
        ['docs/accuracy_protocol.md','完整评测协议、门槛与参考层级'],
        ['python_local.ps1 -m evaluation.runner --out outputs/new_study','重跑 20 房间 × 15 条件；拒绝覆盖'],
        ['python_local.ps1 -m evaluation.summarize outputs/new_study','分组误差、区间、配对和受影响墙统计'],
        ['evaluation/manual_reference.py','接收审定人工标签；完整参数见 --help'],
        ['results/accuracy_v1/','逐墙、逐条件、协议哈希、稳定性和审计记录'],
        ['outputs/accuracy_report_qa/','本地图和排版检查材料']],[9.0,8.99])
    p('使用结论：可以使用本模块执行墙面候选发现、指定区域测量和可追踪输出。在默认条件的连续、较完整墙面上，合成结果良好；稀疏度、空间密度变化、柜板、贴墙杂物和超厚度缺陷需要特别处理。现阶段不宜把“识别到了墙”或“RMS 很小”直接当作质量合格或实体测量准确的证明。')
    sub('参考资料')
    p('[1] 用户提供论文：Chen 等，Exploiting Point Cloud Semantic Segmentation for Automatic Geometric Measurement in Modular Construction，§2.1、2.2.1、2.2.3；课程原版要求与 Chen lecture。原文不随仓库再分发。')
    link('[2] ScanNet 官方实例评测实现（仅参考掩码重叠评价思路）','https://github.com/ScanNet/ScanNet/blob/master/BenchmarkScripts/3d_evaluation/evaluate_semantic_instance.py')
    link('[3] NIST TN 1297 Appendix D4：由测量方法定义的被测量','https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-d4-measurand-defined-measurement-method')
    link('[4] SciPy 官方文档：bootstrap','https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html')
    link('[5] NIST TN 1297 §5：合成标准不确定度及相关性','https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-5-combined-standard-uncertainty')
    from datetime import datetime, timezone
    d.core_properties.created=d.core_properties.modified=datetime.now(timezone.utc)
    d.core_properties.comments='当前重建版；合成评测和真实点云稳定性均重新运行；不代表独立实体精度验证。'
    dest=OUT/'墙面选择与RMS准确性_评测方案及实验报告.docx';d.save(dest)
    resultdir=ROOT/'results/accuracy_v1';resultdir.mkdir(parents=True,exist_ok=True)
    for name in ['protocol.json','execution.json','records.jsonl','condition_summary.json','condition_summary.csv','paired_comparison.json','affected_wall_summary.json','wall_records.json','audit.json']:
        shutil.copyfile(STUDY/name,resultdir/name)
    shutil.copyfile(REAL/'records.json',resultdir/'real_stability.json');shutil.copyfile(REAL/'protocol.json',resultdir/'real_stability_protocol.json')
    print(dest)


if __name__=='__main__':build()
