import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import date
import pyodbc

load_dotenv()   # reads .env into environment variables

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVER   = os.getenv("DB_SERVER")
DATABASE = os.getenv("DB_DATABASE")
USERNAME = os.getenv("DB_USERNAME")
PASSWORD = os.getenv("DB_PASSWORD")

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};PWD={PASSWORD};"
)

def get_conn():
    return pyodbc.connect(CONN_STR)

# 1. Your Existing Endpoint for Company Projects
@app.get("/company/{company_code}/projects")
def get_company_projects(
    company_code: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
):
    conn = get_conn()
    cursor = conn.cursor()

    try:
        if from_date and to_date:
            cursor.execute(
                "EXEC u.sp_ai_GetCompanyProjects @CompanyCode=?, @FromDate=?, @ToDate=?",
                company_code, from_date, to_date
            )
        else:
            cursor.execute(
                "EXEC u.sp_ai_GetCompanyProjects @CompanyCode=?",
                company_code
            )

        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    finally:
        cursor.close()
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No projects found for this company/date range")

    return rows


# 2. NEW Endpoint: Get Employee Projects and Timeline details
@app.get("/employee/{employee_id}/timeline")
def get_employee_timeline(
    employee_id: str,
    company_code: Optional[str] = None,
    days_back: Optional[int] = 7,
):
    conn = get_conn()
    cursor = conn.cursor()

    try:
        # Executes the new stored procedure with parameters
        cursor.execute(
            "EXEC u.sp_ai_GetEmployeeProjectsAndTimeline @EmployeeId=?, @CompanyCode=?, @DaysBack=?",
            employee_id, company_code, days_back
        )

        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    finally:
        cursor.close()
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No projects or timeline records found for this employee")

    return rows