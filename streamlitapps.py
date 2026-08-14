import html
from datetime import date
from pathlib import Path
import os
import pyodbc
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Import standard models
from dashboard_model import (
    clean_rows,
    compute_kpis,
    employee_summary,
    get_important_projects,
    load_company_data,
    load_important_project_data,
    project_details,
)
from Emodel import (
    clean_timeline_rows,
    get_employee_project_details,
    get_employee_timeline_dashboard,
    get_important_projects as get_employee_important_projects,
    load_important_project_data as load_employee_important_project_data,
)
from pmodel import ProjectDataProcessor  # Import the new project processor
from summarize import summarize_dashboard
from weekly import generate_weekly_report_pdf

# Load Database Environment Credentials
load_dotenv()
SERVER = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_DATABASE")
USERNAME = os.getenv("DB_USERNAME")
PASSWORD = os.getenv("DB_PASSWORD")

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
)

# Cached database loader targeting u.sp_ai_DashboardProjectAI
@st.cache_data(ttl=60)
def load_project_ai_data(company_code, employee_id=None, from_date=None, to_date=None):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC u.sp_ai_DashboardProjectAI
                @CompanyCode=?,
                @EmployeeId=?,
                @FromDate=?,
                @ToDate=?
            """,
            company_code,
            employee_id,
            from_date,
            to_date
        )
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        st.error(f"Error loading project AI dataset: {e}")
        return []
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()


# Initialize interconnected variables globally to prevent IDE scoping warnings
selected_project_code = None
employee_id = None
selected_employee = None

st.set_page_config(page_title="Company Dashboard", page_icon="📊", layout="wide")

# Custom CSS Styling Layout (matching dashboard_mockup.html layout)
st.markdown("""
<style>
.top-panel { background:#12151d; border:1px solid #252b3a; border-radius:14px; padding:20px; min-height:330px; }
.panel-label { color:#8a91a6; font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-bottom:16px; }
.ai-copy { color:#cbd0de; font-size:14px; line-height:1.65; height:205px; overflow-y:auto; padding-right:5px; }
.kpi-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.kpi-card { background:#191e29; border:1px solid #252b3a; border-radius:12px; min-height:125px; padding:15px 16px; }
.kpi-value { color:#f4f6fb; font-size:25px; font-weight:700; line-height:1; }
.kpi-label { color:#8a91a6; font-size:12px; margin-top:8px; }
div[data-testid="stVerticalBlockBorderWrapper"] { background:#12151d; border-color:#252b3a; border-radius:14px; min-height:330px; }
@media (max-width:720px) { .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
""", unsafe_allow_html=True)


def _show_weekly_pdf_preview(current_company, current_days_back):
    report_path = st.session_state.get("weekly_report_pdf_path")
    if not report_path:
        return

    if (
        st.session_state.get("weekly_report_company") != current_company
        or st.session_state.get("weekly_report_days_back") != current_days_back
    ):
        return

    pdf_path = Path(report_path)
    if not pdf_path.exists():
        st.warning("The generated weekly PDF is no longer available. Please render it again.")
        return

    pdf_bytes = pdf_path.read_bytes()
    report_url = st.session_state.get("weekly_report_pdf_url")

    st.divider()
    st.subheader("Weekly Report")
    if report_url:
        st.markdown(
            f'<a href="{report_url}" target="_blank">Open PDF in new tab</a>',
            unsafe_allow_html=True,
        )
    st.download_button(
        "Download Weekly PDF",
        data=pdf_bytes,
        file_name=pdf_path.name,
        mime="application/pdf",
        use_container_width=True,
    )


# Dashboard data: controlled by the sidebar date range.
company = st.sidebar.selectbox("Company", ["400", "CRS"])
dashboard_mode = st.sidebar.radio("Dashboard", ["Company", "Employee", "Project Performance (AI)"])
today = date.today()
from_date = st.sidebar.date_input(
    "From date", value=today.replace(month=1, day=1), max_value=today
)
to_date = st.sidebar.date_input(
    "To date", value=today, min_value=from_date, max_value=today
)

st.sidebar.divider()
st.sidebar.subheader("Weekly report")
weekly_days_back = st.sidebar.slider(
    "Completed window days", min_value=7, max_value=90, value=7, step=7
)

if st.sidebar.button("Render Weekly Report", use_container_width=True):
    with st.spinner(f"Generating weekly PDF for company {company}..."):
        try:
            pdf_path = generate_weekly_report_pdf(
                company_code=company,
                days_back=weekly_days_back,
                output_dir="static/weekly_reports",
            )
            st.session_state.weekly_report_pdf_path = pdf_path
            st.session_state.weekly_report_pdf_url = f"/app/static/weekly_reports/{Path(pdf_path).name}"
            st.session_state.weekly_report_company = company
            st.session_state.weekly_report_days_back = weekly_days_back
            st.success("Weekly PDF is ready. Preview is shown below.")
        except Exception as exc:
            st.session_state.pop("weekly_report_pdf_path", None)
            st.session_state.pop("weekly_report_pdf_url", None)
            st.error(f"Could not generate weekly PDF: {exc}")

# Load Company baseline data
rows = load_company_data(company, from_date.isoformat(), to_date.isoformat())
df = clean_rows(rows)
_show_weekly_pdf_preview(company, weekly_days_back)

# Build Employee ID-to-Name lookup dictionary for resolving Support Team names
emp_map = {}
if not df.empty and {"EmployeeId", "Employee"}.issubset(df.columns):
    emp_map = (
        df[["EmployeeId", "Employee"]]
        .dropna(subset=["EmployeeId", "Employee"])
        .assign(
            EmployeeId=lambda data: data["EmployeeId"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip(),
            Employee=lambda data: data["Employee"].astype(str).str.strip(),
        )
        .drop_duplicates()
        .set_index("EmployeeId")["Employee"]
        .to_dict()
    )


# Common Employee Selector (Populated for Employee & Project Performance Modes)
employee_id = None
selected_employee = None
if dashboard_mode in ["Employee", "Project Performance (AI)"]:
    st.sidebar.divider()
    st.sidebar.subheader("Employee selection")
    if df.empty or not {"EmployeeId", "Employee"}.issubset(df.columns):
        st.warning("No employees were returned for the selected company and date range.")
        st.stop()
    employee_options = (
        df[["EmployeeId", "Employee"]]
        .dropna(subset=["EmployeeId", "Employee"])
        .assign(
            EmployeeId=lambda data: data["EmployeeId"].astype(str).str.replace(r"\.0$", "", regex=True),
            Employee=lambda data: data["Employee"].astype(str).str.strip(),
        )
        .drop_duplicates()
        .sort_values("Employee")
        .to_dict("records")
    )
    selected_employee = st.sidebar.selectbox(
        "Employee",
        employee_options,
        format_func=lambda employee: f"{employee['Employee']} ({employee['EmployeeId']})",
    )
    employee_id = selected_employee["EmployeeId"]


# Connected Project Selection (Populates only projects assigned to/worked on by the selected Employee)
project_options = {}
selected_project_code = None
if employee_id:
    # Query database strictly for projects linked to this employee
    emp_project_rows = load_project_ai_data(
        company_code=company,
        employee_id=employee_id,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat()
    )
    
    if emp_project_rows:
        # Filter unique projects
        processor_sidebar = ProjectDataProcessor(emp_project_rows)
        sidebar_tree = processor_sidebar.get_project_timeline_tree(exclude_completed=False)
        
        project_options = {
            f"📁 {p['Parent_Project_Name']} ({p['Parent_Project_Code']})": p["Parent_Project_Code"]
            for p in sidebar_tree
        }
        
        if project_options:
            selected_proj_label = st.sidebar.selectbox(
                "Select Employee's Project",
                options=list(project_options.keys()),
                key="selected_project_idx"
            )
            selected_project_code = project_options[selected_proj_label]


# =====================================================================
# VIEW 1: PROJECT PERFORMANCE (AI) - INTERCONNECTED
# =====================================================================
if dashboard_mode == "Project Performance (AI)":
    st.title("⚙️ Project Performance Dashboard (Active Portfolio)")
    
    with st.spinner("Processing performance records..."):
        # 1. Fetch Company-wide records for high-level baseline details
        raw_rows_company = load_project_ai_data(
            company_code=company,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat()
        )
        
        if not raw_rows_company:
            st.warning("No active project performance records found.")
            st.stop()
            
        processor_company = ProjectDataProcessor(raw_rows_company)
        
        # 2. Fetch Employee-specific records for the interactive explorer tree
        if employee_id:
            raw_rows_employee = load_project_ai_data(
                company_code=company,
                employee_id=employee_id,
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat()
            )
            processor_employee = ProjectDataProcessor(raw_rows_employee)
            tree = processor_employee.get_project_timeline_tree(exclude_completed=True)
        else:
            tree = processor_company.get_project_timeline_tree(exclude_completed=True)

    # 3. Synchronize Selected Project State BEFORE Rendering Top KPIs
    selected_project = None
    selected_label = None
    project_dict = {}

    if tree:
        project_dict = {f"{p['Parent_Project_Name']} ({p['Parent_Project_Code']})": p for p in tree}
        
        # Determine standard/default selected project
        project_tree_codes = [p["Parent_Project_Code"] for p in tree]
        default_idx = 0
        
        # Ensure safe type check to remove the yellow warning line
        if selected_project_code is not None and selected_project_code in project_tree_codes:
            default_idx = project_tree_codes.index(selected_project_code)
        
        default_label = list(project_dict.keys())[min(default_idx, len(project_dict) - 1)]
        
        # Pull selection index from state to update top KPI values in sync with radio clicks
        state_key = f"radio_active_projects_{company}_{employee_id}"
        selected_label = st.session_state.get(state_key, default_label)
        
        # Fallback protection if employee context changes
        if selected_label not in project_dict:
            selected_label = default_label
            
        selected_project = project_dict[selected_label]

    # 4. Compute Project-Specific KPIs
    if selected_project:
        # Calculate unique active team members involved in this specific project
        team_members = set()
        if selected_project.get("EmployeeId"):
            team_members.add(str(selected_project["EmployeeId"]).strip())
        
        support = selected_project.get("Team_Support", "")
        if support:
            for emp in str(support).split(","):
                if emp.strip():
                    team_members.add(emp.strip())
                    
        for action in selected_project["Sub_Actions"]:
            for log in action["Timeline_Logs"]:
                if log.get("ActionLoggedBy"):
                    team_members.add(str(log["ActionLoggedBy"]).strip())
                    
        total_team_members = len([t for t in team_members if t != "nan" and t != "None" and t != ""])
        
        # Calculate total actions logged on this project
        total_actions = sum(len(action["Timeline_Logs"]) for action in selected_project["Sub_Actions"])
        
        allocated_hours = float(selected_project.get("AllocatedHours", 0.0))
        used_hours = float(selected_project.get("TotalProjectUsedHours", 0.0))
        
        usage_rate = 0.0
        if allocated_hours > 0:
            usage_rate = round((used_hours / allocated_hours) * 100, 1)
    else:
        total_team_members = 0
        total_actions = 0
        allocated_hours = 0.0
        used_hours = 0.0
        usage_rate = 0.0

    # 5. Render Top Panels (AI Summary on Left, Project Specific KPIs on Right)
    left_top, right_top = st.columns([1.1, 1.6], gap="large")
    
    if "ai_perf_summary" not in st.session_state:
        st.session_state.ai_perf_summary = ""

    with left_top:
        with st.container(border=True):
            st.markdown('<div class="panel-label">✦ AI Selected Project Summary</div>', unsafe_allow_html=True)
            if st.button("✨ Generate AI Performance Summary", use_container_width=True):
                with st.spinner("Analyzing selected project..."):
                    st.session_state.ai_perf_summary = summarize_dashboard(
                        kpi_data={
                            "total_projects": 1,
                            "total_actions_logged": total_actions,
                            "total_employees": total_team_members,
                            "total_allocated_hours": allocated_hours,
                            "total_used_hours": used_hours
                        },
                        important_projects=None,
                        employee_summary=[selected_project] if selected_project else [],
                        current_project=selected_project
                    )
            summary_text = st.session_state.ai_perf_summary or (
                "Generate a summary to analyze this project's allocation timeline and delivery risks."
            )
            safe_summary = html.escape(summary_text).replace("\n", "<br>")
            st.markdown(f'<div class="ai-copy">{safe_summary}</div>', unsafe_allow_html=True)

    with right_top:
        # Dynamic project-specific KPI cards
        kpi_cards = [
            ("📁", "Project Status", selected_project["Status"] if selected_project else "N/A"),
            ("👥", "Active Team", total_team_members),
            ("⚡", "Actions Logged", total_actions),
            ("⏱", "Allocated Hours", f"{allocated_hours:.1f}"),
            ("⚙️", "Used Hours", f"{used_hours:.1f}"),
            ("📈", "Usage Rate", f"{usage_rate}%"),
        ]
        cards_html = "".join(
            f'<div class="kpi-card"><div>{icon}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-label">{label}</div></div>'
            for icon, label, value in kpi_cards
        )
        st.markdown(
            f'<div class="top-panel"><div class="panel-label">Selected Project Metrics</div>'
            f'<div class="kpi-grid">{cards_html}</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # 6. Interactive Explorer (Synchronized with the top panels)
    st.subheader("📋 Incomplete Projects & Actions Explorer")
    if not tree:
        st.info("No incomplete projects found for the selected employee.")
    else:
        left_list, right_detail = st.columns([1, 2], gap="large")
        
        with left_list:
            st.markdown("**Select Active Project to Explore**")
            
            # Render radio list synchronized with the default selected label index
            selected_option = st.radio(
                "Active Projects",
                options=list(project_dict.keys()),
                index=list(project_dict.keys()).index(selected_label),
                key=f"radio_active_projects_{company}_{employee_id}", 
                label_visibility="collapsed"
            )
            # Re-verify matching record selection
            selected_project = project_dict[selected_option]

        with right_detail:
            st.subheader(f"📁 Project: {selected_project['Parent_Project_Name']}")
            st.write(f"**Description**: {selected_project['Parent_Project_Description'] or 'No description provided.'}")
            
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            with meta_col1:
                st.metric("Status", selected_project["Status"])
                st.write(f"**Responsible**: {selected_project['Employee']}")
            with meta_col2:
                st.metric("Allocated Hours", f"{selected_project['AllocatedHours']} hrs")
                st.write(f"**Deadline**: {selected_project['DeadLine'] or 'Not available'}")
            with meta_col3:
                st.metric("Total Hours Spent", f"{selected_project['TotalProjectUsedHours']} hrs")
                st.write(f"**Budget/Cost**: {selected_project['Cost']:.2f}")

            # Resolve Support Team IDs to Names
            support_ids = selected_project.get("Team_Support", "")
            support_names = []
            if support_ids:
                for emp_id in str(support_ids).split(","):
                    clean_id = emp_id.strip()
                    if clean_id:
                        # Get real name from map, fallback to ID if name is not found in company directory
                        support_names.append(emp_map.get(clean_id, f"ID: {clean_id}"))
            
            support_display = ", ".join(support_names) if support_names else "No support resources listed."

            st.write(f"**Support Team**: {support_display}")

            # Sub-Actions
            st.markdown("### 🔨 Project Sub-Actions & Milestones")
            if not selected_project["Sub_Actions"]:
                st.info("No sub-actions found for this project.")
            else:
                actions_data = []
                for action in selected_project["Sub_Actions"]:
                    actions_data.append({
                        "Action Code": action["Action_Code"],
                        "Action Name": action["Action_Name"],
                        "Allocated Hours": action["AllocatedHours"],
                        "Hours Used": action["ActionUsedHours"],
                        "Status": action["Status"]
                    })
                st.dataframe(pd.DataFrame(actions_data), use_container_width=True, hide_index=True)

                # Chronological timelines
                st.markdown("### 📝Action Timeline")
                all_logs = []
                for action in selected_project["Sub_Actions"]:
                    for log in action["Timeline_Logs"]:
                        all_logs.append({
                            "Date": log["TimelineDate"],
                            "Action / Sub-Project": action["Action_Name"],
                            "Start": log["StartTime"],
                            "End": log["EndTime"],
                            "Time Logged": log["DailyTimeSpent"],
                            "Work Achieved": log["WorkAchieved"],
                            "Status": log["DailyReportStatus"],
                            "Logged By Employee ID": log["ActionLoggedBy"]
                        })
                
                if not all_logs:
                    st.info("No daily logs registered on this project's actions.")
                else:
                    logs_df = pd.DataFrame(all_logs).sort_values("Date", ascending=False)
                    st.dataframe(logs_df, use_container_width=True, hide_index=True)
    st.stop()


# =====================================================================
# VIEW 2: ORIGINAL EMPLOYEE TIMELINE VIEW
# =====================================================================
if dashboard_mode == "Employee":
    days_back = st.sidebar.slider("Timeline days", min_value=7, max_value=90, value=90, step=7)
    
    employee_dashboard = get_employee_timeline_dashboard(
        employee_id=employee_id,
        company_code=company,
        days_back=days_back,
    )
    employee_kpi = employee_dashboard["summary"]
    employee_df = clean_timeline_rows(
        load_employee_important_project_data(employee_id=employee_id, company_code=company)
    )
    employee_important = get_employee_important_projects(employee_df)
    employee_project_map = {}
    employee_project_options = []
    for key, label in (
        ("urgent_project", "🚨 Urgent"),
        ("high_cost_project", "💰 High Cost"),
        ("historical_project", "📅 Historical"),
    ):
        item = employee_important[key]
        if item:
            text = f"{label} - {item['Project_Name']}"
            employee_project_options.append(text)
            employee_project_map[text] = item["Project_Code"]
    # If none of the three important-project rules applies, keep the employee
    # dashboard useful by showing their most recently created parent project.
    if not employee_project_options and employee_important["recent_project"]:
        item = employee_important["recent_project"]
        text = f"🕒 Recent - {item['Project_Name']}"
        employee_project_options.append(text)
        employee_project_map[text] = item["Project_Code"]
    st.title(f"👤 {selected_employee['Employee']} Dashboard")
    left_top, right_top = st.columns([1.1, 1.6], gap="large")
    with left_top:
        with st.container(border=True):
            st.markdown('<div class="panel-label">Employee Overview</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="ai-copy">Timeline period: <b>last {days_back} days</b><br><br>'
                f'Employee ID: <b>{employee_id}</b><br><br>'
                f'This view includes the employee\'s assigned projects, actions, and daily work logs. '
                f'Important projects use the independent employee project history.</div>',
                unsafe_allow_html=True,
            )
    with right_top:
        employee_cards = [
            ("📁", "Projects", employee_kpi["total_projects"]),
            ("⚡", "Actions", employee_kpi["total_actions"]),
            ("✅", "Completed", employee_kpi["completed_projects"]),
            ("⏱", "Remaining", employee_kpi["remaining_projects"]),
            ("🏆", "Achievement", f'{employee_kpi["achievement_pct"]}%'),
            ("📅", "Timeline days", days_back),
        ]
        cards_html = "".join(
            f'<div class="kpi-card"><div>{icon}</div><div class="kpi-value">{value}</div>'
            f'<div class="kpi-label">{label}</div></div>'
            for icon, label, value in employee_cards
        )
        st.markdown(
            f'<div class="top-panel"><div class="panel-label">Employee Metrics</div>'
            f'<div class="kpi-grid">{cards_html}</div></div>',
            unsafe_allow_html=True,
        )
    st.divider()
    employee_left, employee_right = st.columns([1, 2], gap="large")
    selected_employee_project = None
    with employee_left:
        st.subheader("🚨 Focus Projects")
        if employee_project_options:
            selected_employee_project = st.radio(
                "", employee_project_options, label_visibility="collapsed"
            )
        else:
            st.info("No projects were found for this employee.")
    with employee_right:
        st.subheader("📌 Selected Project")
        if selected_employee_project:
            employee_project = get_employee_project_details(
                employee_df,
                employee_project_map[selected_employee_project],
                employee_id,
            )
            st.write(f"**{employee_project.get('Project_Name', '')}**")
            st.write(f"Status: {employee_project.get('Status', '')}")
            st.write(f"Deadline: {employee_project.get('Deadline') or 'Not available'}")
            st.write(f"Actions logged: {employee_project.get('Total_Actions_Logged', 0)}")
        else:
            employee_project = {"Actions": []}
            st.info("Select an important project to view its details.")
    st.divider()
    st.subheader("📋 Recent Daily Timeline")
    timeline_df = pd.DataFrame(employee_dashboard["timeline_records"])
    if timeline_df.empty:
        st.info(f"No timeline records found in the last {days_back} days.")
    else:
        st.dataframe(timeline_df, use_container_width=True, hide_index=True)
    st.divider()
    st.subheader("📝 Selected Project Work Logs")
    project_actions_df = pd.DataFrame(employee_project.get("Actions", []))
    if project_actions_df.empty:
        st.info("No work logs found for the selected project.")
    else:
        st.dataframe(project_actions_df, use_container_width=True, hide_index=True)
    st.stop()


# =====================================================================
# VIEW 3: ORIGINAL COMPANY PROJECT DASHBOARD
# =====================================================================
kpi = compute_kpis(df)
emp_summary = employee_summary(df)
# Important Projects are intentionally independent from the sidebar date range.
important_df = clean_rows(load_important_project_data(company))
important = get_important_projects(important_df)
project_map = {}
options = []
for key, label in (
    ("urgent_project", "🚨 Urgent"),
    ("high_cost_project", "💰 High Cost"),
    ("historical_project", "📅 Historical"),
):
    item = important[key]
    if item:
        text = f"{label} - {item['Project_Name']}"
        options.append(text)
        project_map[text] = item["Project_Code"]
selected = options[0] if options else None
project = (
    project_details(important_df, project_map[selected])
    if selected else {"Employees": [], "Actions": []}
)

st.title("📊 Company Project Dashboard")
# Top left and top right panels match dashboard_mockup.html.
left_top, right_top = st.columns([1.1, 1.6], gap="large")
if "ai_summary" not in st.session_state:
    st.session_state.ai_summary = ""
with left_top:
    with st.container(border=True):
        st.markdown('<div class="panel-label">✦ AI Executive Summary</div>', unsafe_allow_html=True)
        if st.button("✨ Generate AI Summary", use_container_width=True):
            with st.spinner("Analyzing dashboard..."):
                st.session_state.ai_summary = summarize_dashboard(
                    kpi, important, emp_summary.to_dict("records"), project
                )
        summary_text = st.session_state.ai_summary or (
            "Generate a summary to see project risks, progress, and recommended actions."
        )
        safe_summary = html.escape(summary_text).replace("\n", "<br>")
        st.markdown(f'<div class="ai-copy">{safe_summary}</div>', unsafe_allow_html=True)
with right_top:
    kpi_cards = [
        ("📁", "Projects", kpi["total_projects"]),
        ("👥", "Employees", kpi["total_employees"]),
        ("✅", "Completed", kpi["completed_projects"]),
        ("⚡", "Actions", kpi["total_actions"]),
        ("🏆", "Achievement", f'{kpi["achievement_pct"]}%'),
        ("⏱", "Remaining", kpi["remaining_projects"]),
    ]
    cards_html = "".join(
        f'<div class="kpi-card"><div>{icon}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-label">{label}</div></div>'
        for icon, label, value in kpi_cards
    )
    st.markdown(
        f'<div class="top-panel"><div class="panel-label">Key Metrics</div>'
        f'<div class="kpi-grid">{cards_html}</div></div>',
        unsafe_allow_html=True,
    )
st.divider()
left, right = st.columns([1, 2], gap="large")
with left:
    st.subheader("🚨 Focus Projects")
    if options:
        selected = st.radio("", options, label_visibility="collapsed")
        project = project_details(important_df, project_map[selected])
    else:
        st.info("No focus projects match the current business rules.")
with right:
    st.subheader("👨‍💻 Employees Working On This Project")
    employee_df = pd.DataFrame(project["Employees"])
    if employee_df.empty:
        st.info("No employees found.")
    else:
        st.dataframe(employee_df, use_container_width=True, hide_index=True)
st.divider()
st.subheader("📋 Active Actions")
action_df = pd.DataFrame(project["Actions"])
if action_df.empty:
    st.info("No active actions.")
else:
    st.dataframe(action_df, use_container_width=True, hide_index=True)
st.divider()
st.subheader("👥 Company Employee Summary")
st.dataframe(emp_summary, use_container_width=True, hide_index=True)