import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv
from pmodel import ProjectDataProcessor

# Load environment configuration
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

def fetch_project_dashboard_rows(company_code, employee_id=None, from_date=None, to_date=None):
    conn = None
    cursor = None
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute(
            """
            EXEC u.sp_ai_DashboardProjectAI
                @CompanyCode=?,
                @EmployeeId=?,
                @FromDate=?,
                @ToDate=?
            """,
            company_code,
            employee_id if employee_id else None,
            from_date if from_date else None,
            to_date if to_date else None
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except pyodbc.Error as db_err:
        print(f"❌ Database execution error: {str(db_err)}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# Start Test Setup
print("=" * 60)
print("🎯 HIERARCHICAL THREE-TIER DASHBOARD TEST")
print("=" * 60)

TEST_COMPANY = input("👉 Enter Company Code (e.g., 400): ").strip()
TEST_EMPLOYEE = input("👉 Enter Employee ID (Optional - Press Enter to skip): ").strip()

employee_param = TEST_EMPLOYEE if TEST_EMPLOYEE else None

print("\n🚀 Executing lookup and model processing...")
raw_rows = fetch_project_dashboard_rows(company_code=TEST_COMPANY, employee_id=employee_param)

if not raw_rows:
    print("❌ No data returned.")
    exit()

processor = ProjectDataProcessor(raw_rows)
tree = processor.get_project_timeline_tree()

print("\n" + "="*50)
print("🔎 PROJECT TIMELINE HIERARCHY")
print("="*50)

# Traverse projects and display nested actions and achievements
for i, parent in enumerate(tree):
    # Only show parent nodes that have sub-actions to verify the hierarchy
    if parent["Sub_Actions"]:
        print(f"\n📂 [PARENT PROJECT #{i+1}] {parent['Parent_Project_Name']} (Code: {parent['Parent_Project_Code']})")
        print(f"   - Owner: {parent['Employee']} ({parent['EmployeeId']})")
        print(f"   - Status: {parent['Status']} | Total Project Used Hours: {parent['TotalProjectUsedHours']} hrs")
        print(f"   - Total Actions Found: {len(parent['Sub_Actions'])}")
        
        for j, action in enumerate(parent["Sub_Actions"]):
            print(f"     ├── 🔨 [ACTION NAME #{j+1}] {action['Action_Name']} (Code: {action['Action_Code']})")
            print(f"     │   - Action Allocated Hours: {action['AllocatedHours']} | Used: {action['ActionUsedHours']} hrs")
            print(f"     │   - Action Status: {action['Status']}")
            print(f"     │   - Timeline logs ({len(action['Timeline_Logs'])} entries):")
            
            for k, log in enumerate(action["Timeline_Logs"]):
                print(f"     │       📅 Entry {k+1} ({log['TimelineDate']} @ {log['StartTime']} - {log['EndTime']} | spent {log['DailyTimeSpent']} hrs):")
                print(f"     │          📝 Work Achieved: {log['WorkAchieved'][:140]}...")
    else:
        # Parent projects that do not have sub-actions listed under them yet
        print(f"\n📂 [PARENT PROJECT #{i+1}] {parent['Parent_Project_Name']} (Code: {parent['Parent_Project_Code']})")
        print(f"   - Status: {parent['Status']}")
        print(f"   - (No nested child action milestones found for this item.)")

print("\n🚀 Terminal Hierarchy Render Completed.")