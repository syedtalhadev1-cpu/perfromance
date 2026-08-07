# dashboard_api.py
import os
import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import date

from dashboard_model import clean_rows, classify_cases, pick_top_important, compute_kpis, format_important_project

load_dotenv()

app = FastAPI(title="Company Dashboard")

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
    f"UID={os.getenv('DB_USERNAME')};PWD={os.getenv('DB_PASSWORD')};"
)


def fetch_raw_rows(company_code: str, from_date: date, to_date: date) -> list:
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "EXEC u.sp_ai_GetCompanyProjects @CompanyCode=?, @FromDate=?, @ToDate=?",
            company_code, from_date, to_date
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()
    return rows


@app.get("/dashboard/{company_code}")
def get_company_dashboard(company_code: str, from_date: date, to_date: date):
    raw_rows = fetch_raw_rows(company_code, from_date, to_date)
    if not raw_rows:
        raise HTTPException(status_code=404, detail="No data found for this company/date range")

    company_name = raw_rows[0].get("CompanyName", company_code)

    df = clean_rows(raw_rows)
    cases = classify_cases(df)
    kpis = compute_kpis(df)
    top_raw = pick_top_important(cases, top_n=3)
    top_projects = [format_important_project(p) for p in top_raw]

    # Overall status badge based on achievement %
    achievement = kpis["achievement_pct"]
    if achievement >= 70:
        status = {"label": "On track", "color": "green"}
    elif achievement >= 40:
        status = {"label": "At risk", "color": "amber"}
    else:
        status = {"label": "Needs attention", "color": "red"}

    return {
        "company_code": company_code,
        "company_name": company_name,
        "date_range": {"from": str(from_date), "to": str(to_date)},
        "employees": kpis["total_employees"],
        "total_projects": kpis["total_projects"],
        "achievement_pct": kpis["achievement_pct"],
        "status": status,
        "projects": top_projects,          # top 3, name-only
        "important_project": top_projects[0] if top_projects else None,
    }