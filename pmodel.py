import pandas as pd
import numpy as np

class ProjectDataProcessor:
    def __init__(self, raw_data):
        """
        Initializes the processor with raw database rows (list of dictionaries or DataFrame).
        """
        if isinstance(raw_data, pd.DataFrame):
            self.df = raw_data.copy()
        else:
            self.df = pd.DataFrame(raw_data)
            
        self._clean_dataframe()

    def _clean_dataframe(self):
        """Cleans and standardizes columns for safe pandas processing."""
        if self.df.empty:
            return

        # Stored procedures use both names for the same timeline fields.
        if "TimelineDate" not in self.df.columns:
            for alias in ("DailyWorkDate", "WorkDate"):
                if alias in self.df.columns:
                    self.df["TimelineDate"] = self.df[alias]
                    break
        if "DailyTimeSpent" not in self.df.columns and "TimeCount" in self.df.columns:
            self.df["DailyTimeSpent"] = self.df["TimeCount"]
            
        # Ensure codes are clean strings
        self.df["Master_Code"] = self.df["Master_Code"].fillna("").astype(str).str.strip()
        self.df["Project_Code"] = self.df["Project_Code"].fillna("").astype(str).str.strip()
        
        # Ensure allocated hours are numeric
        if "AllocatedHours" in self.df.columns:
            self.df["AllocatedHours"] = self.df["AllocatedHours"].map(self._parse_time_to_hours)
        if "UsedHours" in self.df.columns:
            self.df["UsedHours"] = self.df["UsedHours"].map(self._parse_time_to_hours)
            
        # Standardize date types
        for date_col in ["DeadLine", "CreatedDate", "TimelineDate"]:
            if date_col in self.df.columns:
                self.df[date_col] = pd.to_datetime(self.df[date_col], errors="coerce")

    @staticmethod
    def _parse_time_to_hours(time_val):
        """
        Converts time strings (e.g., '07:45' or '7.75') or decimals safely to float hours.
        """
        if pd.isna(time_val) or not time_val:
            return 0.0
        
        time_str = str(time_val).strip()
        
        # Handle HH:MM format
        if ":" in time_str:
            try:
                parts = time_str.split(":")
                hours = int(parts[0])
                minutes = int(parts[1]) if len(parts) > 1 else 0
                return hours + (minutes / 60.0)
            except (ValueError, IndexError):
                pass
                
        # Handle float/decimal format
        try:
            return float(time_str)
        except ValueError:
            return 0.0

    def compute_dashboard_kpis(self):
        """
        Calculates KPIs avoiding duplication caused by the SQL full join.
        """
        if self.df.empty:
            return {
                "total_projects": 0,
                "total_actions_logged": 0,
                "total_employees": 0,
                "total_allocated_hours": 0.0,
                "total_used_hours": 0.0
            }

        # 1. Identify Unique Projects (Master_Code is empty)
        project_mask = (self.df["Master_Code"] == "") | (self.df["Master_Code"].str.lower() == "none")
        unique_projects = self.df[project_mask].drop_duplicates(subset=["Project_Code"])

        total_projects = unique_projects["Project_Code"].nunique()
        total_allocated_hours = float(unique_projects["AllocatedHours"].sum())

        # 2. Identify Unique Action Logs (where WorkAchieved is present and TimelineDate is valid)
        action_logs = self.df[
            self.df["TimelineDate"].notna() &
            self.df["DailyTimeSpent"].notna()
        ].copy()
        total_actions_logged = len(action_logs)

        # 3. Calculate used hours from each individual daily log
        action_logs["ParsedHours"] = action_logs["DailyTimeSpent"].apply(self._parse_time_to_hours)
        total_used_hours = round(float(action_logs["ParsedHours"].sum()), 2)

        # 4. Count unique active employees (either primary owner or logging work)
        assigned_employees = set(self.df["EmployeeId"].dropna().unique())
        logging_employees = set(self.df["ActionLoggedBy"].dropna().unique())
        unique_employees = list(assigned_employees.union(logging_employees))
        total_employees = len([emp for emp in unique_employees if str(emp).strip() != "" and str(emp) != "nan"])

        return {
            "total_projects": total_projects,
            "total_actions_logged": total_actions_logged,
            "total_employees": total_employees,
            "total_allocated_hours": total_allocated_hours,
            "total_used_hours": total_used_hours
        }

    def get_project_timeline_tree(self, exclude_completed=True):
        """
        Structures data into three levels with strict activity rules:
        - Parent Projects are shown ONLY if they are not completed.
        - Sub-Actions are shown if they are currently active/in-progress, 
          even if the employee doesn't own the parent project or if the parent is completed.
        """
        if self.df.empty:
            return []

        parent_projects = {}
        parent_mask = (self.df["Master_Code"] == "") | (self.df["Master_Code"].str.lower() == "none")
        parent_df = self.df[parent_mask].drop_duplicates(subset=["Project_Code"])

        # Step 1: Map Parent Projects (Only if they are not completed)
        for _, row in parent_df.iterrows():
            p_code = row["Project_Code"]
            status_str = str(row.get("Status", "")).strip().lower()

            # Rule: If the employee owns the parent project, only show it if it is NOT completed
            if exclude_completed and status_str == "completed":
                continue

            parent_projects[p_code] = {
                "Parent_Project_Code": p_code,
                "Parent_Project_Name": row["Project_Name"],
                "Parent_Project_Description": row.get("Project_Description", ""),
                "Employee": row.get("Employee", ""),
                "EmployeeId": row.get("EmployeeId", ""),
                "CompanyName": row.get("CompanyName", ""),
                "DeadLine": row["DeadLine"].strftime('%Y-%m-%d') if pd.notna(row["DeadLine"]) else None,
                "Status": row.get("Status", ""),
                "AllocatedHours": float(row.get("AllocatedHours", 0.0)),
                "TotalProjectUsedHours": 0.0,
                "Cost": float(row.get("Cost", 0.0)),
                "ProjectType": row.get("ProjectType", ""),
                "Team_Support": row.get("Team_Support", ""),
                "Sub_Actions": {}  # Holds child sub-projects / actions
            }

        # Step 2: Map Active Sub-Projects / Actions
        action_df = self.df[~parent_mask].copy()

        for _, row in action_df.iterrows():
            p_code = row["Project_Code"]
            m_code = row["Master_Code"]  # Parent project code
            action_status = str(row.get("Status", "")).strip().lower()

            # Rule: If the sub-action itself is completed, exclude it
            if exclude_completed and action_status == "completed":
                continue

            # Rule: If the sub-action is active, we MUST show it.
            # If its parent is not in parent_projects, create a container for it using the resolved ParentProjectName.
            if m_code not in parent_projects:
                parent_projects[m_code] = {
                    "Parent_Project_Code": m_code,
                    "Parent_Project_Name": row.get("ParentProjectName", f"Parent Project Reference ({m_code})"),
                    "Parent_Project_Description": "Parent project of active sub-actions.",
                    "Employee": row.get("Employee", ""),
                    "EmployeeId": row.get("EmployeeId", ""),
                    "CompanyName": row.get("CompanyName", ""),
                    "DeadLine": None,
                    "Status": "Active Actions Portfolio",
                    "AllocatedHours": 0.0,
                    "TotalProjectUsedHours": 0.0,
                    "Cost": 0.0,
                    "ProjectType": "",
                    "Team_Support": "",
                    "Sub_Actions": {}
                }

            parent_node = parent_projects[m_code]
            if p_code not in parent_node["Sub_Actions"]:
                parent_node["Sub_Actions"][p_code] = {
                    "Action_Code": p_code,
                    "Action_Name": row["Project_Name"],
                    "Action_Description": row.get("Project_Description", ""),
                    "Status": row.get("Status", ""),
                    "AllocatedHours": float(row.get("AllocatedHours", 0.0)),
                    "ActionUsedHours": 0.0,
                    "Timeline_Logs": []
                }

            # Map active work achievement logs
            if pd.notna(row["TimelineDate"]) and pd.notna(row["DailyTimeSpent"]):
                parsed_hours = self._parse_time_to_hours(row["DailyTimeSpent"])
                
                existing_logs = parent_node["Sub_Actions"][p_code]["Timeline_Logs"]
                duplicate_found = any(
                    x["TimelineDate"] == row["TimelineDate"].strftime('%Y-%m-%d') and 
                    x["StartTime"] == str(row.get("StartTime", "")) and 
                    x["WorkAchieved"] == str(row.get("WorkAchieved", ""))
                    for x in existing_logs
                )

                if not duplicate_found:
                    parent_node["Sub_Actions"][p_code]["Timeline_Logs"].append({
                        "TimelineDate": row["TimelineDate"].strftime('%Y-%m-%d'),
                        "StartTime": str(row.get("StartTime", "")),
                        "EndTime": str(row.get("EndTime", "")),
                        "DailyTimeSpent": str(row.get("DailyTimeSpent", "")),
                        "WorkAchieved": str(row.get("WorkAchieved", "")),
                        "DailyReportStatus": str(row.get("DailyReportStatus", "")),
                        "ActionLoggedBy": str(row.get("ActionLoggedBy", ""))
                    })
                    parent_node["Sub_Actions"][p_code]["ActionUsedHours"] += parsed_hours
                    parent_node["TotalProjectUsedHours"] += parsed_hours

        # Convert mappings to sorted lists, discarding any parent project container 
        # that didn't end up having any active sub-actions or parent records
        final_tree = []
        for p_code, parent_node in parent_projects.items():
            if parent_node["Sub_Actions"] or parent_node["Status"] != "Active Actions Portfolio":
                parent_node["TotalProjectUsedHours"] = round(parent_node["TotalProjectUsedHours"], 2)
                action_list = []
                for a_code, action_node in parent_node["Sub_Actions"].items():
                    action_node["ActionUsedHours"] = round(action_node["ActionUsedHours"], 2)
                    action_node["Timeline_Logs"].sort(key=lambda x: x["TimelineDate"], reverse=True)
                    action_list.append(action_node)
                
                parent_node["Sub_Actions"] = action_list
                final_tree.append(parent_node)

        return final_tree