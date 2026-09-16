import os
import subprocess
import time

# Inject environment variable so Pydantic settings uses localhost for local Windows execution
os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5432/ricozportfolio"

def run_alembic(message):
    subprocess.run([r".venv\Scripts\alembic.exe", "revision", "--autogenerate", "-m", message], check=True)
    subprocess.run([r".venv\Scripts\alembic.exe", "upgrade", "head"], check=True)
    time.sleep(1)

def set_init_content(exports):
    content = ""
    for exp in exports:
        content += f"from app.models.{exp} import *\n"
    with open("app/models/__init__.py", "w") as f:
        f.write(content)

def main():
    print("Generating Group 1...")
    set_init_content(["mixins", "organization", "role", "user"])
    run_alembic("Group 1: Orgs, Users, Roles")

    print("Generating Group 2...")
    set_init_content(["mixins", "organization", "role", "user", "strategic_goal", "idea"])
    run_alembic("Group 2: Strategic Goals, Ideas")

    print("Generating Group 3...")
    set_init_content(["mixins", "organization", "role", "user", "strategic_goal", "idea", "business_case", "approval"])
    run_alembic("Group 3: Business Cases, Approvals")

    print("Generating Group 4...")
    set_init_content(["mixins", "organization", "role", "user", "strategic_goal", "idea", "business_case", "approval", "portfolio", "project", "project_member"])
    run_alembic("Group 4: Portfolios, Projects, ProjectMembers")

    print("Generating Group 5...")
    set_init_content([
        "mixins", "organization", "role", "user", "strategic_goal", "idea", 
        "business_case", "approval", "portfolio", "project", "project_member",
        "task", "milestone", "risk", "budget", "expense"
    ])
    run_alembic("Group 5: Tasks, Milestones, Risks, Budgets, Expenses")

if __name__ == "__main__":
    main()
