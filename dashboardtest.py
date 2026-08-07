from dashboard_model import *

rows = load_company_data(
    company_code="400",
    from_date="2025-01-01",
    to_date="2026-08-05"
)

print("Rows:", len(rows))

df = clean_rows(rows)

print("\n===== KPI =====")
print(compute_kpis(df))

print("\n===== Important Projects =====")
print(get_important_projects(df))

print("\n===== Employee Summary =====")
print(employee_summary(df).head())

print("\n===== Project Summary =====")
print(project_summary(df).head())

important = get_important_projects(df)

if important["high_cost_project"]:
    code = important["high_cost_project"]["Project_Code"]

    print("\n===== Project Details =====")
    print(project_details(df, code))