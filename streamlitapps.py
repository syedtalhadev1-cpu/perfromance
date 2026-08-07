import html
from datetime import date

import pandas as pd
import streamlit as st

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
from summarize import summarize_dashboard


st.set_page_config(page_title="Company Dashboard", page_icon="📊", layout="wide")

# Styling for the top section, based on dashboard_mockup.html.
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


# Dashboard data: controlled by the sidebar date range.
company = st.sidebar.selectbox("Company", ["400", "CRS"])
dashboard_mode = st.sidebar.radio("Dashboard", ["Company", "Employee"])
today = date.today()
from_date = st.sidebar.date_input(
    "From date", value=today.replace(month=1, day=1), max_value=today
)
to_date = st.sidebar.date_input(
    "To date", value=today, min_value=from_date, max_value=today
)

rows = load_company_data(company, from_date.isoformat(), to_date.isoformat())
df = clean_rows(rows)

if dashboard_mode == "Employee":
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
    days_back = st.sidebar.slider("Timeline days", min_value=7, max_value=90, value=90, step=7)
    employee_id = selected_employee["EmployeeId"]

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
        st.subheader("🚨 Important Projects")
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
