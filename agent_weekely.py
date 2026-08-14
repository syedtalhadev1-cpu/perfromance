"""
agent_weekly.py
----------------
Pulls the weekly project-status summary (Completed / InProcess / Delay) via
u.sp_ai_GetWeeklyProjectStatusSummary and returns it as clean, split DataFrames
ready for reporting (tables, charts, docgen).

Deliberately takes `company_code` as a plain function argument rather than
reading it from st.session_state or a Streamlit widget directly - today it
comes from the sidebar selectbox in the dashboard app, but if/when company
selection moves to being derived from the logged-in user, only the caller
changes. This module stays untouched either way.
"""

import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv

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
# 1. LOAD RAW DATA FROM STORED PROCEDURE
# =====================================================

def load_weekly_status_summary(company_code=None, days_back=7):
    """
    Calls u.sp_ai_GetWeeklyProjectStatusSummary and returns raw rows.

    company_code: pass None to include all companies (matches the SP's
                  own "pass NULL to ignore filtering" behavior).
    days_back:    size of the "Completed" window, in days. Does not affect
                  the Open/InProcess/Delay section, which is always a live
                  snapshot as of today.
    """
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        cursor.execute(
            """
            EXEC u.sp_ai_GetWeeklyProjectStatusSummary
                @CompanyCode=?,
                @DaysBack=?
            """,
            company_code,
            days_back,
        )

        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return rows

    except pyodbc.Error as db_err:
        print(f"Database error loading weekly status summary: {str(db_err)}")
        return []
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


# =====================================================
# 2. CLEAN + SPLIT INTO THE 3 REPORT TABLES
# =====================================================

def clean_weekly_rows(rows):
    """Basic cleanup: DataFrame conversion, blank-safe text, numeric TotalCount."""
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    text_cols = ["Section", "Manager", "Responsible", "Status", "RowType",
                 "ItemCode", "ItemName", "ParentProjectName"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    if "TotalCount" in df.columns:
        df["TotalCount"] = pd.to_numeric(df["TotalCount"], errors="coerce").fillna(0).astype(int)

    if "TmId" in df.columns:
        df["TmId"] = df["TmId"].astype(str).str.strip()

    if "CompletedOn" in df.columns:
        df["CompletedOn"] = pd.to_datetime(df["CompletedOn"], errors="coerce")

    return df


def summarize_by_employee(df):
    """
    Collapses the item-level rows back to one row per Manager+Employee+Status,
    for a compact count-only view (matches the original report format).
    `TotalCount` is already correct per group (window function in the SP),
    so this is a de-dupe, not a re-aggregation - do NOT sum TotalCount here.
    """
    if df.empty:
        return pd.DataFrame(columns=["Section", "Manager", "TmId", "Responsible", "Status", "TotalCount"])

    return (
        df.drop_duplicates(subset=["Manager", "TmId", "Responsible", "Status"])
        [["Section", "Manager", "TmId", "Responsible", "Status", "TotalCount"]]
        .sort_values(["Manager", "Responsible"])
        .reset_index(drop=True)
    )


def split_weekly_tables(df):
    """
    Splits the combined SP output into the 3 report tables. Each returned
    DataFrame is now ITEM-LEVEL (one row per project/action, per the current
    SP), not employee-level - includes RowType/ItemName/ParentProjectName
    for drill-down. Use summarize_by_employee() on any of these for the
    compact count-only view.
      - completed_df:  Section == 'Completed'
      - delay_df:      Status  == 'Delay'      (subset of Section == 'Open')
      - inprocess_df:  Section == 'Open' and Status != 'Delay'
                        (includes InProcess, Project Hold, Cancelled,
                        Under Approval, etc. - whatever Project_Master has)
    """
    empty_cols = ["Section", "Manager", "TmId", "Responsible", "Status", "RowType",
                  "ItemCode", "ItemName", "ParentProjectName", "CompletedOn", "TotalCount"]

    if df.empty:
        empty = pd.DataFrame(columns=empty_cols)
        return empty.copy(), empty.copy(), empty.copy()

    completed_df = df[df["Section"] == "Completed"].copy()
    delay_df = df[df["Status"] == "Delay"].copy()
    inprocess_df = df[(df["Section"] == "Open") & (df["Status"] != "Delay")].copy()

    return completed_df, delay_df, inprocess_df


def load_last_completed_fallback(company_code=None):
    """
    Used only when the 7-day Completed window comes back empty. Finds the
    most recent completion date (and item) for this company, with no date
    filter, so the report can show "Last completed: [date] - [item]"  youinstead
    of a dead-looking empty table.
    """
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT TOP 1
                PM.Project_Code   AS ItemCode,
                PM.Project_Name   AS ItemName,
                ISNULL(PM.CD, PM.LastUpdate) AS CompletedOn
            FROM Project_Master PM
            WHERE PM.Status = 'Completed'
              AND (? IS NULL OR PM.Emp_Comp_No = ?)
            ORDER BY ISNULL(PM.CD, PM.LastUpdate) DESC
            """,
            company_code, company_code,
        )

        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "ItemCode": row[0],
            "ItemName": row[1],
            "CompletedOn": row[2],
        }

    except pyodbc.Error as db_err:
        print(f"Database error loading last-completed fallback: {str(db_err)}")
        return None
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


# =====================================================
# 3. TOP-LEVEL ENTRY POINT
# =====================================================

def get_weekly_status_report(company_code=None, days_back=7):
    """
    Single call the Streamlit sidebar (or a scheduler job) can use:

        completed_df, delay_df, inprocess_df, totals = get_weekly_status_report(
            company_code=company, days_back=7
        )

    `company` here is whatever the caller already resolved - sidebar
    selectbox today, logged-in-user's company later.
    """
    raw_rows = load_weekly_status_summary(company_code=company_code, days_back=days_back)
    df = clean_weekly_rows(raw_rows)
    completed_df, delay_df, inprocess_df = split_weekly_tables(df)

    # IMPORTANT: rows are now item-level (one row per project/action), and
    # TotalCount repeats the same group-count on every row of that group
    # (window function in the SP) - so summing TotalCount here would massively
    # over-count. The correct total item count is just len(df) at this grain.
    totals = {
        "completed_total": len(completed_df),
        "delay_total": len(delay_df),
        "inprocess_total": len(inprocess_df),
        "company_code": company_code,
        "days_back": days_back,
    }

    # Quiet-week handling: a strict N-day window can legitimately show zero
    # completions given bursty completion logging. Rather than showing a
    # dead empty table, surface the most recent real completion as context.
    last_completed_fallback = None
    if completed_df.empty:
        last_completed_fallback = load_last_completed_fallback(company_code=company_code)
        totals["last_completed_fallback"] = last_completed_fallback
    else:
        totals["last_completed_fallback"] = None

    return completed_df, delay_df, inprocess_df, totals


if __name__ == "__main__":
    # Quick manual test: python agent_weekly.py
    c_df, d_df, i_df, t = get_weekly_status_report(company_code="400", days_back=14)
    print("Completed:\n", c_df)
    print("\nDelay:\n", d_df)
    print("\nInProcess/Open:\n", i_df)
    print("\nTotals:\n", t)