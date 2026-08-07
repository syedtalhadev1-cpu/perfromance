import pandas as pd
from Emodel import (
    load_employee_timeline,
    load_important_project_data,
    clean_timeline_rows,
    get_projects,
    get_actions,
    get_employee_timeline_dashboard,
    get_employee_project_details,
    get_important_projects
)

print("="*60)
print("🎯 STREAMLINED EMPLOYEE TERMINAL TEST FOR Emodel.py")
print("="*60)

TEST_EMPLOYEE = input("👉 Enter Employee ID (e.g., 400203): ").strip()
TEST_COMPANY = input("👉 Enter Company Code (e.g., 400): ").strip()
days_input = input("👉 Enter Days Back for Timeline (press Enter for default 14): ").strip()

DAYS_BACK = int(days_input) if days_input else 14

print("\n" + "="*50)
print(f"🚀 Running Single-Employee Tests for: {TEST_EMPLOYEE}")
print("="*50)

# =====================================================
# 1. TEST EMPLOYEE TIMELINE & SINGLE-EMPLOYEE KPIs
# =====================================================
print("\n[STEP 1] Fetching Personal Employee Timeline, KPIs, & Important Projects...")
timeline_results = get_employee_timeline_dashboard(
    employee_id=TEST_EMPLOYEE,
    company_code=TEST_COMPANY,
    days_back=DAYS_BACK
)

if timeline_results["timeline_records"]:
    print(f"   ✅ Success! Found {len(timeline_results['timeline_records'])} daily actions.")
    
    # Verify personal metrics
    emp_kpis = timeline_results["summary"]
    print(f"\n📈 Personal KPIs for Employee {TEST_EMPLOYEE}:")
    print(f"   - Total Projects Assigned: {emp_kpis['total_projects']}")
    print(f"   - Total Actions Assigned: {emp_kpis['total_actions']}")
    print(f"   - Completed Projects: {emp_kpis['completed_projects']}")
    print(f"   - Completion Rate: {emp_kpis['achievement_pct']}%")

    # Print timeline records
    print("\n📅 Sample Timeline Achievements:")
    timeline_df = pd.DataFrame(timeline_results["timeline_records"])
    display_cols = ["DailyWorkDate", "StartTime", "EndTime", "WorkAchieved", "Project_Name"]
    print(timeline_df[display_cols].head(5))
else:
    print(f"   ❓ No daily timeline logs found for Employee {TEST_EMPLOYEE} in the last {DAYS_BACK} days.")


# =====================================================
# 2. TEST HISTORICAL LOOKBACK FOR OLD ACTIVE PROJECTS
# =====================================================
print("\n[STEP 2] Testing Historical Active Project Lookback...")
raw_important_rows = load_important_project_data(employee_id=TEST_EMPLOYEE, company_code=TEST_COMPANY)
df_important = clean_timeline_rows(raw_important_rows)
print(f"   ✅ Loaded {len(raw_important_rows)} long-term historical rows.")

# Calculate Single Employee Important Projects
personal_important = get_important_projects(df_important)
print(f"\n📊 Personal Important Projects (Historical Lookback):")
print(f"   - Urgent: {personal_important['urgent_project']['Project_Name'] if personal_important['urgent_project'] else 'None'}")
print(f"   - High Cost: {personal_important['high_cost_project']['Project_Name'] if personal_important['high_cost_project'] else 'None'}")
print(f"   - Historical: {personal_important['historical_project']['Project_Name'] if personal_important['historical_project'] else 'None'}")


# =====================================================
# 3. TEST DRILL-DOWN PROJECT DETAILS
# =====================================================
print("\n[STEP 3] Testing Drill-Down Project Details...")
if timeline_results["timeline_records"]:
    # Grab the first project code found in their timeline to test the drill-down
    sample_project_code = timeline_results["timeline_records"][0]["Project_Code"]
    print(f"   Testing drill-down detail for Project Code: {sample_project_code}")

    # Test get_employee_project_details using the cleaned timeline DataFrame
    drill_down_details = get_employee_project_details(df_important, sample_project_code, TEST_EMPLOYEE)

    if drill_down_details:
        print(f"\n✅ Drill-Down Succeeded:")
        print(f"   - Project Name: {drill_down_details['Project_Name']}")
        print(f"   - Current Status: {drill_down_details['Status']}")
        print(f"   - Actions Logged by Employee: {drill_down_details['Total_Actions_Logged']}")
        
        if drill_down_details["Actions"]:
            print("\n   Detailed Actions:")
            actions_df = pd.DataFrame(drill_down_details["Actions"])
            print(actions_df[["DailyWorkDate", "WorkAchieved", "Status"]].head(3))
    else:
        print("   ❌ Drill-down details returned empty.")
else:
    print("   ❓ Skipping drill-down test: No active timeline logs found to test with.")

print("\n🚀 Test Execution Complete.")