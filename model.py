import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def load_and_clean_data(file_path="StreamData_AI.xlsx"):
    df_raw = pd.read_excel(file_path, header=None)
    header_row = 0
    for idx, row in df_raw.head(20).iterrows():
        vals = [str(v).lower().strip() for v in row if pd.notna(v)]
        if any(col in vals for col in ['employee', 'status', 'projectname']):
            header_row = idx
            break
    
    df = pd.read_excel(file_path, header=header_row)
    df.columns = df.columns.astype(str).str.strip()

    column_mapping = {}
    seen_targets = set()
    for col in df.columns:
        c_low = col.lower().replace(" ", "").replace("_", "")
        target = None
        if c_low in ['projectname', 'project']: target = 'Project_Name'
        elif c_low in ['deadline', 'expiry']: target = 'DeadLine'
        elif c_low in ['createddate', 'createddat', 'startdate']: target = 'CreatedDat'
        elif c_low == 'projecttype': target = 'ProjectType'
        elif c_low == 'tasktype': target = 'TaskType'
        elif c_low == 'allocatedhours': target = 'AllocatedHours'
        elif c_low == 'usedhours': target = 'UsedHours'
        elif c_low in ['companyname', 'client', 'customer', 'company']: target = 'CompanyName'
        elif c_low == 'cost': target = 'Cost'
        elif c_low == 'employee': target = 'Employee'
        elif c_low == 'status': target = 'Status'
        if target and target not in seen_targets:
            column_mapping[col] = target
            seen_targets.add(target)

    df = df.rename(columns=column_mapping)
    df = df.loc[:, ~df.columns.duplicated()]

    numeric_cols = ['Cost', 'AllocatedHours', 'UsedHours']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            df[col] = 0.0
    df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0)

    if 'CreatedDat' in df.columns:
        df['CreatedDat'] = pd.to_datetime(df['CreatedDat'], dayfirst=True, errors='coerce').dt.date
    if 'DeadLine' in df.columns:
        df['DeadLine'] = pd.to_datetime(df['DeadLine'], dayfirst=True, errors='coerce').dt.date
    
    return df

def get_dashboard_data(file_path="StreamData_AI.xlsx"):
    df = load_and_clean_data(file_path)
    today = datetime.today().date()
    
    # Global Filter
    mask = (df['ProjectType'].astype(str).str.lower() == 'core tasks') & \
           (df['TaskType'].astype(str).str.lower() == 'project')
    base_df = df[mask].copy()

    # --- CASE 1: Urgent ---
    win_start = today + timedelta(days=1)
    win_end = today + timedelta(days=7)
    case1 = base_df[
        (base_df['DeadLine'] >= win_start) & (base_df['DeadLine'] <= win_end) & 
        (~base_df['Status'].astype(str).str.contains('Completed', case=False, na=False))
    ].copy()
    
    case1 = case1.sort_values(by='DeadLine', ascending=True).reset_index(drop=True) if not case1.empty else case1

    # --- CASE 2: High Cost, Delay First ---
    base_df['UsagePercent'] = (base_df['UsedHours'] / base_df['AllocatedHours'].replace(0, np.nan)) * 100
    base_df['UsagePercent'] = base_df['UsagePercent'].replace([np.inf, -np.inf], np.nan).fillna(0).round(1)

    # Threshold: Top 25% expensive projects
    cost_threshold = base_df['Cost'].quantile(0.75) 

    m_high_cost = (base_df['Cost'] >= cost_threshold)
    m_delay = (base_df['Status'].astype(str).str.lower() == 'delay')
    m_inproc = (base_df['Status'].astype(str).str.lower() == 'inprocess') & (base_df['UsagePercent'] <= 55)
    
    case2 = base_df[m_high_cost & (m_delay | m_inproc)].copy()
    
    # SORTING: Put 'Delay' strings before 'InProcess' strings and sort Cost descending
    case2 = case2.sort_values(by=['Status', 'Cost'], ascending=[True, False])

    # --- CASE 3: Historical ---
    last_year, this_month = today.year - 1, today.month
    case3 = base_df[
        (base_df['CreatedDat'].apply(lambda x: x.year if hasattr(x, 'year') else 0) == last_year) &
        (base_df['CreatedDat'].apply(lambda x: x.month if hasattr(x, 'month') else 0) == this_month) &
        (~base_df['Status'].astype(str).str.contains('Completed', case=False, na=False))
    ].copy()
    
    case3 = case3.sort_values(by='CreatedDat', ascending=True).reset_index(drop=True) if not case3.empty else case3

    # --- CASE 4: Dependency-Heavy ---
    DEPENDENCY_THRESHOLD = 3  # 3+ distinct employees on active actions => flagged

    if 'Project_Code' in base_df.columns and 'Master_Code' in df.columns:
        actions_df = df[df['TaskType'].astype(str).str.lower() == 'action'].copy()

        # Only count active actions
        active_actions = actions_df[
            ~actions_df['Status'].astype(str).str.contains('Completed', case=False, na=False)
        ]

        # 1. Calculate overall counts (Total active actions and unique employees)
        dependency_stats = (
            active_actions.groupby('Master_Code')
            .agg(
                TotalActions=('Employee', 'count'),
                UniqueUsers=('Employee', 'nunique')
            )
            .reset_index()
        )

        # 2. Get a sorted, comma-separated list of the unique employees involved
        unique_emp_list = (
            active_actions.groupby('Master_Code')['Employee']
            .apply(lambda x: ", ".join(sorted(list(set(str(e).strip() for e in x if pd.notna(e))))))
            .reset_index(name='DependentEmployeesList')
        )
        dependency_stats = dependency_stats.merge(unique_emp_list, on='Master_Code', how='inner')

        # 3. Find the bottleneck employee (the one with the most active actions)
        emp_action_counts = (
            active_actions.groupby(['Master_Code', 'Employee'])
            .size()
            .reset_index(name='EmpActionCount')
        )
        
        emp_action_counts = emp_action_counts.sort_values(
            by=['Master_Code', 'EmpActionCount'], 
            ascending=[True, False]
        )
        
        top_responsible = emp_action_counts.groupby('Master_Code').first().reset_index()
        top_responsible = top_responsible.rename(columns={
            'Employee': 'MainResponsibleEmployee',
            'EmpActionCount': 'MainResponsibleActionCount'
        })

        dependency_stats = dependency_stats.merge(top_responsible, on='Master_Code', how='inner')

        # Filter active projects and rename the 'Employee' column to 'ProjectOwner'
        not_completed = base_df[
            ~base_df['Status'].astype(str).str.contains('Completed', case=False, na=False)
        ].copy()
        not_completed = not_completed.rename(columns={'Employee': 'ProjectOwner'})

        case4 = not_completed.merge(
            dependency_stats,
            left_on='Project_Code',
            right_on='Master_Code',
            how='inner'
        )
        
        # Filter projects that meet unique user threshold
        case4 = case4[case4['UniqueUsers'] >= DEPENDENCY_THRESHOLD]
        
        # Sort primarily by TotalActions descending, and then by UniqueUsers descending
        case4 = case4.sort_values(
            by=['TotalActions', 'UniqueUsers'], 
            ascending=[False, False]
        ).reset_index(drop=True)
        
        # Rename 'UniqueUsers' to 'DependentCount' to keep existing output compatible
        case4 = case4.rename(columns={'UniqueUsers': 'DependentCount'})
        # Create helper summary string matching your exact requested format:
        # [Project Owner Name] — [Bottleneck Employee] has [Actions] actions
        case4['Bottleneck_Summary'] = case4.apply(
            lambda row: f"{row['ProjectOwner']} — {row['MainResponsibleEmployee']} has {int(row['MainResponsibleActionCount'])} actions"
            if pd.notna(row['ProjectOwner']) and pd.notna(row['MainResponsibleEmployee']) else "", axis=1
        )
        
        if 'Master_Code' in case4.columns:
            case4 = case4.drop(columns=['Master_Code'])
    else:
        # Fallback if structural columns are missing
        case4 = base_df.iloc[0:0].copy()
        case4['DependentCount'] = pd.Series(dtype='int64')
        case4['TotalActions'] = pd.Series(dtype='int64')
        case4['ProjectOwner'] = pd.Series(dtype='object')
        case4['MainResponsibleEmployee'] = pd.Series(dtype='object')
        case4['MainResponsibleActionCount'] = pd.Series(dtype='int64')
        case4['Bottleneck_Summary'] = pd.Series(dtype='object')
        case4['DependentEmployeesList'] = pd.Series(dtype='object')

    def to_dict_safe(temp_df):
        if temp_df.empty: return []
        res = temp_df.copy()
        for col in ['DeadLine', 'CreatedDat']:
            if col in res.columns:
                res[col] = res[col].apply(lambda x: x.strftime('%d-%m-%Y') if hasattr(x, 'strftime') and pd.notna(x) else "")
        return res.replace({np.nan: None, np.inf: 0, -np.inf: 0}).to_dict(orient='records')

    return {
        "report_date": today.strftime("%d-%m-%Y"),
        "case_1_urgent_projects": to_dict_safe(case1),
        "case_2_high_cost_projects": to_dict_safe(case2),
        "case_3_unresolved_historical": to_dict_safe(case3),
        "case_4_dependency_heavy": to_dict_safe(case4)
    }