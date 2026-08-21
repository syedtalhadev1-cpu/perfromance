import os
import pyodbc
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
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


def load_employee_timeline(
    employee_id,
    company_code=None,
    days_back=90
):
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
        rows = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return rows

    except pyodbc.Error as db_err:
        print("Database error:", str(db_err))
        return []

    finally:
        if 'cursor' in locals():
            cursor.close()

        if 'conn' in locals():
            conn.close()


def test_past_3_months_trend(t, p):

    print("\n" + "=" * 60)
    print("PAST 3 MONTHS PROJECT STATUS TEST")
    print("=" * 60)

    if t.empty or p.empty:
        print("Timeline or Project data is EMPTY")
        return

    t = t.copy()
    p = p.copy()

    # Find columns
    timeline_date_col = next(
        (
            x for x in t.columns
            if str(x).strip().lower()
            in ("timelinedate", "timeline date", "date")
        ),
        None
    )

    timeline_project_col = next(
        (
            x for x in t.columns
            if str(x).strip().lower()
            in ("project_code", "project code", "projectcode")
        ),
        None
    )

    project_code_col = next(
        (
            x for x in p.columns
            if str(x).strip().lower()
            in ("project_code", "project code", "projectcode")
        ),
        None
    )

    status_col = next(
        (
            x for x in p.columns
            if str(x).strip().lower() == "status"
        ),
        None
    )

    print("\nDetected columns:")
    print("Timeline Date   :", timeline_date_col)
    print("Timeline Project:", timeline_project_col)
    print("Project Code    :", project_code_col)
    print("Status          :", status_col)

    if not all([
        timeline_date_col,
        timeline_project_col,
        project_code_col,
        status_col
    ]):
        print("\nERROR: Required columns are missing.")
        return

    # -----------------------------
    # Dates
    # -----------------------------

    t["TestDate"] = pd.to_datetime(
        t[timeline_date_col],
        errors="coerce"
    )

    t = t.dropna(subset=["TestDate"])

    print("\nTimeline date range:")
    print("Min:", t["TestDate"].min())
    print("Max:", t["TestDate"].max())

    # -----------------------------
    # Last 3 calendar months
    # -----------------------------

    today = pd.Timestamp.today().normalize()

    current_month = today.replace(day=1)

    start_month = current_month - pd.DateOffset(months=2)

    print("\nToday:", today)
    print("Start month:", start_month)
    print("Current month:", current_month)

    t = t[
        (t["TestDate"] >= start_month) &
        (t["TestDate"] <= today)
    ].copy()

    print("\nTimeline rows:", len(t))

    if t.empty:
        print("No data found.")
        return

    # -----------------------------
    # Project keys
    # -----------------------------

    t["ProjectKey"] = (
        t[timeline_project_col]
        .astype(str)
        .str.strip()
    )

    p["ProjectKey"] = (
        p[project_code_col]
        .astype(str)
        .str.strip()
    )

    # -----------------------------
    # Status cleaning
    # -----------------------------

    p["StatusClean"] = (
        p[status_col]
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
        .fillna(
            p["StatusClean"].str.title()
        )
    )

    # -----------------------------
    # Project status
    # -----------------------------

    project_status = (
        p[
            [
                "ProjectKey",
                "StatusClean"
            ]
        ]
        .drop_duplicates(
            subset=["ProjectKey"]
        )
    )

    # -----------------------------
    # Merge
    # -----------------------------

    df = t.merge(
        project_status,
        on="ProjectKey",
        how="left"
    )

    df["StatusClean"] = (
        df["StatusClean"]
        .fillna("Unknown")
    )

    # -----------------------------
    # Month
    # -----------------------------

    df["MonthDate"] = (
        df["TestDate"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    df["Month"] = (
        df["MonthDate"]
        .dt.strftime("%b %Y")
    )

    # -----------------------------
    # Count unique projects
    # -----------------------------

    monthly_status = (
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

    monthly_status = monthly_status.sort_values(
        ["MonthDate", "StatusClean"]
    )

    # -----------------------------
    # PRINT RESULT
    # -----------------------------

    print("\n" + "=" * 60)
    print("MONTHLY STATUS")
    print("=" * 60)

    print(
        monthly_status.to_string(
            index=False
        )
    )

    # -----------------------------
    # Months
    # -----------------------------

    available_months = pd.date_range(
        start=start_month,
        end=current_month,
        freq="MS"
    )

    month_labels = [
        month.strftime("%b %Y")
        for month in available_months
    ]

    # -----------------------------
    # Print Completed trend
    # -----------------------------

    print("\n" + "=" * 60)
    print("COMPLETED LINE VALUES")
    print("=" * 60)

    completed_values = []

    for month in available_months:

        temp = monthly_status[
            (monthly_status["MonthDate"] == month) &
            (monthly_status["StatusClean"] == "Completed")
        ]

        if temp.empty:
            count = 0
        else:
            count = int(
                temp["ProjectCount"].sum()
            )

        completed_values.append(count)

        print(
            f"{month.strftime('%b %Y')} "
            f"-> Completed: {count}"
        )

    # -----------------------------
    # Create chart
    # -----------------------------

    fig = go.Figure()

    statuses = [
        "Completed",
        "InProcess",
        "Delayed"
    ]

    # Add any additional statuses
    existing_statuses = (
        monthly_status["StatusClean"]
        .unique()
        .tolist()
    )

    for status in existing_statuses:

        if status not in statuses:
            statuses.append(status)

    # -----------------------------
    # Stacked bars
    # -----------------------------

    for status in statuses:

        values = []

        for month in available_months:

            temp = monthly_status[
                (monthly_status["MonthDate"] == month) &
                (monthly_status["StatusClean"] == status)
            ]

            if temp.empty:
                values.append(0)
            else:
                values.append(
                    int(temp["ProjectCount"].sum())
                )

        fig.add_trace(
            go.Bar(
                x=month_labels,
                y=values,
                name=status
            )
        )

    # -----------------------------
    # Completed trend line
    # -----------------------------

    fig.add_trace(
        go.Scatter(
            x=month_labels,
            y=completed_values,
            name="Completed Trend",
            mode="lines+markers",
            line=dict(
                width=3
            ),
            marker=dict(
                size=9
            )
        )
    )

    # -----------------------------
    # Layout
    # -----------------------------

    fig.update_layout(
        title="Project Status - Last 3 Months",

        barmode="stack",

        xaxis=dict(
            title="Month",
            categoryorder="array",
            categoryarray=month_labels
        ),

        yaxis=dict(
        title="",
        showticklabels=False,
        showgrid=False,
        zeroline=False
        ),

        legend=dict(
            orientation="h",
            y=1.12,
            x=0
        ),

        height=450,

        margin=dict(
            l=20,
            r=20,
            t=70,
            b=20
        ),

        hovermode="x unified",

        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": False
        }
    )
if __name__ == "__main__":

    employee_id = "5732"
    company_code = "DRC"

    rows = load_employee_timeline(
        employee_id=employee_id,
        company_code=company_code,
        days_back=121
    )

    print("\n" + "=" * 60)
    print("ROWS FROM STORED PROCEDURE")
    print("=" * 60)

    print("Total rows:", len(rows))

    if rows:

        df = pd.DataFrame(rows)

        print("\nColumns:")
        print(df.columns.tolist())

        print("\nFirst 10 rows:")
        print(df.head(10).to_string())

        print("\nTimeline dates:")
        print(
            pd.to_datetime(
                df["TimelineDate"],
                errors="coerce"
            ).describe()
        )

        # Your function needs t and p.
        # The SP gives us one combined dataframe,
        # so use the same dataframe for both.
        t = df.copy()
        p = df.copy()

        test_past_3_months_trend(t, p)

    else:
        print("NO DATA RETURNED FROM STORED PROCEDURE")