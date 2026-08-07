import os
import requests

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://68.178.160.26:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:1b"
)


def call_llm(prompt):

    r = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )

    r.raise_for_status()

    return r.json()["response"]


def build_dashboard_prompt(
    kpi,
    important_projects,
    employee_summary,
    selected_project
):

    return f"""
You are a Senior AI Project Management Assistant.

You are analyzing a Project Management Dashboard.

Your task is NOT to repeat the dashboard.

Instead explain the dashboard like a Project Manager.

Write:

1. Overall company performance (2 lines)

2. Mention the three important projects.
Explain why each project needs attention.
Keep each project explanation under 2 lines.

3. Mention employee workload.

4. Mention project execution performance.

5. Give 5 practical recommendations for management.

Use simple professional English.

Do not repeat KPI numbers unless necessary.

Dashboard

KPI
{kpi}

Important Projects
{important_projects}

Selected Project
{selected_project}

Employee Summary
{employee_summary}
"""

    return prompt


def summarize_dashboard(
    kpi,
    important_projects,
    employee_summary,
    selected_project
):

    prompt = build_dashboard_prompt(
        kpi,
        important_projects,
        employee_summary,
        selected_project
    )

    return call_llm(prompt)