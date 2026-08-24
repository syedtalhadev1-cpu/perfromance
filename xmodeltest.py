import os
import pyodbc
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# DATABASE CONFIGURATION
# ============================================================

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


# ============================================================
# LOAD EMPLOYEE TIMELINE
# ============================================================

def load_employee_timeline(
    employee_id,
    company_code=None,
    days_back=5
):
    conn = None
    cursor = None

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
            days_back
        )

        if cursor.description is None:
            return []

        columns = [
            column[0]
            for column in cursor.description
        ]

        rows = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return rows

    except pyodbc.Error as db_error:

        st.error(
            f"Database error: {db_error}"
        )

        return []

    except Exception as error:

        st.error(
            f"Unexpected error: {error}"
        )

        return []

    finally:

        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()


# ============================================================
# STREAMLIT PAGE
# ============================================================

st.set_page_config(
    page_title="Employee Timeline Test",
    page_icon="🧪",
    layout="wide"
)


st.title(
    "🧪 Employee Timeline - Historical Date Test"
)

st.write(
    "This test checks the employee timeline returned by "
    "the stored procedure."
)


# ============================================================
# INPUTS
# ============================================================

col1, col2 = st.columns(2)

with col1:

    employee_id = st.text_input(
        "Employee ID",
        value="5732"
    )


with col2:

    company_code = st.text_input(
        "Company Code",
        value="DRC"
    )


st.markdown("---")


# ============================================================
# IMPORTANT
# ============================================================

st.info(
    """
    The stored procedure calculates @DaysBack from the current
    SQL Server date.

    Therefore this test first requests a large enough range
    to discover the actual TimelineDate values.

    After that, we manually check the 5-day period around
    July 3, 2026.
    """
)


# ============================================================
# LOAD BUTTON
# ============================================================

if st.button(
    "🔍 Check Employee Timeline",
    type="primary"
):

    if not employee_id.strip():

        st.warning(
            "Please enter an Employee ID."
        )

        st.stop()


    # --------------------------------------------------------
    # Request enough historical data
    # --------------------------------------------------------

    days_back_from_sql = 121

    with st.spinner(
        "Loading timeline from SQL Server..."
    ):

        rows = load_employee_timeline(
            employee_id=employee_id,
            company_code=company_code,
            days_back=days_back_from_sql
        )


    st.markdown("---")


    # ========================================================
    # BASIC RESULT
    # ========================================================

    st.subheader(
        "1. Stored Procedure Result"
    )

    result_col1, result_col2, result_col3 = st.columns(3)

    with result_col1:

        st.metric(
            "Employee ID",
            employee_id
        )

    with result_col2:

        st.metric(
            "Company",
            company_code
        )

    with result_col3:

        st.metric(
            "Rows Returned",
            len(rows)
        )


    if not rows:

        st.error(
            "NO DATA RETURNED FROM STORED PROCEDURE."
        )

        st.stop()


    df = pd.DataFrame(rows)


    st.success(
        f"Successfully received {len(df)} rows."
    )


    # ========================================================
    # COLUMNS
    # ========================================================

    st.subheader(
        "2. Columns Returned"
    )

    st.write(
        df.columns.tolist()
    )


    # ========================================================
    # CHECK TIMELINE DATE
    # ========================================================

    st.subheader(
        "3. Actual Timeline Date Range"
    )


    if "TimelineDate" not in df.columns:

        st.error(
            "TimelineDate column was NOT returned by the stored procedure."
        )

        st.stop()


    df["TimelineDate"] = pd.to_datetime(
        df["TimelineDate"],
        errors="coerce"
    )


    valid_dates = (
        df["TimelineDate"]
        .dropna()
    )


    null_date_count = (
        df["TimelineDate"]
        .isna()
        .sum()
    )


    if valid_dates.empty:

        st.error(
            "TimelineDate exists, but ALL TimelineDate values are NULL."
        )

        st.write(
            df.head(20)
        )

        st.stop()


    min_date = valid_dates.min()
    max_date = valid_dates.max()


    date_col1, date_col2, date_col3 = st.columns(3)


    with date_col1:

        st.metric(
            "Minimum Timeline Date",
            min_date.strftime("%Y-%m-%d")
        )


    with date_col2:

        st.metric(
            "Maximum Timeline Date",
            max_date.strftime("%Y-%m-%d")
        )


    with date_col3:

        st.metric(
            "NULL Timeline Dates",
            int(null_date_count)
        )


    # ========================================================
    # ALL AVAILABLE DATES
    # ========================================================

    st.subheader(
        "4. All Timeline Dates Returned"
    )


    date_summary = (
        df.dropna(
            subset=["TimelineDate"]
        )
        .assign(
            Date=lambda x:
                x["TimelineDate"].dt.strftime("%Y-%m-%d")
        )
        .groupby("Date")
        .size()
        .reset_index(
            name="Rows"
        )
        .sort_values(
            "Date",
            ascending=False
        )
    )


    st.dataframe(
        date_summary,
        use_container_width=True,
        hide_index=True
    )


    # ========================================================
    # HISTORICAL TEST DATE
    # ========================================================

    st.markdown("---")

    st.subheader(
        "5. Test Last 5 Days From July 3, 2026"
    )


    reference_date = pd.Timestamp(
        "2026-07-03"
    )


    test_start_date = (
        reference_date
        - pd.Timedelta(days=4)
    )


    test_end_date = reference_date


    st.info(
        f"""
        Reference Date: **{reference_date.strftime("%Y-%m-%d")}**

        5-day timeline:

        **{test_start_date.strftime("%Y-%m-%d")}**
        →
        **{test_end_date.strftime("%Y-%m-%d")}**
        """
    )


    # ========================================================
    # FILTER EXACT 5 DAYS
    # ========================================================

    five_day_df = df[
        (df["TimelineDate"] >= test_start_date)
        &
        (df["TimelineDate"] <= test_end_date)
    ].copy()


    # ========================================================
    # 5-DAY SUMMARY
    # ========================================================

    st.subheader(
        "6. Five-Day Timeline Summary"
    )


    summary_dates = pd.date_range(
        start=test_start_date,
        end=test_end_date,
        freq="D"
    )


    summary_rows = []


    for current_date in summary_dates:

        day_df = five_day_df[
            five_day_df["TimelineDate"].dt.normalize()
            == current_date
        ]


        summary_rows.append(
            {
                "Date":
                    current_date.strftime("%Y-%m-%d"),

                "Rows":
                    len(day_df),

                "Projects":
                    (
                        day_df["Project_Code"]
                        .nunique()
                        if "Project_Code" in day_df.columns
                        else 0
                    ),

                "WorkAchieved":
                    (
                        day_df["WorkAchieved"]
                        .notna()
                        .sum()
                        if "WorkAchieved" in day_df.columns
                        else 0
                    )
            }
        )


    five_day_summary = pd.DataFrame(
        summary_rows
    )


    st.dataframe(
        five_day_summary,
        use_container_width=True,
        hide_index=True
    )


    # ========================================================
    # TOTAL 5-DAY ROWS
    # ========================================================

    st.metric(
        "Total Rows in July 3 Five-Day Window",
        len(five_day_df)
    )


    # ========================================================
    # ACTUAL FIVE-DAY RECORDS
    # ========================================================

    st.subheader(
        "7. Actual Records From June 29 - July 3"
    )


    if five_day_df.empty:

        st.error(
            """
            ❌ NO RECORDS FOUND IN THIS FIVE-DAY PERIOD.

            This means the stored procedure result does not
            contain TimelineDate values between June 29 and
            July 3, 2026 for this employee/company.
            """
        )

    else:

        st.success(
            f"Found {len(five_day_df)} records."
        )


        display_df = five_day_df.copy()


        display_df["TimelineDate"] = (
            display_df["TimelineDate"]
            .dt.strftime("%Y-%m-%d")
        )


        preferred_columns = [
            "TimelineDate",
            "StartTime",
            "EndTime",
            "TimeCount",
            "WorkAchieved",
            "Status",
            "Project_Code",
            "Project_Name",
            "Master_Code",
            "Emp_No",
            "Emp_Comp_No",
            "EmployeeName",
            "CompanyName"
        ]


        available_columns = [
            column
            for column in preferred_columns
            if column in display_df.columns
        ]


        if available_columns:

            st.dataframe(
                display_df[
                    available_columns
                ],
                use_container_width=True,
                hide_index=True
            )

        else:

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )


    # ========================================================
    # EMPLOYEE CHECK
    # ========================================================

    st.subheader(
        "8. Employee Validation"
    )


    employee_columns = [
        column
        for column in [
            "Emp_No",
            "Emp_Comp_No",
            "EmployeeName",
            "CompanyName"
        ]
        if column in five_day_df.columns
    ]


    if employee_columns and not five_day_df.empty:

        st.dataframe(
            five_day_df[
                employee_columns
            ].drop_duplicates(),
            use_container_width=True,
            hide_index=True
        )


    # ========================================================
    # PROJECT CHECK
    # ========================================================

    if not five_day_df.empty and "Project_Code" in five_day_df.columns:

        st.subheader(
            "9. Projects Found In Five-Day Timeline"
        )


        project_columns = [
            column
            for column in [
                "Project_Code",
                "Project_Name",
                "Status",
                "TimelineDate",
                "WorkAchieved",
                "TimeCount"
            ]
            if column in five_day_df.columns
        ]


        project_df = (
            five_day_df[
                project_columns
            ]
            .copy()
        )


        if "TimelineDate" in project_df.columns:

            project_df["TimelineDate"] = (
                project_df["TimelineDate"]
                .dt.strftime("%Y-%m-%d")
            )


        st.dataframe(
            project_df,
            use_container_width=True,
            hide_index=True
        )


    # ========================================================
    # RAW DATA
    # ========================================================

    with st.expander(
        "🔎 View All Raw Stored Procedure Data"
    ):

        raw_df = df.copy()

        if "TimelineDate" in raw_df.columns:

            raw_df["TimelineDate"] = (
                raw_df["TimelineDate"]
                .dt.strftime("%Y-%m-%d")
            )


        st.dataframe(
            raw_df,
            use_container_width=True,
            hide_index=True
        )