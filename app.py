"""z/OS Compatibility Intelligence — seven-page Streamlit application.

Run: streamlit run app.py
Data provenance: original six vendor CSVs (baseline); separately stored Broadcom vendor snapshots.
Refresh executes a source read on demand. Failed scrapes never remove the preceding snapshot.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st

from compatibility_db import CompatibilityDB, VENDORS, ZOS_VERSIONS, VER, SOURCES, build_excel, to_output
from crawler import BROADCOM_URL, crawl_broadcom
from store import DEFAULT_DB, latest, changes, jobs, save, record_error, save_vendor_audits, vendor_audits
from multi_vendor import audit_all, audit_vendor, sources_for_vendors, reconcile_observations, audit_uploaded_document
from evidence_pipeline import latest_unique_observations, UNKNOWN_PTF
from vendor_coverage import product_source_worklist, coverage_summary
from rag_engine import RagIndex, generate_answer, watsonx_configured
from workbook_data import NAME as ISV_NAME, load_workbook, merge_workbook, workbook_worklist, extract_ptfs
from maintenance import ids as maintenance_ids, display_ptfs, link_present
from quality import ptf_ids, maintenance_availability, maintenance_source, scraped_ptf_status, match_key, installation_status, per_ptf_statements

BASE=Path(__file__).resolve().parent

# Automatically refresh approved vendor evidence after app startup.
# Nonblocking and safe to skip when permissions/network/browser are unavailable.
from auto_scrape_v13 import launch as _launch_vendor_scraping
_launch_vendor_scraping(BASE)
DB_PATH=Path(os.getenv('ZOS_DB_PATH',str(DEFAULT_DB)))
XLSX_MIME='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PAGE_NAMES=['Overview','Comparative Matrix','Compatibility Matrix','PTF Intelligence','Source Monitor','Extraction Coverage','Change History','Inventory Readiness','AI Assistant','Workbook Explorer']
st.set_page_config(page_title='z/OS Compatibility Intelligence', page_icon='🖥️',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root { --brand: #1d4ed8; --navy: #101d35; --accent:#38bdf8; }
html, body, [class*="st-"] {font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;}
.block-container {padding-top:1.7rem;padding-bottom:3rem;max-width:1580px;}
[data-testid="stSidebar"] {border-right:1px solid rgba(116,138,169,.16);}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {letter-spacing:-.025em;}
[data-testid="stSidebar"] [role="radiogroup"] label {border-radius:9px;padding:5px 7px;margin-bottom:3px;}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:rgba(62,116,221,.12);}
[data-testid="stMetric"] {padding:1rem 1.15rem;border:1px solid rgba(116,138,169,.19);border-radius:14px;background:rgba(125,155,204,.045);min-height:107px;}
[data-testid="stMetricLabel"] {font-size:.81rem;color:#64748b;font-weight:600;}
[data-testid="stMetricValue"] {font-weight:750;letter-spacing:-.04em;}
[data-testid="stDataFrame"] {border:1px solid rgba(116,138,169,.18);border-radius:11px;overflow:hidden;}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {border-radius:10px;font-weight:650;}
.stTabs [data-baseweb="tab-list"] {gap:.4rem;}
.stTabs [data-baseweb="tab"] {border-radius:8px 8px 0 0;}
.brand {position:relative;overflow:hidden;padding:28px 30px;background:linear-gradient(115deg,#101d35 0%,#193e70 58%,#155e8c 100%);box-shadow:0 10px 30px rgba(16,29,53,.13);border-radius:17px;color:white;margin-bottom:20px;}
.brand:after {content:'';position:absolute;right:-48px;top:-72px;width:290px;height:290px;border-radius:50%;border:55px solid rgba(255,255,255,.055);pointer-events:none;}
.brand h1 {font-size:clamp(1.5rem,2.5vw,2.15rem);font-weight:800;letter-spacing:-.045em;color:#fff;margin:0;position:relative;z-index:1;}
.brand p {color:#cfdef2;margin:7px 0 0;font-size:.92rem;max-width:850px;position:relative;z-index:1;}
.small-note {font-size:12px;color:#64748b;}
.section-kicker {font-size:.72rem;font-weight:750;letter-spacing:.13em;color:#3282db;text-transform:uppercase;margin-bottom:.45rem;}
.status-good {border-left:4px solid #16a34a;}.status-warn {border-left:4px solid #f59e0b;}
@media(max-width:850px){.block-container{padding:1rem}.brand{padding:22px 19px;border-radius:13px}}
</style>''',unsafe_allow_html=True)

@st.cache_resource
def csv_db():
    return CompatibilityDB.load(str(BASE/'data'))

@st.cache_data(show_spinner=False)
def workbook():
    return load_workbook(BASE / ISV_NAME)

@st.cache_resource
def base_db():
    raw=csv_db()
    _,amxt,urls=workbook()
    return CompatibilityDB(merge_workbook(raw.df,amxt,urls))


def source_records():
    try:return latest(path=DB_PATH)
    except Exception as exc:
        st.warning(f'Snapshot store not readable: {exc}')
        return [],None


def combined_data(db:CompatibilityDB,live:list[dict])->pd.DataFrame:
    """Keep CSV baseline intact; replace only exactly matched vendor/product/VRM+OS cells."""
    frame=db.df.copy()
    for ver in ZOS_VERSIONS:
        frame[f'provenance_{ver}']='CSV baseline'
    if 'workbook_source' in frame.columns:
        frame.loc[frame['workbook_source'].str.startswith('AMXT Excel row'), 'provenance_3.2']='Excel AMXT'
    frame['live_details_count']=0
    for ver in ZOS_VERSIONS:
        for field in ('ptf_id_source','ptf_source_url','ptf_availability','ptf_last_scraped','ptf_verification'):
            frame[f'{field}_{ver}']=''
        ptf_col=VER[ver][1]
        frame[f'ptf_availability_{ver}']=frame.apply(
            lambda r:maintenance_availability(' '.join(str(r.get(c,'')) for c in
                ([ptf_col,'workbook_ptf_raw','workbook_comments'] if ver=='3.2' else [ptf_col]))),axis=1)
        frame[f'ptf_id_source_{ver}']='Workbook/CSV baseline'
        frame[f'ptf_source_url_{ver}']=frame.get('link','')
        frame[f'ptf_verification_{ver}']='Baseline only; not live-verified'
    if not live:return frame
    # Merge conservative exact matches. Do not accidentally map two vendor releases.
    index={match_key(r['vendor'],r['product'],r['vrm']):i for i,r in frame.iterrows()}
    added=[]
    for r in live:
        if r['zos_version'] not in VER:continue
        col,ptf_col,*_=VER[r['zos_version']]
        k=match_key(r['vendor'],r['product'],r['vrm'])
        index_number=index.get(k)
        if index_number is None:
            # Include scraped rows that are absent from the original CSV.
            if k not in added:
                record={c:'' for c in frame.columns}
                record.update({'vendor':r['vendor'],'product':r['product'],'vrm':r['vrm'],'label':f"{r['vendor']} | {r['product']} | {r['vrm']}",
                               'link':r['source_url'],'data_status':'Live vendor snapshot','last_checked':'Snapshot'})
                for v in ZOS_VERSIONS:record[VER[v][0]]='Unverified';record[VER[v][1]]='Verify';record[f'provenance_{v}']='No baseline'
                frame=pd.concat([frame,pd.DataFrame([record])],ignore_index=True)
                index_number=len(frame)-1;index[k]=index_number;added.append(k)
            else:index_number=index[k]
        frame.at[index_number,col]=r['status']
        frame.at[index_number,f'provenance_{r["zos_version"]}']='Vendor snapshot'
        links=r.get('links') or []
        # Do not discard verified workbook values if a vendor's linked section was blocked.
        value, evidence = display_ptfs(r, frame.at[index_number,ptf_col])
        frame.at[index_number,ptf_col] = value
        version=r['zos_version']
        frame.at[index_number,f'ptf_source_url_{version}']=maintenance_source(r) or str(frame.at[index_number,'link'])
        frame.at[index_number,f'ptf_last_scraped_{version}']=str(r.get('captured_at') or '')
        if evidence.startswith('Live'):
            frame.at[index_number,f'ptf_id_source_{version}']='Broadcom linked detail'
            frame.at[index_number,f'ptf_verification_{version}']='Extracted IDs; maintenance applicability needs validation'
            frame.at[index_number,f'ptf_availability_{version}']=scraped_ptf_status(r)
        else:
            frame.at[index_number,f'ptf_id_source_{version}']='Workbook/CSV retained' if evidence.startswith('Existing') else 'No exact IDs extracted'
            frame.at[index_number,f'ptf_verification_{version}']='Live link partial; baseline retained' if evidence.startswith('Existing') else 'PTF IDs not verified'
        if evidence.startswith('Existing'):
            frame.at[index_number,f'provenance_{r["zos_version"]}'] = 'Vendor status + workbook maintenance'
        frame.at[index_number,'live_details_count']=int(frame.at[index_number,'live_details_count'] or 0)+len(links)
    return frame


def status_counts(d,ver):
    c=VER[ver][0]
    return d[c].value_counts().reindex(['Yes','No','In Progress','Unverified','N/A','Unknown'],fill_value=0)


def format_links(r):
    links=r.get('links',[])
    ptfs=', '.join(r.get('ptfs',[]))
    return ptfs or ('PTF link available; identifiers not extracted' if r.get('ptf_links_present') else 'No PTF link in this cell')


def detail_frame(rows):
    return pd.DataFrame([{'Type':l['type'],'PTF IDs':', '.join(l['ptfs']),'APAR IDs':', '.join(l['apars']),
        'FIXCAT':', '.join(l['fixcats']),'USERMOD':', '.join(l.get('usermods',[])),'SYSMOD':', '.join(l.get('sysmods',[])),'FMIDs':', '.join(l.get('fmids',[])),'Extraction':l['extraction_status'],'Source URL':l['url'],'Extracted text':l['text']}
        for r in rows for l in r.get('links',[])])


def excel_bytes(data):
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine='openpyxl') as w:
        for name,df in data.items():
            copy=df.copy()
            for col in copy.columns:
                copy[col]=copy[col].map(lambda v:json.dumps(v) if isinstance(v,(dict,list)) else v)
            copy.to_excel(w,sheet_name=name[:31],index=False)
            ws=w.sheets[name[:31]]
            ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:
                cell.font=cell.font.copy(bold=True)
            for col in ws.columns:
                letter=col[0].column_letter
                ws.column_dimensions[letter].width=min(57,max(13,max(len(str(c.value or '')) for c in list(col)[:150])+2))
    return buf.getvalue()


def page_header(title,subtitle):
    st.markdown(f'<div class="brand"><h1>{title}</h1><p>{subtitle}</p></div>',unsafe_allow_html=True)


base=base_db()
workbook_sheets, workbook_amxt, workbook_urls = workbook()
records,info=source_records()
all_df=combined_data(base,[{**r,'captured_at':info['captured_at']} for r in records] if info else records)
from deep_app_bridge_v13 import merge_verified_deep
all_df=merge_verified_deep(all_df,BASE/'exports'/'deep'/'all_vendor_extracted_compatibility.csv')
db=CompatibilityDB(all_df)

with st.sidebar:
    st.markdown('### ◈ z/OS Intelligence')
    st.caption('COMPATIBILITY CONTROL CENTER')
    page=st.radio('Workspace',PAGE_NAMES,label_visibility='collapsed')
    st.divider()
    zos=st.selectbox('Target z/OS release',ZOS_VERSIONS,key='global_zos')
    st.metric('Vendor records',len(db.df))
    st.metric('Vendors in workbook',workbook_amxt['Vendor'].nunique())
    st.caption('Broadcom snapshot: '+(str(info['captured_at'])[:19]+' UTC' if info else 'Not yet collected'))
    st.divider()
    st.caption('Sources: reference ISV workbook (AMXT / Sheet1 / Sheet2), historic CSV baseline and optional Broadcom live snapshot. z/OS 3.1 is never inferred from 3.2.')


if page=='Overview':
    page_header('Compatibility Overview','Mainframe software intelligence · vendor statements, maintenance and upgrade risks')
    if info:st.success(f'Latest Broadcom snapshot: {info["row_count"]} version-specific records collected {info["captured_at"][:19]} UTC')
    else:st.info('Displaying the supplied ISV Excel workbook plus historic CSV baseline. To collect current Broadcom maintenance evidence, open Source Monitor and select Refresh Broadcom.')
    deep_root=BASE/'exports'/'deep'
    status_path=deep_root/'auto_scrape_status.json'
    if status_path.exists():
        try:
            state=json.loads(status_path.read_text(encoding='utf-8'))
            state_label=state.get('state','Unknown')
            stamp=state.get('timestamp_utc','')[:19]
            if state_label=='Completed':st.caption(f'● Vendor crawler: last run completed {stamp} UTC. Open Extraction Coverage to verify usable results.')
            elif state_label in ('Scraping','Running'):st.info('Vendor crawler is running in the background. Existing results remain visible.')
            elif state_label in ('Failed','Partial'):st.warning(f'Vendor crawler: {state_label}. Check Extraction Coverage for the last run details.')
        except (ValueError,OSError):pass
    stats=db.summarize(db.df,zos)
    cols=st.columns(6)
    for col,(lab,num) in zip(cols,[('Products',stats['total']),('Compatible',stats['yes']),('Not compatible',stats['no']),('In progress',stats['in_progress']),('Unverified',stats['unverified']),('Require PTF review',stats['ptf'])]):col.metric(lab,num)
    a,b=st.columns(2)
    with a:
        st.subheader('Compatibility statuses')
        st.bar_chart(status_counts(db.df,zos).rename('Records'),height=320)
    with b:
        st.subheader('Vendor coverage')
        st.bar_chart(db.df.groupby('vendor').size().rename('Products'),height=320)
    st.subheader('Recent source jobs')
    history=jobs(5,DB_PATH)
    if history:st.dataframe(pd.DataFrame(history),hide_index=True,use_container_width=True)
    else:st.caption('No source jobs have been recorded yet. Automatic refresh runs in a background worker when due.')
    st.subheader('Important distinctions')
    st.write('**Compatible:** the vendor indicates support for that z/OS release. **Maintenance requirements:** linked PTFs/APARs/prerequisites may still be needed. **Upgrade ready:** cannot be confirmed until you compare these with installed mainframe maintenance.')

elif page=='Comparative Matrix':
    page_header('z/OS 3.1 vs 3.2','Compare only explicitly sourced statuses — do not infer 3.1 from 3.2')
    st.info('The supplied AMXT Excel sheet contains **z/OS 3.2 only**. z/OS 3.1 is shown only where an independent CSV baseline or a successfully scraped vendor snapshot provides it. A blank 3.1 is not equivalent to Yes.')
    a,b=st.columns([1,2])
    vv=a.multiselect('Vendors',sorted(db.df.vendor.unique()),default=sorted(db.df.vendor.unique()))
    qq=b.text_input('Search product or release',key='compare_query')
    compare=db.df[db.df.vendor.isin(vv)].copy()
    if qq:compare=compare[compare.apply(lambda row:qq.casefold() in ' '.join(row.astype(str)).casefold(),axis=1)]
    cols=['vendor','product','vrm','zos31','ptf_required_31','zos32','ptf_required','workbook_source','link']
    compare=compare[cols].rename(columns={'vendor':'Vendor','product':'Product','vrm':'Version','zos31':'z/OS 3.1','ptf_required_31':'3.1 PTFs','zos32':'z/OS 3.2','ptf_required':'3.2 PTFs','workbook_source':'AMXT provenance','link':'Verify source'})
    st.dataframe(compare,hide_index=True,use_container_width=True,height=520,column_config={'Verify source':st.column_config.LinkColumn('Verify source')})
    st.download_button('Download comparison CSV',compare.to_csv(index=False).encode(),file_name='zos_31_32_comparison.csv',mime='text/csv')

elif page=='Compatibility Matrix':
    page_header('Compatibility Matrix','ISV workbook + historic CSV baselines; matched Broadcom rows use the latest successful live snapshot')
    a,b,c,d=st.columns([1,1,1,2])
    vend=a.multiselect('Vendors',sorted(db.df['vendor'].dropna().unique()),default=sorted(db.df['vendor'].dropna().unique()))
    ver=b.selectbox('Target release',ZOS_VERSIONS,index=ZOS_VERSIONS.index(zos))
    status=c.multiselect('Status',['Yes','No','In Progress','Unverified','N/A','Unknown'])
    q=d.text_input('Search product / version / PTF',placeholder='ACF2, Endevor, Db2, LU15603 ...')
    filtered=db.filter(vendors=vend,status=status or None,search=q,version=ver)
    summary=db.summarize(filtered,ver)
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Matching records',len(filtered));c2.metric('Compatible',summary['yes']);c3.metric('Not compatible',summary['no']);c4.metric('Unverified',summary['unverified'])
    fields=['vendor','product','vrm',VER[ver][0],VER[ver][1],f'provenance_{ver}','workbook_source','workbook_status_raw','workbook_ptf_raw','eos_date','latest_version','link']
    # Explicit PTF identifiers are shown separately, as in the reference PTF worklist.
    filtered = filtered.copy()
    # Do not union current vendor-required PTFs with historical workbook notes.
    # Show workbook-mentioned IDs separately so unavailable/superseded IDs remain auditable.
    filtered['Extracted PTF IDs'] = filtered.apply(
        lambda row: ', '.join(ptf_ids(row.get(VER[ver][1],''))) if
        str(row.get(f'ptf_id_source_{ver}','')).startswith('Broadcom linked') else
        ', '.join(ptf_ids(' '.join(str(row.get(c,'')) for c in
            ([VER[ver][1],'workbook_ptf_raw','workbook_comments'] if ver=='3.2' else [VER[ver][1]])))),axis=1)
    filtered['Workbook-mentioned PTF IDs'] = filtered.apply(
        lambda row: ', '.join(ptf_ids(' '.join(str(row.get(c,'')) for c in
            ['workbook_ptf_raw','workbook_comments']))) if ver=='3.2' else '',axis=1)
    filtered['PTF evidence'] = filtered.apply(
        lambda row: 'Identifiers listed' if row['Extracted PTF IDs'] else
          ('PTF / maintenance reference' if 'PTF' in str(row.get(VER[ver][1],'')).upper() else 'Not verified'), axis=1)
    filtered['PTF availability'] = filtered[f'ptf_availability_{ver}'].fillna('').replace('',UNKNOWN_PTF)
    filtered['PTF ID source'] = filtered[f'ptf_id_source_{ver}']
    filtered['PTF source URL'] = filtered[f'ptf_source_url_{ver}']
    filtered['Last live scrape (UTC)'] = filtered[f'ptf_last_scraped_{ver}']
    filtered['PTF verification'] = filtered[f'ptf_verification_{ver}']
    fields += ['Extracted PTF IDs','Workbook-mentioned PTF IDs','PTF evidence','PTF availability','PTF ID source','PTF source URL','Last live scrape (UTC)','PTF verification']
    st.dataframe(filtered[fields].rename(columns={'vendor':'Vendor','product':'Product','vrm':'Release',VER[ver][0]:'Compatibility',VER[ver][1]:'PTF required',f'provenance_{ver}':'Evidence','workbook_source':'Workbook evidence','workbook_status_raw':'Original 3.2 statement','workbook_ptf_raw':'Original 3.2 maintenance','eos_date':'EOS date','latest_version':'Latest version','link':'Vendor source'}),hide_index=True,use_container_width=True,height=450,column_config={'Vendor source':st.column_config.LinkColumn('Vendor source')})
    st.download_button('⬇ Download filtered Excel',excel_bytes({'Compatibility':filtered[fields]}),file_name=f'zos_{ver}_filtered.xlsx',mime=XLSX_MIME)
    if records:
        with st.expander('View scraped-only matrix rows / maintenance details'):
            rows=[r for r in records if r['zos_version']==ver and r['vendor'] in vend]
            st.dataframe(pd.DataFrame([{'Product':r['display_name'],'Status':r['status'],'PTFs':', '.join(r['ptfs']),'PTF links':bool(r.get('ptf_links_present')) or any('PTF' in str(l.get('type','')).upper() for l in r.get('links',[])),'Source':r['source_url']} for r in rows]),use_container_width=True,hide_index=True)

elif page=='PTF Intelligence':
    page_header('PTF Intelligence','Exact PTF identifiers, linked instructions, fix categories and traceable evidence')
    st.subheader('Excel AMXT — PTFs / USERMODs worklist')
    source_ptfs=workbook_worklist(workbook_amxt)
    ptf_search=st.text_input('Search the workbook PTF worklist',key='ptf_workbook_search',placeholder='LU17113, Broadcom, DB2 ...')
    if ptf_search:
        source_ptfs=source_ptfs[source_ptfs.astype(str).apply(lambda r:r.str.contains(re.escape(ptf_search),case=False,na=False).any(),axis=1)]
    st.caption('Original AMXT maintenance entries; these are workbook assertions, not verified live PTF installation status.')
    st.dataframe(source_ptfs,hide_index=True,use_container_width=True,height=340,column_config={'Verification Link':st.column_config.LinkColumn('Verification Link')})
    st.download_button('Download AMXT maintenance worklist',source_ptfs.to_csv(index=False).encode(),file_name='AMXT_maintenance_worklist.csv',mime='text/csv')
    st.divider()
    st.subheader('Combined PTF / USERMOD worklist')
    work = db.df.copy()
    work['PTF IDs'] = work.apply(lambda row: ', '.join(ptf_ids(row.get('ptf_required',''))) if
        str(row.get('ptf_id_source_3.2','')).startswith('Broadcom linked') else
        ', '.join(ptf_ids(' '.join(str(row.get(c,'')) for c in
            ['ptf_required','workbook_ptf_raw','workbook_comments']))), axis=1)
    work['Workbook-mentioned PTF IDs'] = work.apply(lambda row:', '.join(ptf_ids(
        str(row.get('workbook_ptf_raw',''))+' '+str(row.get('workbook_comments','')))),axis=1)
    work['PTF / Usermod details'] = work['ptf_required']
    work['PTF availability'] = work['ptf_availability_3.2'].fillna('').replace('',UNKNOWN_PTF)
    work['Installation status (AMXT-reported)'] = work.apply(lambda r:installation_status(' '.join(str(r.get(c,'')) for c in ['workbook_ptf_raw','workbook_comments'])),axis=1)
    work['PTF ID source'] = work['ptf_id_source_3.2']
    work['PTF source URL'] = work['ptf_source_url_3.2']
    work['Last live scrape (UTC)'] = work['ptf_last_scraped_3.2']
    work['PTF verification'] = work['ptf_verification_3.2']
    work = work[(work['PTF IDs']!='') | work['PTF / Usermod details'].str.contains(
        r'PTF|USERMOD|SYSMOD|^Yes',case=False,regex=True,na=False)]
    show_cols=['vendor','product','vrm','zos32','PTF IDs','Workbook-mentioned PTF IDs','PTF / Usermod details','PTF availability','Installation status (AMXT-reported)','PTF ID source','PTF source URL','Last live scrape (UTC)','PTF verification','workbook_comments','link']
    work=work[show_cols].rename(columns={'vendor':'Vendor','product':'Product','vrm':'Version',
        'zos32':'z/OS 3.2 Status','workbook_comments':'Comments','link':'Verification Link'})
    st.dataframe(work,hide_index=True,use_container_width=True,height=330,
        column_config={'Verification Link':st.column_config.LinkColumn('Verification Link'),'PTF source URL':st.column_config.LinkColumn('PTF source URL')})
    st.download_button('⬇ Download combined PTF worklist',work.to_csv(index=False).encode('utf-8-sig'),
        file_name='zos_ptf_worklist.csv',mime='text/csv')
    st.divider()
    st.subheader('Live Broadcom source evidence')
    if not records:
        st.info('No live maintenance snapshot exists yet. Open Source Monitor → Refresh Broadcom to fetch additional source PTF and Additional Information details.')
    else:
        options=sorted({(r['product'],r['vrm']) for r in records})
        pair=st.selectbox('Product / release',options,format_func=lambda t:f'{t[0]} {t[1]}')
        version=st.selectbox('Target z/OS',ZOS_VERSIONS,index=ZOS_VERSIONS.index(zos))
        sel=[r for r in records if (r['product'],r['vrm'])==pair and r['zos_version']==version]
        if sel:
            r=sel[0]
            a,b,c,d=st.columns(4)
            a.metric('Compatibility',r['status']);b.metric('PTFs identified',len(r['ptfs']))
            c.metric('Detail links',len(r['links']));d.metric('Evidence',r['evidence_status'])
            t1,t2,t3,t4=st.tabs(['Required PTFs','Additional Information','OS Comparison','Source Evidence'])
            with t1:
                if r['ptfs']:st.code(', '.join(r['ptfs']),language=None)
                elif r.get('ptf_links_present') or any('PTF' in str(l.get('type','')).upper() for l in r.get('links',[])):st.warning('PTF link exists, but exact identifiers could not be verified in the extracted text.')
                else:st.info('No PTF link listed for this product and OS. That is not proof that maintenance is unnecessary.')
                st.caption('PTF identifiers must be checked against vendor instructions and installed SMP/E records.')
                df=detail_frame([r]);subset=df[df['Type'].str.contains('PTF',case=False,na=False)] if not df.empty else df
                if not subset.empty:st.dataframe(subset,hide_index=True,use_container_width=True,column_config={'Source URL':st.column_config.LinkColumn('Source URL')})
            with t2:
                df=detail_frame([r]);subset=df[~df['Type'].str.contains('PTF',case=False,na=False)] if not df.empty else df
                if subset.empty:st.info('No linked additional-information content extracted for this combination.')
                else:
                    for _,entry in subset.iterrows():
                        with st.expander(f"{entry['Type']} · {entry['Extraction']}"):
                            st.write(entry['Extracted text'] or 'Link could not be resolved.');st.link_button('Open original reference',entry['Source URL'])
            with t3:
                comparison=[x for x in records if (x['product'],x['vrm'])==pair]
                st.dataframe(pd.DataFrame([{'z/OS':x['zos_version'],'Compatibility':x['status'],'PTFs':', '.join(x['ptfs']),'Detail links':len(x['links']),'Evidence':x['evidence_status']} for x in comparison]),use_container_width=True,hide_index=True)
            with t4:
                st.write('**Source:**',r['source_url']);st.write('**Last snapshot:**',info['captured_at'])
                st.json({'product':r['product'],'vrm':r['vrm'],'zos_version':r['zos_version'],'status':r['status'],'ptfs':r['ptfs'],'evidence_status':r['evidence_status']},expanded=False)
                for link in r['links']:
                    with st.expander(link['type']+' · '+link['extraction_status']):
                        st.write(link['text'] or 'Not readable');st.link_button('Open vendor evidence',link['url'])
            st.download_button('⬇ Download maintenance Excel',excel_bytes({'Details':detail_frame([r]),'Selected record':pd.DataFrame([r]).drop(columns=['links','ptfs'],errors='ignore')}),file_name='zos_maintenance_details.xlsx',mime=XLSX_MIME)

elif page=='Source Monitor':
    page_header('Source Monitor','Controlled collection, vendor evidence coverage, refresh outcomes and detailed logs')
    st.warning('A refresh makes live network requests from the running server. Your first run may encounter rate limits, blocked pages, redirects or changed HTML. The previous successful snapshot will be preserved on failure.')
    st.write('**Broadcom matrix source:**');st.link_button('Open Broadcom matrix',BROADCOM_URL)
    st.caption('The crawler extracts the main product table, resolves internal PTF and Additional Information anchors, and follows approved off-page vendor documents when enabled.')
    fetch_external=st.checkbox('Follow approved external detail pages (slower)',value=False,help='Local anchor links are always expanded. Separate pages can require additional requests.')
    if st.button('↻ Refresh Broadcom now',type='primary'):
        try:
            with st.spinner('Fetching Broadcom matrix, expanding maintenance references, and checking the extracted data...'):
                fresh,stats=crawl_broadcom(follow_external=fetch_external)
                if len(fresh)<30:raise ValueError('Unusually few rows: rejected to avoid publishing incomplete results')
                snap=save(fresh,stats,DB_PATH)
            st.success(f'Snapshot #{snap} published: {stats["records"]} version-specific rows, {stats["links"]} detail links. Open any page to see refreshed data.')
            st.rerun()
        except Exception as exc:
            try: record_error('Broadcom',str(exc),DB_PATH)
            except Exception: pass  # still report the original scrape error
            st.error(f'Refresh failed: {type(exc).__name__}: {exc}. Previous successful data was retained.')
    if info:
        st.write(f'**Last good snapshot:** {info["captured_at"]} UTC · {info["row_count"]} records')
        with st.expander('Extraction statistics'):st.json(json.loads(info['stats_json']))
    if records:
        st.subheader('Live PTF extraction coverage')
        with_ptf_link=[r for r in records if link_present(r)]
        with_ids=[r for r in with_ptf_link if maintenance_ids(r.get('ptfs',[]))]
        a,b,c=st.columns(3)
        a.metric('PTF-linked OS records',len(with_ptf_link))
        b.metric('Links with extracted PTF IDs',len(with_ids))
        c.metric('Links needing further review',len(with_ptf_link)-len(with_ids))
        ptf_monitor=pd.DataFrame([{
            'Product':r.get('display_name') or (r.get('product','')+' '+r.get('vrm','')),
            'z/OS':r.get('zos_version'),
            'PTF identifiers':', '.join(maintenance_ids(r.get('ptfs',[]))),
            'PTF status':scraped_ptf_status(r),
            'PTF verification':'IDs extracted; applicability not independently confirmed' if maintenance_ids(r.get('ptfs',[])) else 'Incomplete extraction',
            'Source':maintenance_source(r),
            'Last successful scrape (UTC)':info['captured_at'] if info else ''
        } for r in with_ptf_link])
        if not ptf_monitor.empty:
            st.dataframe(ptf_monitor,hide_index=True,use_container_width=True,height=290,
                column_config={'Source':st.column_config.LinkColumn('Source')})
            st.download_button('⬇ Download scraped PTF results',ptf_monitor.to_csv(index=False).encode('utf-8-sig'),
                file_name='broadcom_scraped_ptfs.csv',mime='text/csv')
    st.divider()
    st.subheader('All-vendor source audit — public references')
    st.info('This checks approved official vendor HTML/PDF links and may follow up to two clearly labelled compatibility documents per vendor. Product/OS mentions are evidence, **not** compatibility certification. Broadcom retains its dedicated crawler. Login/MFA pages are not bypassed.')
    vendor_options=sorted(set(base.df['vendor'].dropna().astype(str)) | set(workbook_amxt['Vendor'].map(lambda v: str(v))))
    from workbook_data import vendor_name
    vendor_options=sorted(set(vendor_name(v) for v in vendor_options if str(v).strip()))
    chosen_vendors=st.multiselect('Vendors to check',vendor_options,default=[v for v in ['IBM','BMC','Rocket','Precisely','ASG'] if v in vendor_options],key='vendor_audit_choice')
    col_a,col_b=st.columns(2)
    urls_per=col_a.slider('Maximum source URLs per vendor',1,5,2)
    audit_timeout=col_b.slider('Per-source timeout (seconds)',5,25,10)
    source_file=st.file_uploader('Optional: supply more official vendor URLs (CSV columns: Vendor, URL)',type=['csv'],key='vendor_source_urls')
    additional=[]
    if source_file is not None:
        try:
            source_data=pd.read_csv(source_file,dtype=str,keep_default_na=False)
            if not {'Vendor','URL'}.issubset(source_data.columns):
                st.error('URL CSV must contain exactly named columns Vendor and URL.')
            else:
                additional=source_data[['Vendor','URL']].head(150).to_dict('records')
                st.caption(f'{len(additional)} submitted vendor URL(s); private, authentication, or wrong-vendor URLs will be ignored.')
        except Exception as e:st.error(f'Could not read URL CSV: {e}')
    sources_map=sources_for_vendors(workbook_amxt,workbook_urls,chosen_vendors,urls_per,additional)
    planned=sum(len(x) for x in sources_map.values())
    st.caption(f'{len(chosen_vendors)} vendor(s), {planned} initial source URLs planned; up to two explicit compatibility documents may be discovered for each vendor. Run small batches to avoid server timeouts.')
    if st.button('↻ Check selected vendor sources',disabled=not bool(chosen_vendors)):
        with st.spinner('Reading approved public vendor pages and recording evidence...'):
            audit_rows=audit_all(workbook_amxt,workbook_urls,base.df,chosen_vendors,urls_per,audit_timeout,extra_sources=additional)
            n=save_vendor_audits(audit_rows,DB_PATH)
        st.success(f'{n} source audit results saved. Pages requiring authentication or failing extraction remain clearly labeled.')
        st.rerun()
    with st.expander('Import an authorized vendor HTML/PDF reference (for blocked sites)'):
        st.caption('Use a document you are authorized to download. Uploaded sources are labelled as operator supplied, not live-verified. No authentication bypass is attempted.')
        upload_vendor=st.selectbox('Document vendor',vendor_options,key='uploaded_doc_vendor')
        upload_doc=st.file_uploader('Vendor HTML or PDF document (maximum 2 MB)',type=['html','htm','pdf'],key='vendor_offline_document')
        upload_url=st.text_input('Official source URL (optional, for traceability)',key='vendor_document_source_url')
        if st.button('Extract evidence from document',disabled=upload_doc is None):
            try:
                payload=upload_doc.getvalue()
                vendor_rows=base.df[base.df['vendor']==upload_vendor].to_dict('records')
                imported=audit_uploaded_document(upload_vendor,upload_doc.name,payload,vendor_rows,upload_url.strip())
                save_vendor_audits([imported],DB_PATH)
                st.success(f'Document reviewed: {len(imported["assertions"])} structured observations and {len(imported["matches"])} contextual matches. Not live-certified.')
            except Exception as exc:
                st.error(f'Document extraction could not finish: {exc}')
    audit_history=vendor_audits(DB_PATH)
    if audit_history:
        report=pd.DataFrame(audit_history)
        latest_per_url=(report.sort_values('checked_at').drop_duplicates(['vendor','source_url'],keep='last'))
        verified_release_count=0
        from evidence_pipeline import latest_unique_observations
        for assertion in latest_unique_observations(audit_history):
            if 'Explicit vendor table: product, release' in str(assertion.get('evidence_level','')) and str(assertion.get('vrm','')).strip().casefold() not in ('','not stated','unknown'):
                verified_release_count+=1
        m1,m2,m3,m4=st.columns(4)
        m1.metric('Unique URLs checked',len(latest_per_url))
        m2.metric('Latest readable URLs',int((latest_per_url['state']=='Read').sum()))
        m3.metric('Latest blocked / missing',int((latest_per_url['state']!='Read').sum()))
        m4.metric('Explicit release claims for review',verified_release_count)
        st.caption('Release claims are source assertions pending human review, not verified installed compatibility or installed PTFs.')
        report['Evidence found']=report['matched_products']
        report['Maintenance IDs mentioned']=report['ptf_mentions']
        report['Structured observations']=report['assertions_json'].fillna('[]').map(lambda x:len(json.loads(x or '[]')))
        report['Access status']=report['state'].map(lambda x:'Readable' if x=='Read' else 'Blocked / missing')
        report['Verification']='Evidence only — check product/release'  
        cols=['vendor','state','Access status','source_url','checked_at','origin','Evidence found','Maintenance IDs mentioned','Structured observations','Verification','note']
        st.dataframe(report[cols].rename(columns={'vendor':'Vendor','state':'Result','source_url':'URL','checked_at':'Checked at','origin':'Source type','note':'Details'}),hide_index=True,use_container_width=True,height=360,column_config={'URL':st.column_config.LinkColumn('URL')})
        st.caption('Historical checks are listed here. A 403/401 response indicates restricted access, not incompatibility. Source-check timestamps do not constitute verified PTF extraction.')
        st.download_button('⬇ Download vendor source audit',report[cols].to_csv(index=False).encode('utf-8-sig'),file_name='vendor_source_audit.csv',mime='text/csv')
        with st.expander('Inspect exact source excerpts and mentioned PTF IDs'):
            with_mentions=report[report['matched_products']>0]
            if with_mentions.empty:st.caption('No source excerpts matched an exact product and z/OS release yet.')
            else:
                index=st.selectbox('Audit page',with_mentions.index.tolist(),format_func=lambda i: f"{report.at[i,'vendor']} — {report.at[i,'source_url']}")
                evidence=json.loads(report.at[index,'matches_json'])
                st.dataframe(pd.DataFrame([{'Product':r['product'],'VRM':r['vrm'],'OS mentions':', '.join(r['zos_mentions']),'PTF mentions':', '.join(r['ptf_ids']),'Excerpt':r['excerpt'],'Evidence':r['evidence_level']} for r in evidence]),hide_index=True,use_container_width=True)
        # Only the newest result for each vendor+source URL contributes observations.
        # Older audits remain available in the audit-history table.
        structured=latest_unique_observations(audit_history)
        if structured:
            st.subheader('Published vendor observations (product release must be verified)')
            st.warning('Observations can be explicit support-table cells, minimum-version requirements, maintenance mentions or release-unspecified announcements. Review evidence level; they are NOT silently merged into the compatibility matrix.')
            structured_df=pd.DataFrame(reconcile_observations(structured,base.df))
            st.dataframe(structured_df,hide_index=True,use_container_width=True,column_config={'source_url':st.column_config.LinkColumn('Official source')})
            st.caption('Latest observation per vendor/source only; audit history is retained above. No automatic compatibility override is performed.')
            st.download_button('⬇ Download structured source observations',structured_df.to_csv(index=False).encode('utf-8-sig'),file_name='vendor_published_observations.csv',mime='text/csv')
    else:st.caption('No vendor source audits have been run yet. Existing workbook entries remain visible across the other dashboard pages.')
    st.subheader('Product-by-product source coverage and missing evidence')
    st.caption('One row per existing inventory record. Vendor-domain links can be generic; they are not necessarily product-specific, and reading a URL does not verify product/release compatibility or installed PTFs. This is the acquisition worklist for all vendors, not additional scraped compatibility rows.')
    latest_observations=latest_unique_observations(audit_history) if audit_history else []
    coverage=product_source_worklist(base.df,audit_history,latest_observations)
    metrics=coverage_summary(coverage)
    a,b,c,d=st.columns(4)
    a.metric('Inventory rows',metrics.get('products',0))
    b.metric('Approved vendor-domain links',metrics.get('approved_vendor_references',0))
    c.metric('Missing/unapproved links',metrics.get('missing_approved_sources',0))
    d.metric('Exact-release claims for review',metrics.get('explicit_3_2_claims_for_review',0))
    cov_vendor=st.multiselect('Filter source worklist vendors',sorted(coverage['Vendor'].unique()),default=[],key='source_coverage_vendor')
    cov_status=st.selectbox('Source worklist filter',['All','Missing official source','Blocked source','Exact release evidence','Approved vendor-domain URL'],key='source_coverage_status')
    visible_cov=coverage.copy()
    if cov_vendor:visible_cov=visible_cov[visible_cov['Vendor'].isin(cov_vendor)]
    if cov_status=='Missing official source':visible_cov=visible_cov[visible_cov['Source status']!='Approved vendor-domain URL']
    elif cov_status=='Blocked source':visible_cov=visible_cov[visible_cov['Last URL check']=='Blocked / failed']
    elif cov_status=='Exact release evidence':visible_cov=visible_cov[visible_cov['Exact release observations']>0]
    elif cov_status=='Approved vendor-domain URL':visible_cov=visible_cov[visible_cov['Source status']=='Approved vendor-domain URL']
    st.dataframe(visible_cov,hide_index=True,use_container_width=True,height=300,
        column_config={'Approved vendor-domain URL':st.column_config.LinkColumn('Approved vendor-domain URL')})
    st.download_button('⬇ Download product-specific vendor source gaps',coverage.to_csv(index=False).encode('utf-8-sig'),
        file_name='vendor_product_source_worklist.csv',mime='text/csv')
    with st.expander('Check one product-specific official reference now'):
        st.caption('Runs a single controlled read for the selected inventory record, without general link crawling. A product mention is not an approval of compatibility or installed PTFs.')
        choices=coverage.index[coverage['Approved source URL'].ne('')].tolist()
        if choices:
            selection=st.selectbox('Inventory record',choices,format_func=lambda i: str(coverage.at[i,'Vendor'])+' · '+str(coverage.at[i,'Product'])+' · '+str(coverage.at[i,'Release']),key='coverage_one_product')
            selected_row=coverage.loc[selection]
            st.write('Official reference:',selected_row['Approved source URL'])
            if st.button('↻ Check this product reference',key='audit_one_product'):
                try:
                    unit={'product':selected_row['Product'],'vrm':selected_row['Release']}
                    source={'url':selected_row['Approved source URL'],'origin':'Selected inventory product reference','label':selected_row['Product']}
                    with st.spinner('Checking source and capturing product evidence...'):
                        found=audit_vendor(str(selected_row['Vendor']),[source],[unit],timeout=audit_timeout,follow_discovered=False)
                        save_vendor_audits(found,DB_PATH)
                    row=found[0]
                    if row['state']=='Read':
                        st.success(f"Source read: {len(row['assertions'])} structured observation(s), {len(row['matches'])} contextual product match(es). Review evidence before changing compatibility.")
                    else:st.warning(str(row['note']))
                except Exception as exc:st.error(f'Product source check failed: {exc}')
        else:st.info('No approved vendor-domain references exist. Add an official URL or upload an authorized document.')

    st.caption('To resolve gaps: add official product-specific URLs in Source Monitor, or upload authorized HTML/PDF evidence from blocked vendor portals. Product/release claims always require review.')
    source_summary=pd.DataFrame([{'Vendor':v,'Combined baseline rows':int((base.df['vendor']==v).sum()),'Live coverage':'Structured Broadcom crawler' if v=='Broadcom' else 'Public source audit; compatibility not inferred','Last Broadcom scrape':info['captured_at'] if v=='Broadcom' and info else 'Never'} for v in vendor_options])
    st.dataframe(source_summary,hide_index=True,use_container_width=True)
    st.subheader('Refresh job history')
    log=jobs(path=DB_PATH)
    if log:st.dataframe(pd.DataFrame(log),hide_index=True,use_container_width=True)
    else:st.caption('No crawl jobs performed yet.')
    st.subheader('Official vendor source directory')
    for v in vendor_options:
        with st.expander(v):
            for vendor,title,url,description in SOURCES:
                if vendor==v:st.markdown(f'[{title}]({url}) — {description}')


elif page=='Extraction Coverage':
    page_header('Extraction Coverage','Vendor-by-vendor source quality · exact compatibility evidence · remaining acquisition gaps')
    deep=BASE/'exports'/'deep'
    def _report(filename):
        path=deep/filename
        if not path.is_file():return pd.DataFrame()
        try:return pd.read_csv(path,dtype=str,keep_default_na=False)
        except (OSError,ValueError,UnicodeError):return pd.DataFrame()
    status_file=deep/'auto_scrape_status.json'
    auto_status={}
    if status_file.is_file():
        try:auto_status=json.loads(status_file.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    state=auto_status.get('state','Not started')
    stamp=auto_status.get('timestamp_utc','')[:19]
    if state=='Completed':st.success(f'Latest automatic source refresh completed · {stamp} UTC. Completed does not mean every vendor has verified data.')
    elif state in ('Scraping','Running'):st.info('Vendor collection is in progress. This page will show the last available reports until it finishes.')
    elif state in ('Failed','Partial'):st.warning(f'Automatic source refresh: {state}. {auto_status.get("message",auto_status.get("error","Review logs below."))}')
    else:st.info('No automatic crawl status found yet. The first collection starts when the application opens with network access.')
    vendors=_report('vendor_extraction_coverage.csv')
    products=_report('vendor_product_extraction_coverage.csv')
    quality=_report('vendor_source_quality.csv')
    failed=_report('vendor_failed_links.csv')
    facts=_report('vendor_document_facts.csv')
    if vendors.empty:
        st.warning('Vendor extraction coverage has not been generated. Baseline inventory is still available; this is not proof that all vendors were scraped.')
        st.metric('Vendors in baseline',len(set(base.df['vendor'].dropna())))
    else:
        for c in ('inventory_products','urls_checked','urls_read','compatibility_claims','ptf_claims','document_facts'):
            if c in vendors:vendors[c]=pd.to_numeric(vendors[c],errors='coerce').fillna(0).astype(int)
        verified=vendors[(vendors.get('compatibility_claims',pd.Series(0,index=vendors.index))>0)|(vendors.get('ptf_claims',pd.Series(0,index=vendors.index))>0)]
        k1,k2,k3,k4,k5=st.columns(5)
        k1.metric('Vendors tracked',len(vendors))
        k2.metric('Vendors with claims',len(verified))
        k3.metric('URLs checked',int(vendors['urls_checked'].sum()) if 'urls_checked' in vendors else 0)
        k4.metric('Compatibility claims',int(vendors['compatibility_claims'].sum()) if 'compatibility_claims' in vendors else 0)
        k5.metric('Published facts',int(vendors['document_facts'].sum()) if 'document_facts' in vendors else 0)
        st.caption('URL counts are crawl observations. Exact-release compatibility and PTF claims are separate. A published fact does not prove installed software is ready.')
        searchcol,filtercol=st.columns([2,1])
        q=searchcol.text_input('Find vendor',placeholder='IBM, Broadcom, BMC…',key='extraction_vendor_q')
        state_options=['All states']+sorted(set(vendors.get('coverage_state',pd.Series(dtype=str)).astype(str)))
        state_filter=filtercol.selectbox('Evidence filter',state_options,key='extraction_vendor_state')
        view=vendors.copy()
        if q:view=view[view['vendor'].astype(str).str.contains(re.escape(q),case=False,na=False)]
        if state_filter!='All states':view=view[view['coverage_state']==state_filter]
        st.subheader('Vendor extraction health')
        display=['vendor','inventory_products','urls_checked','urls_read','urls_failed','compatibility_claims','ptf_claims','document_facts','coverage_state','next_action']
        st.dataframe(view[[c for c in display if c in view.columns]],hide_index=True,use_container_width=True,height=420)
        st.download_button('Download vendor coverage',vendors.to_csv(index=False).encode('utf-8-sig'),file_name='vendor_extraction_coverage.csv',mime='text/csv')
        st.subheader('Source acquisition priorities')
        gaps=vendors[~vendors['vendor'].isin(verified['vendor'])]
        if len(gaps):st.warning(f'{len(gaps)} of {len(vendors)} vendors have no accepted exact compatibility or assigned PTF records. Prioritize the official product-specific sources listed below.')
        else:st.info('Every tracked vendor has at least one structured record. This does not prove that every product is covered.')
    if not products.empty:
        st.subheader('Inventory product coverage')
        a,b=st.columns([1,2]); selected=a.selectbox('Product vendor',['All']+sorted(products['vendor'].dropna().unique().tolist()),key='extraction_product_vendor')
        textq=b.text_input('Product or release',placeholder='Product name, version…',key='extraction_product_q')
        chosen=products.copy()
        if selected!='All':chosen=chosen[chosen['vendor']==selected]
        if textq:chosen=chosen[chosen[['product','release']].astype(str).agg(' '.join,axis=1).str.contains(re.escape(textq),case=False,na=False)]
        st.dataframe(chosen,hide_index=True,use_container_width=True,height=360,column_config={'source_url':st.column_config.LinkColumn('Official source')})
        st.download_button('Download product-level gaps',products.to_csv(index=False).encode('utf-8-sig'),file_name='vendor_product_extraction_coverage.csv',mime='text/csv')
    else:st.caption('Per-product extraction report will appear after the next successful collection.')
    left,right=st.columns(2)
    with left:
        st.subheader('Failed URLs')
        if not failed.empty:st.dataframe(failed,hide_index=True,use_container_width=True,height=280)
        else:st.caption('No failed URL report available.')
    with right:
        st.subheader('Document facts')
        if not facts.empty:st.dataframe(facts,hide_index=True,use_container_width=True,height=280)
        else:st.caption('No vendor document facts extracted yet.')
    with st.expander('Detailed source-quality observations'):
        if not quality.empty:st.dataframe(quality,hide_index=True,use_container_width=True,height=340)
        else:st.caption('No source quality report available.')
    st.caption('No authentication bypass is used. Sites that require login or prevent automated access are marked as gaps rather than marked compatible.')

elif page=='Change History':
    page_header('Change History','Track changed support statements and linked maintenance across successful source snapshots')
    history=changes(path=DB_PATH)
    if not info:st.info('Collect a first snapshot, then a second successful snapshot. Changes are reported only after comparisons between two real snapshots.')
    elif not history:st.info('No changes recorded. This may be the first snapshot or a repeat with identical information.')
    else:
        st.metric('Recorded changes',len(history))
        table=pd.DataFrame([{'Timestamp':r['captured_at'],'Key':r['row_key'],'Type':r['change_type']} for r in history])
        st.dataframe(table,hide_index=True,use_container_width=True)
        selected=st.selectbox('Inspect change',range(len(history)),format_func=lambda i:history[i]['row_key']+' ('+history[i]['change_type']+')')
        a,b=st.columns(2)
        with a:st.markdown('**Previous**');st.json(json.loads(history[selected]['before_json']) if history[selected]['before_json'] else {},expanded=True)
        with b:st.markdown('**Current**');st.json(json.loads(history[selected]['after_json']) if history[selected]['after_json'] else {},expanded=True)
        st.download_button('⬇ Export change log',excel_bytes({'Changes':table}),file_name='zos_changes.xlsx',mime=XLSX_MIME)

elif page=='Inventory Readiness':
    page_header('Inventory Readiness','Match existing mainframe products to vendor statements and maintenance obligations')
    target=st.selectbox('Target release',ZOS_VERSIONS,index=ZOS_VERSIONS.index(zos))
    up=st.file_uploader('Upload inventory (CSV / Excel: Vendor, Product, VRM)',type=['csv','xlsx'])
    labels=db.df['label'].tolist()
    selected=st.multiselect('Or select individual products',labels)
    chosen=db.df[db.df['label'].isin(selected)]
    misses=[]
    if up:
        try:
            inventory=pd.read_csv(up,dtype=str,keep_default_na=False) if up.name.lower().endswith('.csv') else pd.read_excel(up,dtype=str,keep_default_na=False)
            matched,misses=db.match_inventory(inventory)
            chosen=pd.concat([chosen,matched],ignore_index=True).drop_duplicates(subset=['vendor','product','vrm'])
        except Exception as exc:st.error(f'Inventory import error: {exc}')
    if chosen.empty:st.info('Select products or upload an inventory to analyze compatibility and possible PTF requirements.')
    else:
        stat=db.summarize(chosen,target);cs=st.columns(5)
        for c,(lab,val) in zip(cs,[('Matched',len(chosen)),('Compatible',stat['yes']),('Not compatible',stat['no']),('PTF review',stat['ptf']),('Unverified',stat['unverified'])]):c.metric(lab,val)
        result=to_output(chosen,version=target)
        result['Migration readiness']='Not confirmed — installed PTFs not provided'
        st.dataframe(result,hide_index=True,use_container_width=True,height=400)
        if stat['no']:st.error('One or more products are not compatible with the target z/OS release.')
        if stat['ptf']:st.warning('Vendor-reported PTF requirements must be checked against installed SMP/E service.')
        if stat['unverified'] or stat['in_progress']:st.warning('Some products have no confirmed vendor support statement for the target release.')
        st.download_button('⬇ Download inventory review',excel_bytes({'Assessment':result,'Unmatched':pd.DataFrame({'Issue':misses})}),file_name='zos_inventory_review.xlsx',mime=XLSX_MIME)
    for msg in misses:st.caption('⚠ '+msg)

elif page=='AI Assistant':
    page_header('AI Assistant','Evidence-grounded answers from the compatibility database with optional watsonx.ai')
    st.caption('Without watsonx credentials the application provides retrieval results instead of generating unsupported answers.')
    samples=['What Broadcom products are not compatible with z/OS 3.2?','Does ACF2 16.0 need PTFs?','Which products are still unverified?']
    question=st.text_input('Ask about compatibility or maintenance',placeholder=samples[1])
    k=st.slider('Retrieve matching records',5,30,12)
    if question:
        hits=RagIndex.build(db.df).retrieve(question,k)
        if hits.empty:st.warning('No matching rows found. Try vendor, product or release.')
        else:
            if watsonx_configured():
                try:st.markdown(generate_answer(question,hits))
                except Exception as exc:st.warning('AI answer unavailable; displaying evidence rows instead.')
            else:st.info('Showing matching evidence. Set WATSONX_APIKEY and WATSONX_PROJECT_ID for written answers.')
            st.dataframe(to_output(hits,version=zos),hide_index=True,use_container_width=True)
            if records:
                st.caption('Detailed PTF evidence is available on the PTF Intelligence page. AI text may be incomplete; always check original vendor instructions.')



elif page=='Workbook Explorer':
    page_header('Reference Workbook Explorer','Inspect the original three Excel sheets without losing any source columns or manual notes')
    sheet=st.selectbox('Choose original worksheet',list(workbook_sheets),index=list(workbook_sheets).index('AMXT'))
    raw=workbook_sheets[sheet].copy()
    st.caption(f'Source: {ISV_NAME} · {sheet} · {len(raw):,} data rows · {len(raw.columns)} columns. Original values are preserved.')
    if sheet=='AMXT':
        a,b,c=st.columns(3)
        a.metric('Rows with vendor + product',len(workbook_amxt))
        b.metric('Original maintenance cells populated',sum(bool(str(x).strip()) for x in workbook_amxt['If Yes, PTF Required?']))
        c.metric('Verification URL cells',sum(str(x).startswith(('https://','http://')) for x in workbook_amxt['Link to verify compatibility report']))
        st.subheader('PTFs & USERMODs worklist — original source values')
        worklist=workbook_worklist(workbook_amxt)
        st.dataframe(worklist,use_container_width=True,hide_index=True,height=350,column_config={'Verification Link':st.column_config.LinkColumn('Verification Link')})
        st.download_button('Export PTF worklist',worklist.to_csv(index=False).encode(),file_name='AMXT_PTF_worklist.csv',mime='text/csv')
    elif sheet=='Sheet1':
        st.info('Vendor website directory and access notes. A missing URL is not proof of public access. Authentication and MFA are never bypassed.')
    else:
        st.info('Original Sheet2 inventory is retained as a separate historical worksheet; it is not silently treated as current z/OS 3.2 verification.')
    q=st.text_input('Search all columns on this sheet',key='source_sheet_search')
    if q:raw=raw[raw.astype(str).apply(lambda r:r.str.contains(re.escape(q),case=False,na=False).any(),axis=1)]
    st.dataframe(raw,use_container_width=True,hide_index=True,height=520)
    st.download_button('Export selected sheet CSV',raw.to_csv(index=False).encode(),file_name=f'ISV_{sheet}.csv',mime='text/csv')

st.divider()
st.caption('z/OS Compatibility Intelligence · Open vendor sources for authoritative verification · Data is not a guarantee that installed maintenance is sufficient.')
