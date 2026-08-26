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


def parse_hours(value):
    try:
        if pd.isna(value):
            return 0.0
        text = str(value).strip()
        if ":" in text:
            hours, minutes = text.split(":", 1)
            return int(hours) + int(minutes) / 60
        return float(text)
    except (TypeError, ValueError):
        return 0.0


# =====================================================
# 1. LOAD DATA FROM STORED PROCEDURE
# =====================================================

def load_company_data(
    company_code="400",
    from_date=None,
    to_date=None,
):

    # Default to the current calendar year, not all historical data.
    # A caller may still provide a specific range.
    today = datetime.today().date()
    from_date = from_date or today.replace(month=1, day=1).isoformat()
    to_date = to_date or today.isoformat()

    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            EXEC u.sp_ai_GetCompanyProjects
                @CompanyCode=?,
                @FromDate=?,
                @ToDate=?
            """,
            company_code,
            from_date,
            to_date,
        )

        columns = [c[0] for c in cursor.description]

        rows = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return rows

    finally:

        cursor.close()
        conn.close()


def load_important_project_data(company_code="400"):
    """Load data for Important Projects independently of dashboard filters."""
    today = datetime.today().date()
    # Urgent projects can have been created well before their deadline.
    # Keep a separate three-year lookback so old active projects due this week
    # are not removed by the dashboard's reporting date range.
    from_date = today - timedelta(days=3 * 365)
    to_date = today + timedelta(days=7)

    return load_company_data(
        company_code,
        from_date.isoformat(),
        to_date.isoformat(),
    )


# =====================================================
# 2. CLEAN DATA
# =====================================================

def clean_rows(rows):

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    date_cols = [
        "DeadLine",
        "CreatedDate",
        "DPG"
    ]

    for col in date_cols:

        if col in df.columns:

            df[col] = pd.to_datetime(
                df[col],
                errors="coerce"
            )

    numeric_cols = [
        "AllocatedHours",
        "UsedHours",
        "Cost"
    ]

    for col in numeric_cols:

        if col in df.columns:

            df[col] = df[col].map(parse_hours)

    if "UsedHours" in df.columns and {"Master_Code", "Project_Code"}.issubset(df.columns):
        time_col = next(
            (col for col in ("DailyTimeSpent", "TimeCount") if col in df.columns),
            None,
        )
        date_col = next(
            (col for col in ("TimelineDate", "DailyWorkDate", "WorkDate") if col in df.columns),
            None,
        )
        if time_col and date_col:
            logged = df[df[date_col].notna()].copy()
            logged["_LoggedHours"] = logged[time_col].map(parse_hours)
            logged_hours = logged.groupby("Master_Code")["_LoggedHours"].sum()
            parent_mask = df["Master_Code"].isna() | df["Master_Code"].astype(str).str.strip().eq("")
            fallback = df.loc[parent_mask, "Project_Code"].map(logged_hours).fillna(0)
            df.loc[parent_mask, "UsedHours"] = df.loc[parent_mask, "UsedHours"].where(
                df.loc[parent_mask, "UsedHours"] > 0,
                fallback,
            )

    return df


# =====================================================
# 3. PROJECTS
# =====================================================

def get_projects(df):

    projects = df[
        (df["TaskType"].astype(str).str.strip().str.lower() == "project") &
        # SQL may return a NULL or an empty Master_Code for a parent project.
        (df["Master_Code"].isna() | df["Master_Code"].astype(str).str.strip().eq(""))
    ].copy()

    return projects


# =====================================================
# 4. ACTIONS
# =====================================================

def get_actions(df):

    actions = df[
        (df["TaskType"].astype(str).str.strip().str.lower() == "action") &
        (df["Master_Code"].notna()) &
        (df["Master_Code"].astype(str).str.strip().ne(""))
    ].copy()

    # An action belongs to a project only when its Master_Code references an
    # actual parent Project_Code in the same dataset.
    project_codes = set(
        get_projects(df)["Project_Code"].dropna().astype(str).str.strip()
    )
    actions = actions[
        actions["Master_Code"].astype(str).str.strip().isin(project_codes)
    ].copy()

    return actions


# =====================================================
# 5. KPI
# =====================================================

def compute_kpis(df):

    projects = get_projects(df)

    actions = get_actions(df)

    total_projects = projects["Project_Code"].nunique()

    total_actions = actions["Project_Code"].nunique()

    total_employees = df["EmployeeId"].nunique()

    # The stored procedure can return more than one row for the same parent
    # project. Count completed *project codes*, not returned rows, so that a
    # project can never be counted as completed twice.
    completed_projects = projects.loc[
        projects["Status"].astype(str).str.strip().str.lower().eq("completed"),
        "Project_Code",
    ].nunique()

    remaining_projects = (
        total_projects -
        completed_projects
    )

    achievement = round(

        (
            completed_projects /
            total_projects
        ) * 100,

        1

    ) if total_projects else 0

    return {

        "total_projects": total_projects,

        "total_actions": total_actions,

        "total_employees": total_employees,

        "completed_projects": completed_projects,

        "remaining_projects": remaining_projects,

        "achievement_pct": achievement

    }


# =====================================================
# 6. IMPORTANT PROJECTS
# =====================================================

def get_important_projects(df):

    projects = get_projects(df).copy()

    # Important Projects always uses the real current date.  It must not be
    # affected by the date range selected for KPIs and dashboard tables.
    today = pd.Timestamp.today().normalize()

    # Match the important-project scope used in model.py when this column is
    # supplied by the stored procedure.
    if "ProjectType" in projects.columns:
        projects = projects[
            projects["ProjectType"].astype(str).str.strip().str.lower().eq("core tasks")
        ].copy()

    action_counts = get_actions(df).groupby("Master_Code")["Project_Code"].nunique()
    projects["TotalActions"] = projects["Project_Code"].map(action_counts).fillna(0).astype(int)

    # --------------------------------
    # CASE 1
    # Urgent
    # --------------------------------

    urgent = projects[

        # Match the database urgent check: today through the next seven days.
        (projects["DeadLine"] >= today) &

        (projects["DeadLine"] <= today + pd.Timedelta(days=7)) &

        (~projects["Status"].str.contains(
            "Completed",
            case=False,
            na=False
        ))

    ].sort_values("DeadLine")

    urgent_project = (

        urgent.iloc[0].to_dict()

        if not urgent.empty

        else None

    )

    # --------------------------------
    # CASE 2
    # High Cost
    # --------------------------------

    # Apply the same high-cost rules as model.py.
    normalised_status = (
        projects["Status"]
        .fillna("")
        .astype(str)
        .str.lower()
        .str.replace(r"[\s_-]", "", regex=True)
    )

    usage_percent = (
        projects["UsedHours"] /
        projects["AllocatedHours"].replace(0, np.nan)
    ).mul(100).fillna(0)

    if not projects.empty:

        cost_threshold = projects["Cost"].quantile(0.75)

        high = projects[
            (projects["Cost"] >= cost_threshold) &
            (
                normalised_status.isin(["delay", "delayed"]) |
                (
                    normalised_status.eq("inprocess") &
                    usage_percent.le(55)
                )
            )
        ].copy()

        priority = normalised_status.loc[high.index].isin(["delay", "delayed"])
        high = high.assign(_delay_first=priority).sort_values(
            ["_delay_first", "Cost"],
            ascending=[False, False],
        )

    else:
        high = projects.copy()

    high_project = (

        high.iloc[0].to_dict()

        if not high.empty

        else None

    )

    # --------------------------------
    # CASE 3
    # Historical
    # --------------------------------

    historical = projects[
        (projects["CreatedDate"].dt.year == today.year - 1) &
        (projects["CreatedDate"].dt.month == today.month) &
        (~projects["Status"].str.contains("Completed", case=False, na=False))
    ].copy()

    if not historical.empty:

        historical = historical.sort_values(
            "CreatedDate"
        )

    historical_project = (

        historical.iloc[0].to_dict()

        if not historical.empty

        else None

    )

    return {

        "urgent_project": urgent_project,

        "high_cost_project": high_project,

        "historical_project": historical_project

    }
# =====================================================
# 7. PROJECT SUMMARY
# =====================================================

def project_summary(df):

    projects = get_projects(df)
    actions = get_actions(df)

    data = []

    for _, project in projects.iterrows():

        project_code = project["Project_Code"]

        project_actions = actions[
            actions["Master_Code"] == project_code
        ]

        total_actions = project_actions["Project_Code"].nunique()

        completed_actions = project_actions.loc[
            project_actions["Status"].str.contains("Completed", case=False, na=False),
            "Project_Code",
        ].nunique()

        pending_actions = total_actions - completed_actions

        progress = round(
            (completed_actions / total_actions) * 100,
            1
        ) if total_actions else 0

        data.append({

            "Project_Code": project_code,

            "Project_Name": project["Project_Name"],

            "Owner": project["Employee"],

            "Status": project["Status"],

            "Deadline": project["DeadLine"],

            "Cost": project["Cost"],

            "Total_Actions": total_actions,

            "Completed_Actions": completed_actions,

            "Pending_Actions": pending_actions,

            "Progress": progress

        })

    return pd.DataFrame(data)


def project_details(df, project_code):

    projects = get_projects(df)
    actions = get_actions(df)

    project = projects[
        projects["Project_Code"] == project_code
    ]

    if project.empty:
        return {}

    project = project.iloc[0]

    # All actions belonging to this project
    project_actions = actions[
        actions["Master_Code"] == project_code
    ].copy()

    completed = len(
        project_actions[
            project_actions["Status"].str.contains(
                "Completed",
                case=False,
                na=False
            )
        ]
    )

    # Employees working on this project
    employees_df = (
        project_actions
        .groupby("Employee")
        .size()
        .reset_index(name="TotalActions")
        .sort_values("TotalActions", ascending=False)
    )

    # Action list
    actions_df = project_actions[
        [
            "Project_Name",
            "Employee",
            "Status",
            "DeadLine",
            "AllocatedHours",
            "UsedHours",
            "Cost"
        ]
    ].copy()

    return {

        "Project_Name": project["Project_Name"],

        "Owner": project["Employee"],

        "Description": project["Project_Description"],

        "Responsible": project["Team_Res"],

        "Coordinator": project["Team_Coor"],

        "Support": project["Team_Support"],

        "Status": project["Status"],

        "Deadline": project["DeadLine"],

        "Cost": project["Cost"],

        "AllocatedHours": project["AllocatedHours"],

        "UsedHours": project["UsedHours"],

        "TotalActions": project_actions["Project_Code"].nunique(),

        "CompletedActions": completed,

        "PendingActions": len(project_actions) - completed,

        "Employees": employees_df.to_dict(orient="records"),

        "Actions": actions_df.to_dict(orient="records")

    }
# =====================================================
# 9. EMPLOYEE SUMMARY
# =====================================================

def employee_summary(df):

    actions = get_actions(df)

    projects = get_projects(df)

    employees = []

    for emp in sorted(df["Employee"].dropna().unique()):

        emp_projects = projects[
            projects["Employee"] == emp
        ]

        emp_actions = actions[
            actions["Employee"] == emp
        ]

        completed = len(
            emp_projects[
                emp_projects["Status"]
                .str.contains("Completed", case=False, na=False)
            ]
        )

        employees.append({

            "Employee": emp,

            "TotalProjects": len(emp_projects),

            "TotalActions": len(emp_actions),

            "CompletedProjects": completed,

            "RemainingProjects": len(emp_projects) - completed

        })

    return pd.DataFrame(employees)


# =====================================================
# 10. EMPLOYEE ACTION SUMMARY
# =====================================================

def employee_action_summary(df, project_code):

    actions = get_actions(df)

    actions = actions[
        actions["Master_Code"] == project_code
    ]

    result = (

        actions

        .groupby("Employee")

        .agg(

            TotalActions=("Project_Code", "count"),

            Completed=("Status",
                       lambda x:
                       x.astype(str)
                       .str.contains(
                           "Completed",
                           case=False,
                           na=False
                       ).sum())

        )

        .reset_index()

    )

    result["Pending"] = (

        result["TotalActions"] -

        result["Completed"]

    )

    return result


# =====================================================
# 11. ACTION SUMMARY
# =====================================================

def action_summary(df, project_code):

    actions = get_actions(df)

    actions = actions[
        actions["Master_Code"] == project_code
    ]

    return actions[[
        "Project_Name",
        "Employee",
        "Status",
        "DeadLine",
        "AllocatedHours",
        "UsedHours",
        "Cost"
    ]].copy()


# =====================================================
# 12. COMPLETE DASHBOARD
# =====================================================

def dashboard_data(df):

    important = get_important_projects(df)

    dashboard = {

        "summary":

            compute_kpis(df),

        "important_projects":

            important,

        "projects":

            project_summary(df).to_dict(
                orient="records"
            ),

        "employees":

            employee_summary(df).to_dict(
                orient="records"
            ),

        "urgent_project_details":

            project_details(
                df,
                important["urgent_project"]["Project_Code"]
            )

            if important["urgent_project"] else {},

        "high_cost_project_details":

            project_details(
                df,
                important["high_cost_project"]["Project_Code"]
            )

            if important["high_cost_project"] else {},

        "historical_project_details":

            project_details(
                df,
                important["historical_project"]["Project_Code"]
            )

            if important["historical_project"] else {}

    }

    return dashboard
