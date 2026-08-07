# dashboard_api.py

import os
import pyodbc
from datetime import date
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dashboard_model import *

load_dotenv()

app = FastAPI(title="Dashboard Model API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_DATABASE')};"
    f"UID={os.getenv('DB_USERNAME')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
)


def get_rows(company_code, from_date, to_date):

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
            to_date
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


@app.get("/dashboard/{company_code}")
def dashboard(
    company_code: str,
    from_date: date,
    to_date: date
):

    rows = get_rows(company_code, from_date, to_date)

    if not rows:
        raise HTTPException(404, "No data found")

    df = clean_rows(rows)

    return {

        "kpi": compute_kpis(df),

        "important_projects": get_important_projects(df),

        "project_summary": project_summary(df).to_dict("records"),

        "employee_summary": employee_summary(df).to_dict("records"),

        "dashboard": dashboard_data(df)

    }


@app.get("/project/{company_code}/{project_code}")
def project(
    company_code: str,
    project_code: str,
    from_date: date,
    to_date: date
):

    rows = get_rows(company_code, from_date, to_date)

    if not rows:
        raise HTTPException(404, "No data found")

    df = clean_rows(rows)

    return project_details(df, project_code)


@app.get("/actions/{company_code}/{project_code}")
def actions(
    company_code: str,
    project_code: str,
    from_date: date,
    to_date: date
):

    rows = get_rows(company_code, from_date, to_date)

    if not rows:
        raise HTTPException(404, "No data found")

    df = clean_rows(rows)

    return action_summary(df, project_code).to_dict("records")


@app.get("/employees/{company_code}")
def employees(
    company_code: str,
    from_date: date,
    to_date: date
):

    rows = get_rows(company_code, from_date, to_date)

    if not rows:
        raise HTTPException(404, "No data found")

    df = clean_rows(rows)

    return employee_summary(df).to_dict("records")