import os
import pyodbc
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from datetime import datetime, timedelta

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


# =====================================================
# 1. LOAD DATA FROM STORED PROCEDURE (Employee-Only)
# =====================================================

def load_employee_timeline(
    employee_id,
    company_code=None,
    days_back=121
):
    """
    Loads the daily timeline logs and project details strictly for the specified employee.
    """
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        
        cursor.execute(
            """
            EXEC u.sp_ai_GetEmployeeProjectsAndTimeline
                @EmployeeId=?,
                @CompanyCode=?,
                @DaysBack=?
            """,
            employee_id,
            company_code,
            days_back,
        )

        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return rows

    except pyodbc.Error as db_err:
        print(f"Database error loading employee timeline: {str(db_err)}")
        return []
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


def load_important_project_data(employee_id, company_code="400"):
    """Loads long-term historical projects strictly for the specified employee."""
    # 3-year lookback for this employee's old active projects
    days_back = 3 * 365 
    
    return load_employee_timeline(
        employee_id=employee_id,
        company_code=company_code,
        days_back=days_back
    )
def get_past_3_months_status_trend(rows):

    if rows is None:
        return pd.DataFrame()

    if isinstance(rows, pd.DataFrame):
        if rows.empty:
            return pd.DataFrame()
        df = rows.copy()
    else:
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame()

    required = [
        "TimelineDate",
        "Project_Code",
        "Status"
    ]

    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    t = df.copy()
    p = df.copy()

    if "TimelineDate" not in t.columns:
        return pd.DataFrame()

    if "Project_Code" not in t.columns:
        return pd.DataFrame()

    if "Project_Code" not in p.columns:
        return pd.DataFrame()

    if "Status" not in p.columns:
        return pd.DataFrame()

    t["TestDate"] = pd.to_datetime(
        t["TimelineDate"],
        errors="coerce"
    )

    t = t.dropna(subset=["TestDate"])

    today = pd.Timestamp.today().normalize()
    current_month = today.replace(day=1)
    start_month = current_month - pd.DateOffset(months=4)

    t = t[
        (t["TestDate"] >= start_month) &
        (t["TestDate"] <= today)
    ].copy()

    if t.empty:
        return pd.DataFrame()

    t["ProjectKey"] = (
        t["Project_Code"]
        .astype(str)
        .str.strip()
    )

    p["ProjectKey"] = (
        p["Project_Code"]
        .astype(str)
        .str.strip()
    )

    p["StatusClean"] = (
        p["Status"]
        .fillna("Unknown")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    status_map = {
        "completed": "Completed",
        "complete": "Completed",
        "inprocess": "InProcess",
        "in process": "InProcess",
        "in-progress": "InProcess",
        "in progress": "InProcess",
        "delay": "Delayed",
        "delayed": "Delayed"
    }

    p["StatusClean"] = (
        p["StatusClean"]
        .map(status_map)
        .fillna(p["StatusClean"].str.title())
    )

    project_status = (
        p[
            [
                "ProjectKey",
                "StatusClean"
            ]
        ]
        .drop_duplicates("ProjectKey")
    )

    df = t.merge(
        project_status,
        on="ProjectKey",
        how="left"
    )

    df["StatusClean"] = df["StatusClean"].fillna("Unknown")

    df["MonthDate"] = (
        df["TestDate"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    df["Month"] = (
        df["MonthDate"]
        .dt.strftime("%b %Y")
    )

    trend = (
        df.groupby(
            [
                "MonthDate",
                "Month",
                "StatusClean"
            ]
        )["ProjectKey"]
        .nunique()
        .reset_index(
            name="ProjectCount"
        )
    )

    return trend.sort_values(
        ["MonthDate", "StatusClean"]
    )


# =====================================================
# 2. CLEAN DATA
# =====================================================

def clean_timeline_rows(rows):
    """Cleans raw row data and dynamically resolves the date column name to prevent KeyError."""
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # Dynamically map the date column to prevent KeyError
    possible_date_cols = ["DailyWorkDate", "TimelineDate", "WorkDate", "date"]
    found_date_col = None
    for col in possible_date_cols:
        if col in df.columns:
            found_date_col = col
            break

    if found_date_col and found_date_col != "DailyWorkDate":
        df["DailyWorkDate"] = df[found_date_col]

    # Clean text nulls to prevent JSON errors
    text_cols = ["WorkAchieved", "StartTime", "EndTime", "TimeCount", "Status"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("")

    # Parse standard date columns
    date_cols = ["DailyWorkDate", "DeadLine", "CreatedOn", "Project_EndDate"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df


# =====================================================
# 3. PROJECTS (Strict Rule: TaskType='Project' and Master_Code is Empty)
# =====================================================

def get_projects(df):
    if df.empty:
        return df

    projects = df[
        (df["TaskType"].astype(str).str.strip().str.lower() == "project") &
        (df["Master_Code"].isna() | df["Master_Code"].astype(str).str.strip().eq(""))
    ].copy()

    return projects


# =====================================================
# 4. ACTIONS (Strict Rule: TaskType='Action' and Master_Code is NOT Empty)
# =====================================================

def get_actions(df):
    if df.empty:
        return df

    actions = df[
        (df["TaskType"].astype(str).str.strip().str.lower() == "action") &
        (df["Master_Code"].notna()) &
        (df["Master_Code"].astype(str).str.strip().ne(""))
    ].copy()

    # The employee stored procedure can return a person's action/timeline row
    # without also returning the parent-project row.  Do not discard that valid
    # action merely because its Master_Code is absent from this result set.

    return actions


# =====================================================
# 5.1 EMPLOYEE-SPECIFIC KPI COMPUTATION
# =====================================================

def compute_employee_kpis(df, employee_id):
    """
    Computes KPIs strictly scoped to a single employee's assigned parent projects and actions.
    """
    if df.empty:
        return {
            "employee_id": employee_id,
            "total_projects": 0,
            "total_actions": 0,
            "completed_projects": 0,
            "remaining_projects": 0,
            "achievement_pct": 0
        }

    projects = get_projects(df)
    actions = get_actions(df)

    # 1. Parent Projects explicitly assigned to the employee
    assigned_project_codes = set()
    if not projects.empty and "Team_Res" in projects.columns:
        emp_projects = projects[projects["Team_Res"].astype(str).str.strip() == str(employee_id)]
        assigned_project_codes = set(emp_projects["Project_Code"].dropna().astype(str).str.strip())

    # 2. Parent projects where the employee completed daily actions in this period
    worked_project_codes = set()
    if not actions.empty and "Master_Code" in actions.columns:
        worked_project_codes = set(actions["Master_Code"].dropna().astype(str).str.strip())

    # 3. Combine both lists to get the TRUE unique parent projects they are involved with
    all_unique_projects = assigned_project_codes.union(worked_project_codes)
    all_unique_projects = {p for p in all_unique_projects if p != "" and p != "nan" and p != "None"}

    total_projects = len(all_unique_projects)
    # The procedure returns one row per daily work log, so count each action
    # code once for the KPI.  The timeline still shows every daily log.
    total_actions = actions["Project_Code"].nunique()

    completed_projects = 0
    if not projects.empty and "Status" in projects.columns:
        completed_projects = projects.loc[
            (projects["Status"].astype(str).str.strip().str.lower().eq("completed")) &
            (projects["Project_Code"].astype(str).str.strip().isin(all_unique_projects)),
            "Project_Code",
        ].nunique()

    remaining_projects = total_projects - completed_projects
    achievement = round((completed_projects / total_projects) * 100, 1) if total_projects else 0

    return {
        "employee_id": employee_id,
        "total_projects": total_projects,
        "total_actions": total_actions,
        "completed_projects": completed_projects,
        "remaining_projects": remaining_projects,
        "achievement_pct": achievement
    }


# =====================================================
# 6. IMPORTANT PROJECTS (Employee-Specific version)
# =====================================================

def get_important_projects(df):
    """
    Identifies Urgent, High Cost, and Historical projects strictly for the single employee.
    """
    projects = get_projects(df).copy()
    if projects.empty:
        return {
            "urgent_project": None,
            "high_cost_project": None,
            "historical_project": None,
            "recent_project": None,
        }

    # Safe Column Mappings from PM.* output
    if "Duration" in projects.columns and "AllocatedHours" not in projects.columns:
        projects["AllocatedHours"] = pd.to_numeric(projects["Duration"], errors="coerce").fillna(0)
    if "Project_Cost" in projects.columns and "Cost" not in projects.columns:
        projects["Cost"] = pd.to_numeric(projects["Project_Cost"], errors="coerce").fillna(0)
    if "CreatedOn" in projects.columns and "CreatedDate" not in projects.columns:
        projects["CreatedDate"] = pd.to_datetime(projects["CreatedOn"], errors="coerce")
    if "UsedHours" not in projects.columns:
        projects["UsedHours"] = 0.0 # Default to 0 if not tracked natively

    today = pd.Timestamp.today().normalize()

    # Match Project Scope
    if "ProjectType" in projects.columns:
        projects = projects[
            projects["ProjectType"].astype(str).str.strip().str.lower().eq("core tasks")
        ].copy()

    # --- Case 1: Urgent ---
    urgent = projects[
        (projects["DeadLine"] >= today) &
        (projects["DeadLine"] <= today + pd.Timedelta(days=7)) &
        (~projects["Status"].str.contains("Completed", case=False, na=False))
    ].sort_values("DeadLine")

    urgent_project = urgent.iloc[0].to_dict() if not urgent.empty else None

    # Clean Datetime columns in dictionary outputs for JSON serialization safety
    if urgent_project:
        for k, v in urgent_project.items():
            if isinstance(v, pd.Timestamp):
                urgent_project[k] = v.strftime('%Y-%m-%d')

    # --- Case 2: High Cost ---
    normalised_status = (
        projects["Status"].fillna("").astype(str).str.lower().str.replace(r"[\s_-]", "", regex=True)
    )
    usage_percent = (projects["UsedHours"] / projects["AllocatedHours"].replace(0, np.nan)).mul(100).fillna(0)

    cost_threshold = projects["Cost"].quantile(0.75) if not projects.empty else 0
    high = projects[
        (projects["Cost"] >= cost_threshold) &
        (normalised_status.isin(["delay", "delayed"]) | (normalised_status.eq("inprocess") & usage_percent.le(55)))
    ].copy()

    if not high.empty:
        priority = normalised_status.loc[high.index].isin(["delay", "delayed"])
        high = high.assign(_delay_first=priority).sort_values(["_delay_first", "Cost"], ascending=[False, False])
        high_project = high.iloc[0].to_dict()
    else:
        high_project = None

    if high_project:
        for k, v in high_project.items():
            if isinstance(v, pd.Timestamp):
                high_project[k] = v.strftime('%Y-%m-%d')

    # --- Case 3: Historical ---
    historical = projects[
        (projects["CreatedDate"].dt.year == today.year - 1) &
        (projects["CreatedDate"].dt.month == today.month) &
        (~projects["Status"].str.contains("Completed", case=False, na=False))
    ].copy()

    historical_project = historical.sort_values("CreatedDate").iloc[0].to_dict() if not historical.empty else None

    if historical_project:
        for k, v in historical_project.items():
            if isinstance(v, pd.Timestamp):
                historical_project[k] = v.strftime('%Y-%m-%d')

    # Fallback for employees who have no urgent, high-cost, or historical
    # project.  This is their latest parent project, independent of status.
    recent_project = None
    if not projects.empty and "CreatedDate" in projects.columns:
        recent = projects.sort_values("CreatedDate", ascending=False)
        recent = recent.drop_duplicates(subset="Project_Code")
        if not recent.empty:
            recent_project = recent.iloc[0].to_dict()
            for k, v in recent_project.items():
                if isinstance(v, pd.Timestamp):
                    recent_project[k] = v.strftime('%Y-%m-%d')

    return {
        "urgent_project": urgent_project,
        "high_cost_project": high_project,
        "historical_project": historical_project,
        "recent_project": recent_project,
    }


# =====================================================
# 8. EMPLOYEE TIMELINE GENERATION
# =====================================================

def get_employee_timeline_dashboard(employee_id, company_code=None, days_back=7):
    """
    Combines single-employee KPIs with their daily timeline activities over the last X days.
    """
    raw_rows = load_employee_timeline(employee_id, company_code, days_back)
    df = clean_timeline_rows(raw_rows)

    if df.empty or "DailyWorkDate" not in df.columns:
        return {
            "summary": {
                "employee_id": employee_id,
                "total_projects": 0,
                "total_actions": 0,
                "completed_projects": 0,
                "remaining_projects": 0,
                "achievement_pct": 0
            },
            "timeline_records": [],
            "important_projects": {
                "urgent_project": None,
                "high_cost_project": None,
                "historical_project": None
            }
        }

    # Compute personal KPIs and get single employee important projects
    employee_summary_kpis = compute_employee_kpis(df, employee_id)
    important_projects = get_important_projects(df)

    # Filter out active timeline items (rows representing actual daily work logged)
    timeline_df = df[df["DailyWorkDate"].notna()].copy()
    timeline_records = []

    if not timeline_df.empty:
        timeline_df["DailyWorkDate"] = timeline_df["DailyWorkDate"].dt.strftime('%Y-%m-%d')
        
        timeline_records = timeline_df[[
            "DailyWorkDate",
            "StartTime",
            "EndTime",
            "TimeCount",
            "WorkAchieved",
            "Status",
            "Project_Code",
            "Project_Name",
            "Master_Code"
        ]].to_dict(orient="records")

    return {
        "summary": employee_summary_kpis,
        "timeline_records": timeline_records,
        "important_projects": important_projects
    }


# =====================================================
# 9. DRILL-DOWN: EMPLOYEE PROJECT DETAILS
# =====================================================

def get_employee_project_details(df, project_code, employee_id):
    projects = get_projects(df)
    
    project = projects[projects["Project_Code"] == project_code]
    if project.empty:
        return {}

    project = project.iloc[0]
    
    project_code = str(project_code).strip()
    employee_project_actions = df[
        (
            df["Project_Code"].astype(str).str.strip().eq(project_code) |
            df["Master_Code"].astype(str).str.strip().eq(project_code)
        ) &
        (df["DailyWorkDate"].notna())
    ].copy()

    total_actions = len(employee_project_actions)
    completed_actions = 0
    
    if total_actions > 0 and "Status" in employee_project_actions.columns:
        completed_actions = len(
            employee_project_actions[
                employee_project_actions["Status"].str.contains("Completed", case=False, na=False)
            ]
        )

    actions_list = []
    if not employee_project_actions.empty:
        employee_project_actions["DailyWorkDate"] = employee_project_actions["DailyWorkDate"].dt.strftime('%Y-%m-%d')
        actions_list = employee_project_actions[[
            "DailyWorkDate",
            "StartTime",
            "EndTime",
            "TimeCount",
            "WorkAchieved",
            "Status"
        ]].to_dict(orient="records")

    return {
        "Project_Code": project_code,
        "Project_Name": project["Project_Name"],
        "Description": project.get("Project_Description", ""),
        "Status": project.get("Status", "InProcess"),
        "Deadline": project["DeadLine"].strftime('%Y-%m-%d') if pd.notna(project["DeadLine"]) else None,
        "Total_Actions_Logged": total_actions,
        "Completed_Actions_Logged": completed_actions,
        "Pending_Actions_Logged": total_actions - completed_actions,
        "Actions": actions_list
    }
