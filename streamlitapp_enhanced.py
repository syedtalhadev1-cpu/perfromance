import os, html
from textwrap import dedent
from datetime import date
import pyodbc
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

from dashboard_model import (
    clean_rows, compute_kpis, employee_summary,
    get_important_projects, load_company_data,
    load_company_master, load_important_project_data, project_details,
)
from Emodel import (
    clean_timeline_rows,
    get_employee_project_details,
    get_employee_timeline_dashboard,
    get_important_projects as get_employee_important_projects,
    load_important_project_data as load_employee_important_project_data,
    get_past_3_months_status_trend,
    load_employee_timeline,
)
from pmodel import ProjectDataProcessor
from summarize import summarize_dashboard
from weekly import generate_weekly_report_pdf

load_dotenv()
SERVER=os.getenv('DB_SERVER'); DATABASE=os.getenv('DB_DATABASE')
USERNAME=os.getenv('DB_USERNAME'); PASSWORD=os.getenv('DB_PASSWORD')
CONN_STR=(f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};"
          f"DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};")

st.set_page_config(page_title='Performance Intelligence', page_icon='📊', layout='wide')

# ============================================================
# THEME STYLING
# ============================================================
st.markdown("""
    <style>
        :root {
            --bg: var(--background-color);
            --sidebar: var(--secondary-background-color);
            --panel: var(--secondary-background-color);
            --p2: var(--background-color);
            --border: color-mix(in srgb, var(--text-color) 18%, var(--background-color));
            --text: var(--text-color);
            --muted: var(--text-color);
            color-scheme: light dark;
            --teal: #2dd9c7;
            --indigo: #6e7cf6;
            --mint: #4ade9a;
            --amber: #f5b84e;

            --coral: #f0685c;
            --notice-bg: var(--secondary-background-color);
            --notice-text: var(--text-color);
        }

        [data-testid="stAppViewContainer"], [data-testid="stApp"] { background-color: var(--bg) !important; }
        [data-testid="stSidebar"], [data-testid="stSidebarContent"] { background-color: var(--sidebar) !important; border-right: 1px solid var(--border); }
        [data-testid="stHeader"], [data-testid="stToolbar"] { background: var(--bg) !important; }
        [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"],
        .panel, .focus-card, .timeline-item { background: var(--panel) !important; border: 1px solid var(--border) !important; }
        .stMarkdown, .stText, label, p, [data-testid="stMetricLabel"], [data-testid="stMetricValue"] { color: var(--text) !important; }
        [data-testid="stRadio"] label, [data-testid="stRadio"] label p,
        [data-testid="stSelectbox"] label, [data-testid="stDateInput"] label,
        [data-testid="stSlider"] label { color: var(--text) !important; opacity: 1 !important; }
        [data-testid="stRadio"] input[type="radio"] { accent-color: var(--teal) !important; }
        [data-testid="stRadio"] [role="radio"] { border-color: var(--muted) !important; }
        [data-testid="stRadio"] [role="radio"][aria-checked="true"] { border-color: var(--teal) !important; background-color: var(--teal) !important; }
        input, textarea, [data-baseweb="select"] > div, [data-testid="stDateInput"] input {
            background-color: var(--panel) !important;
            color: var(--text) !important;
            border: 1px solid var(--border) !important;
        }
        [data-testid="stSlider"] [role="slider"] { background: var(--teal) !important; border-color: var(--teal) !important; }
        [data-testid="stAlert"] { background-color: var(--notice-bg) !important; color: var(--notice-text) !important; border-color: var(--border) !important; }
        button { color: var(--text) !important; background: var(--panel) !important; border: 1px solid var(--border) !important; }
        .block-container { max-width: 1500px; padding-top: 28px; padding-bottom: 50px; }
        
        .dashboard-header { display: flex; justify-content: space-between; align-items: end; margin-bottom: 22px; }
        .eyebrow, .section-title, .panel-label { color: var(--muted); font-size: 10.5px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
        .header-title { color: var(--text); font-size: 28px; font-weight: 750; margin-top: 4px; }
        .header-sub { color: var(--muted); font-size: 12px; margin-top: 4px; }
        .live { color: var(--mint); font-size: 11px; font-weight: 700; }
        
        .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 15px; padding: 19px; }
        .ai-copy { color: var(--text); font-size: 13px; line-height: 1.7; max-height: 220px; overflow: auto; }
        
        .kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
        .kpi-card {
            background: var(--p2);
            border: 1px solid color-mix(in srgb, var(--text-color) 16%, var(--background-color)) !important;
            border-radius: 12px;
            padding: 14px;
            min-height: 105px;
        }
        .kpi-icon { font-size: 15px; margin-bottom: 9px; }
        .kpi-value { color: var(--text); font-size: 23px; font-weight: 750; }
        .kpi-label { color: var(--muted); font-size: 10.5px; margin-top: 7px; }
        
        .section-title { margin: 25px 0 12px; color: var(--text); }
        .chart-title { color: var(--text); font-size: 13px; font-weight: 650; margin-bottom: 7px; }
        
        .focus-card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px; min-height: 140px; }
        .danger { border-top: 2px solid var(--coral); }
        .warning { border-top: 2px solid var(--amber); }
        .info { border-top: 2px solid var(--indigo); }
        
        .focus-top { display: flex; justify-content: space-between; color: var(--muted); font-size: 9.5px; text-transform: uppercase; }
        .focus-name { color: var(--text); font-size: 14px; font-weight: 650; margin: 14px 0; }
        .track { height: 6px; background: var(--border); border-radius: 100px; overflow: hidden; }
        .fill { height: 100%; background: linear-gradient(90deg, var(--indigo), var(--teal)); }
        .focus-meta { display: flex; justify-content: space-between; color: var(--muted); font-size: 9.5px; margin-top: 8px; }
        
        .timeline-day { position: relative; margin-left: 10px; padding-left: 28px; padding-bottom: 20px; border-left: 2px solid var(--border); }
        .timeline-dot { position: absolute; left: -7px; top: 0; width: 12px; height: 12px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 0 3px var(--panel); }
        .timeline-date { color: var(--text); font-size: 13px; font-weight: 700; margin-bottom: 9px; }
        .timeline-date span { color: var(--muted); font-size: 10px; margin-left: 5px; }
        .timeline-item { display: grid; grid-template-columns: 125px 1fr 150px; gap: 12px; align-items: center; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; margin-bottom: 7px; }
        .timeline-time { color: var(--teal); font-size: 10.5px; font-weight: 650; }
        .timeline-action { color: var(--text); font-size: 11.5px; font-weight: 650; }
        .timeline-work { color: var(--muted); font-size: 9.5px; margin-top: 3px; white-space: pre-wrap; line-height: 1.4; }
        .timeline-scroll { height: 450px; overflow-y: auto; padding-right: 8px; box-sizing: border-box; }

        .focus-expand summary { list-style: none; cursor: pointer; }
        .focus-expand summary::-webkit-details-marker { display: none; }
        .focus-expand .focus-card { width: 100%; box-sizing: border-box; }

        .focus-details { padding: 16px; border: 1px solid var(--border); border-top: 0; background: var(--panel); display: grid; grid-template-columns: 1fr 1fr; gap: 14px 24px; }
        .focus-detail-item { display: flex; flex-direction: column; gap: 4px; }
        .focus-detail-item span { font-size: 10px; color: var(--muted); letter-spacing: .7px; }
        .focus-detail-item strong { font-size: 13px; color: var(--text); font-weight: 600; }
        .focus-hint { padding: 10px; text-align: center; border: 1px solid var(--border); border-top: 0; color: var(--muted); font-size: 11px; background: var(--panel); }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def load_project_ai_data(company_code, employee_id=None, from_date=None, to_date=None):
    conn=cur=None
    try:
        conn=pyodbc.connect(CONN_STR); cur=conn.cursor()
        cur.execute('''EXEC u.sp_ai_DashboardProjectAI @CompanyCode=?, @EmployeeId=?, @FromDate=?, @ToDate=?''',company_code,employee_id,from_date,to_date)
        cols=[c[0] for c in cur.description]
        return [dict(zip(cols,r)) for r in cur.fetchall()]
    except Exception as e:
        st.error(f'Error loading project AI dataset: {e}'); return []
    finally:
        if cur: cur.close()
        if conn: conn.close()

def num(v,d=0.0):
    try:return d if v is None or pd.isna(v) else float(v)
    except:return d

def txt(v,d='N/A'):
    return d if v is None or pd.isna(v) else str(v)

@st.cache_data(ttl=3600)
def company_display_name(company_code):
    try:
        rows = load_company_data(company_code)
        if rows:
            name = rows[0].get('CompanyName')
            if name and not pd.isna(name):
                return str(name).strip()
    except Exception:
        pass
    return company_code

@st.cache_data(ttl=3600)
def load_company_options():
    rows = load_company_master()
    options = {}
    for row in rows:
        code = row.get("CompanyCode", row.get("Company_Code"))
        if code is None or pd.isna(code): continue
        code = str(code).strip()
        if code.endswith(".0"): code = code[:-2]
        if not code: continue
        name = row.get("CompanyName", row.get("Company_Name"))
        name = code if name is None or pd.isna(name) else str(name).strip()
        options[code] = name or code
    return dict(sorted(options.items(), key=lambda item: item[1].lower()))

def cards(items):
    return '<div class="panel"><div class="panel-label">Key Metrics</div><div class="kpi-grid">'+''.join(f'<div class="kpi-card"><div class="kpi-icon">{i}</div><div class="kpi-value">{html.escape(str(v))}</div><div class="kpi-label">{html.escape(str(l))}</div></div>' for i,l,v in items)+'</div></div>'

def layout(h=320):
    return dict(height=h,margin=dict(l=8,r=12,t=10,b=10),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#CBD0DE'))

def project_df(raw):
    if raw is None or raw.empty:return pd.DataFrame()
    d=raw.copy();mp={}
    for c in d.columns:
        k=str(c).strip().lower().replace('_',' ')
        if k in ('project name','projectname'):mp[c]='Project_Name'
        elif k in ('project code','projectcode'):mp[c]='Project_Code'
        elif k=='status':mp[c]='Status'
        elif k in ('deadline','dead line'):mp[c]='Deadline'
        elif k in ('allocatedhours','allocated hours'):mp[c]='AllocatedHours'
        elif k in ('usedhours','used hours'):mp[c]='UsedHours'
        elif k=='cost':mp[c]='Cost'
        elif k in ('team res','teamres','responsible'):mp[c]='Team_Res'
        elif k=='employee':mp[c]='Employee'
        elif k in ('employeeid','employee id'):mp[c]='EmployeeId'
        
    d=d.rename(columns=mp)
    if 'Project_Name' not in d:return pd.DataFrame()
    for c,default in [('Project_Code',''),('Status','Unknown'),('Deadline',pd.NaT),('AllocatedHours',0),('UsedHours',0),('Cost',0),('Team_Res',''),('Employee',''),('EmployeeId','')]:
        if c not in d:d[c]=default
    for c in ['AllocatedHours','UsedHours']:
        d[c]=d[c].map(ProjectDataProcessor._parse_time_to_hours)
    d['Cost']=pd.to_numeric(d['Cost'],errors='coerce').fillna(0)
    if 'TimelineDate' not in d.columns:
        for alias in ('DailyWorkDate','WorkDate'):
            if alias in d.columns:
                d['TimelineDate']=d[alias]
                break
    if 'DailyTimeSpent' not in d.columns and 'TimeCount' in d.columns:
        d['DailyTimeSpent']=d['TimeCount']
    if {'Master_Code','TimelineDate','DailyTimeSpent'}.issubset(d.columns):
        logged=d[d['TimelineDate'].notna()].copy()
        logged['_LoggedHours']=logged['DailyTimeSpent'].apply(ProjectDataProcessor._parse_time_to_hours)
        logged_hours=logged.groupby('Master_Code')['_LoggedHours'].sum()
    else:
        logged_hours=pd.Series(dtype='float64')
    d['Deadline']=pd.to_datetime(d['Deadline'],errors='coerce')
    d['EmployeeId']=d['EmployeeId'].astype(str).str.strip()
    d['Team_Res']=d['Team_Res'].astype(str).str.strip()
    d['Employee']=d['Employee'].fillna('').astype(str).str.strip()
    employee_map=d[d['Employee']!=''].drop_duplicates('EmployeeId').set_index('EmployeeId')['Employee'].to_dict()
    d['Responsible']=d['Team_Res'].map(employee_map)
    d['Responsible']=d['Responsible'].fillna(d['Employee'])
    d['Responsible']=d['Responsible'].replace({'':'Not Assigned','nan':'Not Assigned','None':'Not Assigned'})
    p=d.groupby(['Project_Code','Project_Name'],dropna=False).agg(
        Status=('Status','first'),
        Deadline=('Deadline','min'),
        AllocatedHours=('AllocatedHours','max'),
        UsedHours=('UsedHours','sum'),
        Cost=('Cost','max'),
        Responsible=('Responsible','first')
    ).reset_index()
    p['_LoggedHours']=p['Project_Code'].map(logged_hours).fillna(0)
    p['UsedHours']=p['UsedHours'].where(p['UsedHours']>0,p['_LoggedHours']).fillna(0)
    p=p.drop(columns=['_LoggedHours'])
    p['Progress']=p['Status'].astype(str).str.lower().apply(lambda x:100.0 if 'completed' in x else 0.0)
    m=(p.Progress==0)&(p.AllocatedHours>0)
    p.loc[m,'Progress']=(p.loc[m,'UsedHours']/p.loc[m,'AllocatedHours']*100).clip(0,100)
    return p

def chart_progress(p):
    if p.empty: st.info("No project data."); return
    d=p.copy()
    d["Progress"]=pd.to_numeric(d["Progress"],errors="coerce").fillna(0).clip(0,100)
    d["Project_Name"]=d["Project_Name"].fillna("Unnamed Project").astype(str).str.strip()
    d["Cost"]=pd.to_numeric(d["Cost"],errors="coerce").fillna(0)
    d=d[d["Progress"]<100].copy()
    if d.empty: st.success("All projects are completed."); return
    d=d.sort_values("Cost",ascending=False).head(5).sort_values("Progress",ascending=True)

    f=px.bar(d, x="Progress", y="Project_Name", orientation="h", text="Project_Name")
    f.update_traces(marker_color="#2DD9C7", textposition="inside", insidetextanchor="middle", textfont=dict(color="#0B0E14",size=11), customdata=d[["Cost"]], hovertemplate="<b>%{y}</b><br>Progress: %{x:.0f}%<br>Cost: %{customdata[0]:,.2f}<extra></extra>")
    for _,row in d.iterrows():
        f.add_annotation(x=min(float(row["Progress"])+2,98), y=row["Project_Name"], text=f"{row['Progress']:.0f}%", showarrow=False, xanchor="left", font=dict(color="#F4F6FB",size=10))
    f.update_layout(**layout(), xaxis=dict(range=[0,105], title=None, gridcolor="#252B3A", ticksuffix="%", showgrid=True, zeroline=False), yaxis=dict(title=None, showticklabels=False, showgrid=False, zeroline=False), showlegend=False)
    st.plotly_chart(f, use_container_width=True, config={"displayModeBar":False,"responsive":True})

def chart_status(t,p):
    s=None
    if not t.empty:
        c=next((x for x in t.columns if str(x).lower().strip() in ('status','dailyreportstatus')),None)
        if c:s=t[c].fillna('Unknown').astype(str).value_counts().reset_index();s.columns=['Status','Count']
    if s is None or s.empty:
        if p.empty:st.info('No status data.');return
        s=p.Status.fillna('Unknown').astype(str).value_counts().reset_index();s.columns=['Status','Count']
    f=px.pie(s,names='Status',values='Count',hole=.68);f.update_traces(textinfo='percent');f.update_layout(**layout(),legend=dict(orientation='h',y=-.05));st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})

def chart_daily(t):
    if t.empty:st.info('No timeline data.');return
    dc=next((x for x in t.columns if str(x).lower().strip() in ('date','timelinedate','timeline date')),None)
    if not dc:st.info('Timeline date unavailable.');return
    tc=next((x for x in t.columns if str(x).lower().strip() in ('time logged','dailytimespent','daily time spent','hours')),None)
    d=t.copy();d['D']=pd.to_datetime(d[dc],errors='coerce');d['H']=pd.to_numeric(d[tc],errors='coerce').fillna(0) if tc else 0
    d=d.dropna(subset=['D']).groupby('D',as_index=False)['H'].sum().sort_values('D')
    if d.empty:st.info('No valid daily work records.');return
    f=px.line(d,x='D',y='H',markers=True);f.update_traces(line=dict(color='#2DD9C7',width=3));f.update_layout(**layout(),xaxis=dict(title=None),yaxis=dict(title='Hours',gridcolor='#252B3A'),showlegend=False);st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})

def chart_hours(p):
    if p.empty: st.info("No project hours data."); return
    d=p.copy()
    d["Progress"]=pd.to_numeric(d["Progress"],errors="coerce").fillna(0).clip(0,100)
    d["Cost"]=pd.to_numeric(d["Cost"],errors="coerce").fillna(0)
    d["AllocatedHours"]=pd.to_numeric(d["AllocatedHours"],errors="coerce").fillna(0)
    d["UsedHours"]=pd.to_numeric(d["UsedHours"],errors="coerce").fillna(0)
    d["Project_Name"]=d["Project_Name"].fillna("Unnamed Project").astype(str).str.strip()
    d["Responsible"]=d["Responsible"].fillna("Not Assigned").astype(str).str.strip()
    d=d[(d["Progress"]<100) & (d["Cost"]>0)].copy()
    if d.empty: st.info("No incomplete project data available."); return
    d=d.sort_values("Cost",ascending=False).head(5).sort_values("Cost",ascending=True)
    d["Cost_Label"]=d["Cost"].apply(lambda x:f"{x:,.0f}")
    custom=d[["Project_Name","Responsible","Cost","AllocatedHours","UsedHours"]].to_numpy()
    
    f=go.Figure()
    f.add_trace(go.Bar(name="Allocated", x=d["Cost_Label"], y=d["AllocatedHours"], marker_color="#8B7CFF", customdata=custom, hovertemplate="<b>%{customdata[0]}</b><br>Responsible: %{customdata[1]}<br>Cost: %{customdata[2]:,.0f}<br>Allocated Hours: %{customdata[3]:,.1f}<br>Used Hours: %{customdata[4]:,.1f}<extra></extra>"))
    f.add_trace(go.Bar(name="Used", x=d["Cost_Label"], y=d["UsedHours"], marker_color="#2DD9C7", customdata=custom, hovertemplate="<b>%{customdata[0]}</b><br>Responsible: %{customdata[1]}<br>Cost: %{customdata[2]:,.0f}<br>Allocated Hours: %{customdata[3]:,.1f}<br>Used Hours: %{customdata[4]:,.1f}<extra></extra>"))
    f.update_layout(**layout(), barmode="group", hovermode="closest", xaxis=dict(title="Project Cost", type="category", categoryorder="array", categoryarray=d["Cost_Label"].tolist(), showgrid=False, zeroline=False), yaxis=dict(title="Hours", gridcolor="#252B3A", showgrid=True, zeroline=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), showlegend=True)
    st.plotly_chart(f, use_container_width=True, config={"displayModeBar":False,"responsive":True})

def chart_employee_focus_hours(focus_imp):
    if not focus_imp: st.info("No employee focus project available."); return
    rows = []
    for x in focus_imp.values():
        if not x: continue
        responsible = txt(x.get("Responsible"), "").strip()
        if responsible.lower() in ("nan", "none", "null", ""): responsible = ""
        employee_name = txt(x.get("Employee"), "").strip()
        if employee_name.lower() in ("nan", "none", "null", ""): employee_name = ""
        team_res = txt(x.get("Team_Res"), "").strip()
        if team_res.lower() in ("nan", "none", "null", ""): team_res = ""
        employee_id = txt(x.get("EmployeeId"), "").strip()
        if employee_id.lower() in ("nan", "none", "null", ""): employee_id = ""

        if responsible: pass
        elif employee_name: responsible = employee_name
        elif team_res and employee_id and team_res == employee_id: responsible = "Employee" + employee_id
        elif team_res: responsible = team_res
        else: responsible = "Not Assigned"

        rows.append({"Project_Name": txt(x.get("Project_Name"), "Unnamed Project"), "AllocatedHours": num(x.get("AllocatedHours")), "UsedHours": num(x.get("UsedHours")), "Cost": num(x.get("Cost")), "Responsible": responsible})

    d = pd.DataFrame(rows)
    if d.empty: st.info("No employee focus project hours available."); return
    d["AllocatedHours"] = pd.to_numeric(d["AllocatedHours"], errors="coerce").fillna(0)
    d["UsedHours"] = pd.to_numeric(d["UsedHours"], errors="coerce").fillna(0)
    d["Cost"] = pd.to_numeric(d["Cost"], errors="coerce").fillna(0)
    d["Project"] = [f"P{i + 1}" for i in range(len(d))]

    custom = d[["Project_Name", "Responsible", "Cost", "AllocatedHours", "UsedHours"]].to_numpy()
    hover = "<b>%{customdata[0]}</b><br>Responsible: %{customdata[1]}<br>Cost: %{customdata[2]:,.0f}<br>Allocated: %{customdata[3]:,.1f} hrs<br>Used: %{customdata[4]:,.1f} hrs<extra></extra>"

    f = go.Figure()
    f.add_trace(go.Bar(name="Allocated", x=d["Project"], y=d["AllocatedHours"], marker_color="#8B7CFF", customdata=custom, hovertemplate=hover))
    f.add_trace(go.Bar(name="Used", x=d["Project"], y=d["UsedHours"], marker_color="#2DD9C7", customdata=custom, hovertemplate=hover))
    f.update_layout(**layout(), barmode="group", hovermode="closest", xaxis=dict(title=None, showticklabels=True, showgrid=False, zeroline=False), yaxis=dict(title="Hours", gridcolor="#252B3A", showgrid=True, zeroline=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), showlegend=True)
    st.plotly_chart(f, use_container_width=True, config={"displayModeBar": False, "responsive": True})

def chart_risk(p):
    d=p.dropna(subset=['Deadline']).copy()
    if d.empty:st.info('No valid deadlines.');return
    today=pd.Timestamp.today().normalize();d['Days']=(d.Deadline-today).dt.days;d['RiskScore']=((100-d.Progress).clip(0,100)*.6+(30-d.Days).clip(0,30)/30*40).clip(0,100);d['Risk']=pd.cut(d.RiskScore,[-1,35,65,101],labels=['Low','Medium','High'])
    f=px.scatter(d,x='Progress',y='Days',size='UsedHours',color='Risk',hover_name='Project_Name',size_max=38);f.update_layout(**layout(350),xaxis=dict(title='Progress %',range=[0,105],gridcolor='#252B3A'),yaxis=dict(title='Days to Deadline',gridcolor='#252B3A'),legend=dict(orientation='h',y=1.08));f.add_vline(x=50,line_dash='dash',line_color='#575E72');f.add_hline(y=7,line_dash='dash',line_color='#F5B84E');st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})

def chart_workload(p):
    if p.empty:st.info('No workload data.');return
    f=px.scatter(p,x='UsedHours',y='Progress',size='AllocatedHours',color='Status',hover_name='Project_Name',size_max=42);f.update_layout(**layout(350),xaxis=dict(title='Hours Used',gridcolor='#252B3A'),yaxis=dict(title='Progress %',range=[0,105],gridcolor='#252B3A'));st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})

def focus_cards(imp,title):
    st.markdown(f'<div class="section-title">{html.escape(title)} — click a card for details</div>',unsafe_allow_html=True)
    arr=[('urgent_project','🚨 Urgent','danger'),('high_cost_project','💰 High Cost','warning'),('historical_project','📅 Historical','info')]
    arr=[x for x in arr if imp.get(x[0])]
    if not arr: st.info('No focus projects found.'); return
    cs=st.columns(len(arr))
    for col,(k,label,css) in zip(cs,arr):
        x=imp[k]
        a=num(x.get('AllocatedHours')); u=num(x.get('UsedHours')); pct=u/a*100 if a else 0
        name=txt(x.get("Project_Name"),"Unnamed"); status=txt(x.get("Status"),"Unknown")
        deadline=txt(x.get("DeadLine",x.get("Deadline")),"N/A")[:10]
        responsible=txt(x.get("Responsible",x.get("Employee")),"Not Assigned")
        actions=x.get("TotalActions",x.get("Total_Action",x.get("Actions",0))); cost=num(x.get("Cost"))
        with col:
            st.markdown(f'''<details class="focus-expand"><summary class="focus-card {css}"><div class="focus-top"><span>{label}</span><span>{html.escape(status)}</span></div><div class="focus-name">{html.escape(name)}</div><div class="track"><div class="fill" style="width:{min(pct,100):.0f}%"></div></div><div class="focus-meta"><span>{u:.1f}/{a:.1f} hrs</span><span>{html.escape(deadline)}</span></div></summary><div class="focus-details"><div class="focus-detail-item"><span>RESPONSIBLE</span><strong>{html.escape(responsible)}</strong></div><div class="focus-detail-item"><span>ACTIONS</span><strong>{html.escape(txt(actions,"0"))}</strong></div><div class="focus-detail-item"><span>COST</span><strong>{cost:,.0f}</strong></div><div class="focus-detail-item"><span>ALLOCATED</span><strong>{a:.1f} hrs</strong></div><div class="focus-detail-item"><span>USED</span><strong>{u:.2f} hrs</strong></div><div class="focus-detail-item"><span>DEADLINE</span><strong>{html.escape(deadline)}</strong></div></div><div class="focus-hint">Click to collapse</div></details>''',unsafe_allow_html=True)

def focus_project_details(imp):
    selected=st.session_state.get("selected_focus_project")
    if not selected or selected not in imp: return
    x=imp[selected]
    st.markdown('<div class="section-title">Project Details</div>',unsafe_allow_html=True)
    name=txt(x.get("Project_Name"),"Unnamed Project"); status=txt(x.get("Status"),"Unknown")
    responsible=txt(x.get("Responsible",x.get("Employee")),"Not Assigned")
    cost=num(x.get("Cost")); allocated=num(x.get("AllocatedHours")); used=num(x.get("UsedHours"))
    actions=x.get("TotalActions",x.get("Total_Action",x.get("Actions",0)))
    members=x.get("AssignedMembers",x.get("Assigned_Members",x.get("Members",0)))
    deadline=txt(x.get("DeadLine",x.get("Deadline")),"N/A")
    cols=st.columns(4)
    with cols[0]: st.metric("Total Actions",actions)
    with cols[1]: st.metric("Assigned Members",members)
    with cols[2]: st.metric("Cost",f"{cost:,.0f}")
    with cols[3]: st.metric("Progress",f"{(used/allocated*100 if allocated else 0):.0f}%")
    st.markdown(f'''<div class="focus-card info"><div class="focus-top"><span>Project</span><span>{html.escape(status)}</span></div><div class="focus-name">{html.escape(name)}</div><div class="focus-meta"><span>Responsible: {html.escape(responsible)}</span></div><div class="focus-meta"><span>Allocated: {allocated:.1f} hrs</span><span>Used: {used:.1f} hrs</span></div><div class="focus-meta"><span>Deadline: {html.escape(deadline)[:10]}</span></div></div>''',unsafe_allow_html=True)

def employee_focus_cards(imp,title,p):
    st.markdown(f'<div class="section-title">{html.escape(title)} — click a card for details</div>',unsafe_allow_html=True)
    arr=[('urgent_project','🚨 Urgent','danger'),('high_cost_project','💰 High Cost','warning'),('historical_project','📅 Historical','info')]
    arr=[x for x in arr if imp.get(x[0])]
    if not arr and imp.get('recent_project'): arr=[('recent_project','🕒 Recent','info')]
    if not arr: st.info('No focus projects found.'); return
    cs=st.columns(len(arr))
    for col,(k,label,css) in zip(cs,arr):
        x=imp[k]
        a=num(x.get('AllocatedHours')); u=num(x.get('UsedHours')); pct=u/a*100 if a else 0
        name=txt(x.get("Project_Name"),"Unnamed"); status=txt(x.get("Status"),"Unknown")
        deadline=txt(x.get("DeadLine",x.get("Deadline")),"N/A")[:10]
        actions=x.get("TotalActions",x.get("Total_Action",x.get("Actions",0)))
        cost=num(x.get("Cost")); members=x.get("AssignedMembers",x.get("Assigned_Members",x.get("Members",0)))
        
        proj_code = x.get("Project_Code"); responsible = "Not Assigned"
        if p is not None and not p.empty and proj_code:
            match = p[p['Project_Code'] == proj_code]
            if not match.empty: responsible = str(match['Responsible'].iloc[0])
        if pd.isna(responsible) or responsible == "" or responsible == "Not Assigned":
            responsible = txt(x.get("Responsible", x.get("Employee", x.get("Team_Res"))), "Not Assigned")

        with col:
            st.markdown(f'''<details class="focus-expand"><summary class="focus-card {css}"><div class="focus-top"><span>{label}</span><span>{html.escape(status)}</span></div><div class="focus-name">{html.escape(name)}</div><div class="track"><div class="fill" style="width:{min(pct,100):.0f}%"></div></div><div class="focus-meta"><span>{u:.1f}/{a:.1f} hrs</span><span>{html.escape(deadline)}</span></div></summary><div class="focus-details"><div class="focus-detail-item"><span>RESPONSIBLE</span><strong>{html.escape(responsible)}</strong></div><div class="focus-detail-item"><span>ACTIONS</span><strong>{html.escape(txt(actions,"0"))}</strong></div><div class="focus-detail-item"><span>ASSIGNED MEMBERS</span><strong>{html.escape(txt(members,"0"))}</strong></div><div class="focus-detail-item"><span>COST</span><strong>{cost:,.0f}</strong></div><div class="focus-detail-item"><span>ALLOCATED</span><strong>{a:.1f} hrs</strong></div><div class="focus-detail-item"><span>USED</span><strong>{u:.2f} hrs</strong></div><div class="focus-detail-item"><span>DEADLINE</span><strong>{html.escape(deadline)}</strong></div></div><div class="focus-hint">Click to collapse</div></details>''',unsafe_allow_html=True)
                   
def resolve_timeline_parent_child_mapping(df):
    if df.empty: return df
    d = df.copy()
    project_lookup = {}
    for _, r in d.iterrows():
        p_code = str(r.get("Project_Code", "")).strip()
        p_name = str(r.get("Project_Name", "")).strip()
        if p_code and p_name and p_name.lower() not in ("none", "nan"):
            project_lookup[p_code] = p_name

    resolved_titles = []
    for _, r in d.iterrows():
        master_code = str(r.get("Master_Code", "")).strip()
        project_name = str(r.get("Project_Name", "")).strip()
        if master_code and master_code in project_lookup:
            parent_project_name = project_lookup[master_code]
            resolved_titles.append(f"{parent_project_name.upper()} • {project_name.upper()}")
        else:
            resolved_titles.append(project_name.upper() if project_name else "RECORDED WORK ACTIVITY")
    d["ResolvedTitle"] = resolved_titles
    return d

def visual_timeline(t, max_height=450):
    if t.empty: st.info('No daily timeline records found.'); return
    d = resolve_timeline_parent_child_mapping(t)
    rename_map = {}
    for c in d.columns:
        k = str(c).lower().strip()
        if k in ('date', 'timelinedate', 'timeline date', 'dailyworkdate'): rename_map[c] = 'Date'
        elif k in ('start', 'starttime'): rename_map[c] = 'Start'
        elif k in ('end', 'endtime'): rename_map[c] = 'End'
        elif k in ('time logged', 'dailytimespent', 'daily time spent', 'timecount'): rename_map[c] = 'Duration'
        elif k in ('work achieved', 'workachieved'): rename_map[c] = 'Work'
        elif k in ('status', 'dailyreportstatus'): rename_map[c] = 'Status'

    d = d.rename(columns=rename_map)
    d['Date'] = pd.to_datetime(d['Date'], errors='coerce')
    d = d.dropna(subset=['Date']).sort_values('Date', ascending=False)

    def parse_to_minutes(time_val):
        if not isinstance(time_val, str) or ":" not in time_val: return 0
        try:
            parts = time_val.strip().split(":")
            return (int(parts[0]) * 60) + int(parts[1])
        except (ValueError, IndexError): return 0

    def format_to_hours(total_minutes):
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    html_buffer = [f'<div class="timeline-scroll" style="height: {max_height}px;"><div style="position: relative; border-left: 2px solid var(--border); margin-left: 15px; padding-left: 20px;">']
    for day, g in d.groupby(d.Date.dt.date, sort=False):
        total_mins = g["Duration"].astype(str).apply(parse_to_minutes).sum()
        formatted_total = format_to_hours(total_mins)
        html_buffer.append(f'<div style="position:relative;margin-bottom:24px;"><div style="position:absolute;left:-27px;top:3px;width:12px;height:12px;border-radius:50%;background:var(--teal);box-shadow:0 0 6px var(--teal);"></div><div class="timeline-date" style="margin-bottom:12px;">{pd.Timestamp(day):%d %b %Y} <span>{pd.Timestamp(day):%a}</span><span style="float:right;color:var(--muted);font-weight:400;font-size:11px;">Total: {formatted_total} hrs</span></div>')
        for _, r in g.iterrows():
            resolved_title = r.get("ResolvedTitle", "RECORDED WORK ACTIVITY")
            start_time = html.escape(txt(r.get("Start"), ""))
            end_time = html.escape(txt(r.get("End"), ""))
            time_range = f"{start_time} → {end_time}" if start_time or end_time else "Activity Logged"
            html_buffer.append(f'<div class="timeline-item" style="margin-bottom:8px;"><div class="timeline-time">{time_range}</div><div><div class="timeline-action">{html.escape(resolved_title)}</div><div class="timeline-work">{html.escape(txt(r.get("Work"), "Work activity recorded"))}</div></div><div class="timeline-right"><span>{html.escape(txt(r.get("Duration"), ""))}</span><span class="pill">{html.escape(txt(r.get("Status"), "Recorded"))}</span></div></div>')
        html_buffer.append('</div>')
    html_buffer.append('</div></div>')
    st.markdown(dedent("".join(html_buffer)), unsafe_allow_html=True)

def calculate_real_progress(actions):
    if not actions: return 0.0
    total_progress = 0.0
    for a in actions:
        status = txt(a.get('Status')).lower(); ah = num(a.get('AllocatedHours')); uh = num(a.get('ActionUsedHours'))
        if 'completed' in status: action_prog = 100.0
        elif ah > 0: action_prog = min((uh / ah) * 100.0, 100.0)
        else: action_prog = 0.0
        total_progress += action_prog
    return total_progress / len(actions)

def chart_past_3_months_trend(trend):
    if trend.empty: st.info("No project trend data available."); return
    available_months = sorted(trend["MonthDate"].unique())
    month_labels = [pd.Timestamp(m).strftime("%b %Y") for m in available_months]
    fig = go.Figure()
    statuses = ["Completed", "InProcess", "Delayed"]
    status_colors = {"Completed": "#2DD9C7", "InProcess": "#4E9AF5", "Delayed": "#F55B4E", "Unknown": "#6C757D"}
    for status in trend["StatusClean"].unique():
        if status not in statuses: statuses.append(status)
        if status not in status_colors: status_colors[status] = "#888888"

    for status in statuses:
        values = []
        for month in available_months:
            temp = trend[(trend["MonthDate"] == month) & (trend["StatusClean"] == status)]
            values.append(0 if temp.empty else int(temp["ProjectCount"].sum()))
        fig.add_trace(go.Bar(x=month_labels, y=values, name=status, marker_color=status_colors.get(status, "#888888")))

    completed_values = []
    for month in available_months:
        temp = trend[(trend["MonthDate"] == month) & (trend["StatusClean"] == "Completed")]
        completed_values.append(0 if temp.empty else int(temp["ProjectCount"].sum()))
    fig.add_trace(go.Scatter(x=month_labels, y=completed_values, name="Completed Trend", mode="lines+markers", line=dict(color="#F5B84E", width=3), marker=dict(size=7, color="#F5B84E")))

    fig.update_layout(title=dict(text="Project Status - Last Month", y=0.98, x=0.01), barmode="stack", xaxis=dict(title="", categoryorder="array", categoryarray=month_labels), yaxis=dict(title="", showticklabels=False, showgrid=False, zeroline=False), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.01), height=450, margin=dict(l=20, r=20, t=140, b=20), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Sidebar
st.sidebar.markdown('**Performance Intelligence**\n\nProject & employee analytics')
company_names = load_company_options()
company_codes = list(company_names)
if not company_codes: st.sidebar.error('No companies found in the database.'); st.stop()
company = st.sidebar.selectbox('Company', options=company_codes, format_func=lambda code: company_names.get(code, code))
company_name = company_names.get(company, company)
mode=st.sidebar.radio('Dashboard',['Company','Employee','Project Performance'])
today=date.today(); fd=st.sidebar.date_input('From date',today.replace(month=1,day=1),max_value=today); td=st.sidebar.date_input('To date',today,min_value=fd,max_value=today)
weekly_days=st.sidebar.slider('Weekly report window',7,90,7,7)
if st.sidebar.button('Render Weekly PDF',use_container_width=True):
    try: generate_weekly_report_pdf(company,weekly_days,'static/weekly_reports'); st.success('Weekly PDF generated.')
    except Exception as e: st.error(f'Could not generate weekly PDF: {e}')

rows=load_company_data(company,fd.isoformat(),td.isoformat()); df=clean_rows(rows)
if df.empty: st.warning('No records returned for the selected filters.'); st.stop()

employee_id=None; selected_employee=None
if mode in ['Employee','Project Performance']:
    opts=(df[['EmployeeId','Employee']].dropna().assign(EmployeeId=lambda x:x.EmployeeId.astype(str).str.replace(r'\.0$','',regex=True).str.strip(),Employee=lambda x:x.Employee.astype(str).str.strip()).drop_duplicates().sort_values('Employee').to_dict('records'))
    if not opts: st.warning('No employees found.'); st.stop()
    selected_employee=st.sidebar.selectbox('Employee',opts,format_func=lambda x:f"{x['Employee']} ({x['EmployeeId']})"); employee_id=selected_employee['EmployeeId']

# Employee Dashboard
if mode=='Employee':
    days=st.sidebar.slider('Timeline days',7,90,30,7)
    ed=get_employee_timeline_dashboard(employee_id,company,days); ek=ed.get('summary',{})
    edf=clean_timeline_rows(load_employee_important_project_data(employee_id,company)); imp=get_employee_important_projects(edf); t=pd.DataFrame(ed.get('timeline_records',[])); p=project_df(edf)
    
    emp_name = selected_employee.get("Employee", str(employee_id))
    if not p.empty and 'Responsible' in p.columns:
        p['Responsible'] = p['Responsible'].astype(str).replace({str(employee_id): emp_name})
    for k, v in imp.items():
        if isinstance(v, dict):
            for field in ["Responsible", "Employee", "Team_Res"]:
                if str(v.get(field)).strip() == str(employee_id).strip():
                    v[field] = emp_name; v["Responsible"] = emp_name

    st.markdown(f'<div class="dashboard-header"><div><div class="eyebrow">Employee Performance</div><div class="header-title">👤 {html.escape(txt(selected_employee.get("Employee"),"Employee"))}</div><div class="header-sub">Employee ID {html.escape(str(employee_id))} · Company {html.escape(company_name)} · Last {days} days</div></div><div class="live">.</div></div>',unsafe_allow_html=True)
    a,b=st.columns([1.05,1.7],gap='large')
    with a:
        with st.container(border=True): st.markdown('<div class="panel-label">✦ Employee Overview</div><div class="ai-copy">This view combines assigned projects, actions and actual daily work logs. The analytics below are calculated from the existing Employee model data.</div>',unsafe_allow_html=True)
    with b: st.markdown(cards([('📁','Projects',ek.get('total_projects',0)),('⚡','Actions',ek.get('total_actions',0)),('✅','Completed',ek.get('completed_projects',0)),('⏱','Remaining',ek.get('remaining_projects',0)),('🏆','Achievement',f"{ek.get('achievement_pct',0)}%"),('📅','Timeline Days',days)]),unsafe_allow_html=True)
    
    focus_imp={}
    for k in ['urgent_project','high_cost_project','historical_project']:
        if imp.get(k): focus_imp[k]=imp[k]
    if not focus_imp and imp.get('recent_project'): focus_imp['recent_project']=imp['recent_project']
       
    employee_focus_cards(focus_imp,'Employee Focus Projects',p)

    st.markdown('<div class="section-title">Performance Analytics</div>',unsafe_allow_html=True)
    c1,c2=st.columns(2,gap='large')
    with c1:
        with st.container(border=True): st.markdown('<div class="chart-title">Work Status Distribution</div>',unsafe_allow_html=True); chart_status(t,p)
    with c2:
        with st.container(border=True): st.markdown('<div class="chart-title">Allocated vs Used Hours</div>',unsafe_allow_html=True); chart_employee_focus_hours(focus_imp)
        
    employee_rows = load_employee_timeline(employee_id=employee_id, company_code=company, days_back=121)
    trend = get_past_3_months_status_trend(employee_rows)

    st.markdown('<div class="section-title">Performance & Daily Worklogs</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(border=True): st.markdown('<div class="chart-title">Month Progress</div>', unsafe_allow_html=True); chart_past_3_months_trend(trend)
    with c2:
        with st.container(border=True): st.markdown('<div class="chart-title">Daily Work Timeline</div>', unsafe_allow_html=True); visual_timeline(t, max_height=450)
    st.stop()

# Project Performance AI
if mode=='Project Performance':
    raw=load_project_ai_data(company,employee_id,fd.isoformat(),td.isoformat())
    if not raw: st.warning('No project performance records found.'); st.stop()
    
    tree=ProjectDataProcessor(raw).get_project_timeline_tree(exclude_completed=True)
    if not tree: st.info('No incomplete projects found.'); st.stop()
    
    pdict={f"{x['Parent_Project_Name']} ({x['Parent_Project_Code']})":x for x in tree}
    label = st.sidebar.selectbox('Project', list(pdict)); x = pdict[label]
    
    members=set([str(x.get('EmployeeId')).strip()]) if x.get('EmployeeId') else set(); members.update(str(x.get('Team_Support','')).split(',')); members={m.strip() for m in members if m.strip() and m.strip().lower() not in ('nan','none')}
    actions = x.get('Sub_Actions', []); logs = sum((a.get('Timeline_Logs', []) for a in actions), [])
    allocated = num(x.get('AllocatedHours')); used = num(x.get('TotalProjectUsedHours')); usage = used / allocated * 100 if allocated else 0
    progress = calculate_real_progress(actions)
    
    st.markdown(f'<div class="dashboard-header"><div><div class="eyebrow">Project Intelligence</div><div class="header-title">⚙️ {html.escape(txt(x.get("Parent_Project_Name"),"Project"))}</div><div class="header-sub">Employee {html.escape(str(employee_id))} · Company {html.escape(company_name)}</div></div><div class="live"> DATA</div></div>',unsafe_allow_html=True)
    st.markdown(cards([('📁','Status',x.get('Status','N/A')),('👥','Active Team',len(members)),('⚡','Actions',len(actions)),('⏱','Allocated',f'{allocated:.1f} h'),('⚙️','Used',f'{used:.1f} h'),('📈','Usage',f'{usage:.1f}%')]),unsafe_allow_html=True)
    
    c1, c2 = st.columns(2, gap='medium')
    with c1:
        with st.container(border=True):
            st.markdown('<div class="chart-title">Progress</div>', unsafe_allow_html=True)
            f=go.Figure(go.Indicator(mode='gauge+number',value=progress,number={'suffix':'%','font':{'color':'#F4F6FB','size':34}},title={'text':'Sub-action completion','font':{'color':'#8A91A6'}},gauge={'axis':{'range':[0,100]},'bar':{'color':'#2DD9C7'},'bgcolor':'#171B26'}))
            f.update_layout(**layout(280))
            st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})
    with c2:
        with st.container(border=True):
            st.markdown('<div class="chart-title">Hours Utilization</div>', unsafe_allow_html=True)
            u=pd.DataFrame({'Metric':['Allocated','Used'],'Hours':[allocated,used]})
            f=px.bar(u,x='Metric',y='Hours',text='Hours')
            f.update_traces(marker_color=['#6E7CF6','#2DD9C7'],texttemplate='%{text:.1f} h',textposition='outside')
            f.update_layout(**layout(280), showlegend=False, yaxis=dict(gridcolor='#252B3A'), xaxis=dict(title=''))
            st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})
            
    ad=[]
    for a in actions:
        ah=num(a.get('AllocatedHours')); uh=num(a.get('ActionUsedHours')); ap=uh/ah*100 if ah else (100 if 'completed' in txt(a.get('Status')).lower() else 0); ad.append({'Action':a.get('Action_Name','Unnamed'),'Status':a.get('Status','Unknown'),'Progress':ap,'Allocated':ah,'Used':uh})
    
    if ad:
        st.markdown('<div class="section-title">Sub-Actions & Milestones</div>',unsafe_allow_html=True); af=pd.DataFrame(ad); f=px.bar(af.sort_values('Progress'),x='Progress',y='Action',orientation='h',color='Status',text='Progress'); f.update_traces(texttemplate='%{text:.0f}%',textposition='outside'); f.update_layout(**layout(350),xaxis=dict(range=[0,110],title='Progress %')); st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})
        with st.expander('View detailed sub-actions'): st.dataframe(af,use_container_width=True,hide_index=True)
        
    logdf=pd.DataFrame([{'Date':l.get('TimelineDate'),'Action':a.get('Action_Name'),'Start':l.get('StartTime'),'End':l.get('EndTime'),'Duration':l.get('DailyTimeSpent'),'WorkAchieved':l.get('WorkAchieved'),'Status':l.get('DailyReportStatus'),'EmployeeId':l.get('ActionLoggedBy')} for a in actions for l in a.get('Timeline_Logs',[])])
    visual_timeline(logdf)
    with st.expander('🔎 View project timeline records'): st.dataframe(logdf,use_container_width=True,hide_index=True)
    st.stop()

# Company Dashboard
kpi=compute_kpis(df); es=employee_summary(df); impdf=clean_rows(load_important_project_data(company)); imp=get_important_projects(impdf)
st.markdown(f'<div class="dashboard-header"><div><div class="eyebrow">Company Performance</div><div class="header-title">📊 {html.escape(company_name)}</div><div class="header-sub">{fd} → {td}</div></div><div class="live">● LIVE DATA</div></div>',unsafe_allow_html=True)
l,r=st.columns([1.05,1.7],gap='large')
with l:
    with st.container(border=True):
        st.markdown('<div class="panel-label">✦ AI Executive Summary</div>',unsafe_allow_html=True)
        if st.button('✨ Generate AI Summary',use_container_width=True):
            with st.spinner('Analyzing company performance...'): st.session_state.ai_summary=summarize_dashboard(kpi,imp,es.to_dict('records'),{'Employees':[],'Actions':[]})
        st.markdown(f'<div class="ai-copy">{html.escape(st.session_state.get("ai_summary","Generate a summary to analyze company performance and risks.")).replace(chr(10),"<br>")}</div>',unsafe_allow_html=True)
with r:
    st.markdown(cards([('📁', 'Projects', f"{kpi.get('total_projects', 0):,}"), ('👥', 'Employees', f"{kpi.get('total_employees', 0):,}"), ('✅', 'Completed', f"{kpi.get('completed_projects', 0):,}"), ('⚡', 'Actions', f"{kpi.get('total_actions', 0):,}"), ('🏆', 'Achievement', f"{kpi.get('achievement_pct', 0)}%"), ('⏱', 'Remaining', f"{kpi.get('remaining_projects', 0):,}")]), unsafe_allow_html=True)

focus_cards(imp, 'Company Focus Projects')
focus_project_details(imp)
st.markdown("<div style='height:35px'></div>",unsafe_allow_html=True)

cp=project_df(impdf)
c1,c2=st.columns(2,gap='large')
with c1:
    with st.container(border=True): st.markdown('<div class="chart-title">Project Progress</div>',unsafe_allow_html=True); chart_progress(cp)
with c2:
    with st.container(border=True): st.markdown('<div class="chart-title">Allocated vs Used Hours</div>',unsafe_allow_html=True); chart_hours(cp)

if not es.empty:
    val=next((c for c in ['TotalActions','Total_Actions','TotalActionsLogged'] if c in es.columns),None)
    if val:
        st.markdown('<div class="section-title">Employee Workload</div>',unsafe_allow_html=True)
        d=es.copy(); d[val]=pd.to_numeric(d[val],errors='coerce').fillna(0); d=d.sort_values(val,ascending=False).head(12)
        f=px.bar(d,x=val,y='Employee',orientation='h',text=val)
        f.update_traces(marker_color='#6E7CF6',textposition='outside')
        f.update_layout(**layout(350),xaxis=dict(title='Actions',gridcolor='#252B3A'),yaxis=dict(title=None))
        st.plotly_chart(f,use_container_width=True,config={'displayModeBar':False})