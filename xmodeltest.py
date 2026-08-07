from dashboard_model import *

# ---------------------------------------
# Load Data
# ---------------------------------------

rows = load_company_data(
    company_code="400",
    from_date="2026-01-01",
    to_date="2026-05-31"
)

print("\n==============================")
print("RAW ROWS")
print("==============================")
print("Total Rows :", len(rows))

# ---------------------------------------
# Clean
# ---------------------------------------

df = clean_rows(rows)

print("\n==============================")
print("DATAFRAME")
print("==============================")
print(df.head())

# ---------------------------------------
# KPI
# ---------------------------------------

print("\n==============================")
print("KPI")
print("==============================")

kpi = compute_kpis(df)

for k, v in kpi.items():
    print(f"{k:25}: {v}")

# ---------------------------------------
# Important Projects
# ---------------------------------------

print("\n==============================")
print("IMPORTANT PROJECTS")
print("==============================")

important = get_important_projects(df)

print("\nUrgent Project")
print(important["urgent_project"])

print("\nHigh Cost Project")
print(important["high_cost_project"])

print("\nHistorical Project")
print(important["historical_project"])

# ---------------------------------------
# Project Summary
# ---------------------------------------

print("\n==============================")
print("PROJECT SUMMARY")
print("==============================")

summary = project_summary(df)

print(summary.head(10))

# ---------------------------------------
# Project Details
# ---------------------------------------

if important["urgent_project"]:

    project_code = important["urgent_project"]["Project_Code"]

    print("\n==============================")
    print("PROJECT DETAILS")
    print("==============================")

    details = project_details(df, project_code)

    for k, v in details.items():
        print(f"{k:25}: {v}")

    print("\n==============================")
    print("EMPLOYEE ACTION SUMMARY")
    print("==============================")

    print(employee_action_summary(df, project_code))

    print("\n==============================")
    print("ACTION SUMMARY")
    print("==============================")

    print(action_summary(df, project_code))

# ---------------------------------------
# Employee Summary
# ---------------------------------------

print("\n==============================")
print("EMPLOYEE SUMMARY")
print("==============================")

employees = employee_summary(df)

print(employees.head(20))

# ---------------------------------------
# Dashboard Data
# ---------------------------------------

print("\n==============================")
print("FULL DASHBOARD")
print("==============================")

dashboard = dashboard_data(df)

print(dashboard.keys())

print("\nDashboard Summary")
print(dashboard["summary"])

print("\nImportant Projects")
print(dashboard["important_projects"])