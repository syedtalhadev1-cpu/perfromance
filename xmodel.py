# dashboard_model.py
# Pure data processing. No DB code, no FastAPI code here.

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def clean_rows(rows: list) -> pd.DataFrame:
    """Takes raw SP output (list of dicts) and returns a cleaned DataFrame."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    numeric_cols = ['Cost', 'AllocatedHours', 'UsedHours']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0

    for col in ['DeadLine', 'CreatedDate']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    if 'ProjectType' not in df.columns:
        df['ProjectType'] = 'Core tasks'
    if 'TaskType' not in df.columns:
        df['TaskType'] = 'Project'

    return df


def classify_cases(df: pd.DataFrame) -> dict:
    """Same rule logic as model.py: Case 1 (urgent), Case 2 (high cost/delay), Case 3 (historical)."""
    today = datetime.today().date()

    if df.empty:
        return {"case1": pd.DataFrame(), "case2": pd.DataFrame(), "case3": pd.DataFrame()}

    mask = (df['ProjectType'].astype(str).str.lower() == 'core tasks') & \
           (df['TaskType'].astype(str).str.lower() == 'project')
    base_df = df[mask].copy()

    # CASE 1: Urgent — deadline within next 7 days, not completed
    win_start = today + timedelta(days=1)
    win_end = today + timedelta(days=7)
    case1 = base_df[
        (base_df['DeadLine'] >= win_start) & (base_df['DeadLine'] <= win_end) &
        (~base_df['Status'].astype(str).str.contains('Completed', case=False, na=False))
    ].sort_values(by='DeadLine', ascending=True).reset_index(drop=True)

    # CASE 2: High cost, delayed or stalled
    base_df['UsagePercent'] = (base_df['UsedHours'] / base_df['AllocatedHours'].replace(0, np.nan)) * 100
    base_df['UsagePercent'] = base_df['UsagePercent'].replace([np.inf, -np.inf], np.nan).fillna(0).round(1)
    cost_threshold = base_df['Cost'].quantile(0.75) if not base_df.empty else 0
    m_high_cost = base_df['Cost'] >= cost_threshold
    m_delay = base_df['Status'].astype(str).str.lower() == 'delay'
    m_inproc = (base_df['Status'].astype(str).str.lower() == 'inprocess') & (base_df['UsagePercent'] <= 55)
    case2 = base_df[m_high_cost & (m_delay | m_inproc)].sort_values(
        by=['Status', 'Cost'], ascending=[True, False]
    ).reset_index(drop=True)

    # CASE 3: Historical — created same month last year, still open
    last_year, this_month = today.year - 1, today.month
    case3 = base_df[
        (base_df['CreatedDate'].apply(lambda x: x.year if hasattr(x, 'year') else 0) == last_year) &
        (base_df['CreatedDate'].apply(lambda x: x.month if hasattr(x, 'month') else 0) == this_month) &
        (~base_df['Status'].astype(str).str.contains('Completed', case=False, na=False))
    ].sort_values(by='CreatedDate', ascending=True).reset_index(drop=True)

    return {"case1": case1, "case2": case2, "case3": case3}


def pick_top_important(cases: dict, top_n: int = 3) -> list:
    """
    Picks the top N important projects across cases, priority order:
    Case 1 (urgent) first, then Case 2 (high cost/delay), then Case 3 (historical).
    """
    combined = []
    for case_key, reason in [
        ("case1", "Deadline within next 7 days"),
        ("case2", "High cost project delayed or under-progressing"),
        ("case3", "Unresolved project from same month last year"),
    ]:
        df = cases[case_key]
        for _, row in df.iterrows():
            item = row.to_dict()
            item["reason"] = reason
            combined.append(item)
            if len(combined) >= top_n:
                return combined[:top_n]
    return combined[:top_n]


def compute_kpis(df: pd.DataFrame) -> dict:
    """Total projects, total employees, achievement %."""
    if df.empty:
        return {"total_projects": 0, "total_employees": 0, "achievement_pct": 0}

    total_projects = df['Project_Code'].nunique() if 'Project_Code' in df.columns else len(df)
    total_employees = df['Employee'].nunique() if 'Employee' in df.columns else 0

    total_used = df['UsedHours'].sum() if 'UsedHours' in df.columns else 0
    total_allocated = df['AllocatedHours'].sum() if 'AllocatedHours' in df.columns else 0
    achievement_pct = round((total_used / total_allocated) * 100, 1) if total_allocated else 0

    return {
        "total_projects": int(total_projects),
        "total_employees": int(total_employees),
        "achievement_pct": achievement_pct,
    }
# add this to Cmodel.py

def format_important_project(item: dict) -> dict:
    """Strip internal IDs, keep only display-friendly fields."""
    return {
        "project_name": item.get("Project_Name"),
        "description": item.get("Project_Description"),
        "owner": item.get("Employee"),          # name only, no EmployeeId
        "status": item.get("Status"),
        "deadline": item.get("DeadLine"),
        "created": item.get("CreatedDate"),
        "allocated_hours": item.get("AllocatedHours"),
        "used_hours": item.get("UsedHours"),
        "progress_pct": round((item.get("UsedHours", 0) / item["AllocatedHours"]) * 100, 1)
                         if item.get("AllocatedHours") else 0,
        "cost": item.get("Cost"),
        "reason": item.get("reason"),
    }


def to_json_safe(records: list) -> list:
    """Converts date objects to strings, NaN to None, so FastAPI can serialize cleanly."""
    out = []
    for r in records:
        clean = {}
        for k, v in r.items():
            if hasattr(v, 'strftime'):
                clean[k] = v.strftime('%d-%m-%Y')
            elif pd.isna(v) if not isinstance(v, (list, dict)) else False:
                clean[k] = None
            else:
                clean[k] = v
        out.append(clean)
    return out