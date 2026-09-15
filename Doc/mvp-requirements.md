# RicozPortfolio — MVP Requirements

**Status:** Approved scope. **Source of truth for what to build.** Technical realization is in `architecture.md`; build sequencing is in `implementation-plan.md`.
**Priority scale:** P0 = blocks the core journey, nothing works without it · P1 = required for a complete MVP demo · P2 = valuable but the MVP is still coherent without it.
**Status column:** `MVP` = in scope now · `Post-MVP` = explicitly deferred (listed in Section 12 for completeness, not to be built during MVP phases).

---

## 1. Product Recap (for context, not re-derivation)

RicozPortfolio takes organizations through: **Strategy & Goals → Demand/Ideas → Business Case → Approval → Portfolio & Project Planning → Execution → Monitoring (Budget/Risk) → Dashboards.** The MVP implements a thin-but-real slice of every stage rather than a deep implementation of only execution — this is what proves it's a *portfolio* tool and not a plain task tracker. The single most important journey is **Idea → Business Case → Approval → Project conversion**; everything else is scoped around making that journey real and demoable.

---

## 2. Authentication & User Management

### 2.1 Registration & Organization Creation — **MVP, P0**
- **Purpose:** Let a new organization onboard itself with no manual provisioning.
- **User story:** As a prospective customer, I want to register and automatically get my own organization, so I can start using the product immediately.
- **Business rules:**
  - Registration creates one `Organization` and one `User` in a single transaction.
  - The registering user is automatically assigned the `org_admin` role.
  - Email must be globally unique across the entire system (`UNIQUE(email)`).
  - Password is hashed (bcrypt) before storage; plaintext is never persisted or logged.
- **Acceptance criteria:**
  - Given valid registration details, when submitted, then an Organization and User are created and the user is logged in (tokens issued).
  - Given an email that already exists anywhere in the system, when registration is attempted, then it's rejected with a clear error.
- **Status:** MVP.

### 2.2 Login / Logout — **MVP, P0**
- **Purpose:** Authenticate returning users.
- **User story:** As a registered user, I want to log in and out securely.
- **Business rules:** Access token (JWT, in-memory on frontend) issued on login; refresh token set as httpOnly Secure cookie. Logout clears the refresh cookie.
- **Acceptance criteria:**
  - Given correct credentials, when logging in, then an access token is returned and a refresh cookie is set.
  - Given incorrect credentials, when logging in, then a 401 is returned with no token issued.
  - Given a logged-in session, when logging out, then the refresh cookie is invalidated and subsequent refresh attempts fail.
- **Status:** MVP.

### 2.3 Token Refresh — **MVP, P0**
- **Purpose:** Keep users logged in without storing long-lived tokens in vulnerable browser storage.
- **Business rules:** Refresh reads the httpOnly cookie, issues a new access token, rotates the refresh cookie.
- **Acceptance criteria:**
  - Given a valid refresh cookie, when `/auth/refresh` is called, then a new access token is returned and the cookie is rotated.
  - Given an expired/invalid/missing refresh cookie, when `/auth/refresh` is called, then it's rejected (401), forcing re-login.
- **Status:** MVP.

### 2.4 Roles & Permissions (RBAC) — **MVP, P0**
- **Purpose:** Ensure users only see and do what their role permits.
- **User story:** As an Org Admin, I want to control who can approve ideas, manage projects, or just view/update their own tasks.
- **Business rules:** Four fixed roles: `org_admin`, `portfolio_manager`, `project_manager`, `team_member`. A user may hold more than one role. Roles are seeded, not user-creatable, in MVP.
  | Role | Permitted actions |
  |---|---|
  | org_admin | Everything; manage users/roles/org settings |
  | portfolio_manager | Strategic goals, idea review, business case, approve/reject, convert idea→project, manage portfolios, view all projects |
  | project_manager | Manage assigned projects: members, tasks, milestones, budget, risks |
  | team_member | View assigned projects/tasks, update own task status, submit ideas |
- **Acceptance criteria:**
  - Given a user with role `team_member`, when they attempt to approve an idea, then the request is denied (403).
  - Given a user with role `org_admin`, when they assign a role to another user, then that user's permissions update accordingly.
- **Status:** MVP.

### 2.5 User Profile Management — **MVP, P1**
- **Purpose:** Basic self-service and admin user management.
- **User story:** As an Org Admin, I want to invite/deactivate users; as a user, I want to see my own profile.
- **Business rules:** Only `org_admin` can create/invite users or change roles; users can view (not necessarily edit) their own profile in MVP.
- **Acceptance criteria:** Given an org_admin, when they deactivate a user, then that user can no longer log in.
- **Status:** MVP.

---

## 3. Organization & Multi-Tenancy

### 3.1 Tenant Isolation — **MVP, P0**
- **Purpose:** Guarantee one organization can never see another's data — a non-negotiable trust requirement for a multi-tenant SaaS.
- **Business rules:** Every tenant-scoped table carries `organization_id`; every query is scoped to the authenticated user's organization, never a client-supplied value.
- **Acceptance criteria:**
  - Given a user in Organization A, when they request any resource belonging to Organization B (by ID), then the system returns 403/404, never the data.
  - Given two organizations with identically-named entities, when each organization's users list their data, then each sees only their own.
- **Status:** MVP.

---

## 4. Strategy Management

### 4.1 Strategic Goals — **MVP, P1**
- **Purpose:** Give ideas something concrete to align to, so "strategic alignment" is a real link, not a label.
- **User story:** As an Org Admin or Portfolio Manager, I want to define strategic goals so ideas can be tied to organizational priorities.
- **Business rules:** A goal has a title and optional description; no KPI/scoring engine in MVP.
- **Acceptance criteria:** Given a portfolio_manager, when they create a Strategic Goal, then it appears in the goals list and is selectable when submitting an Idea.
- **Status:** MVP. *(KPI tracking, strategic alignment scoring: Post-MVP.)*

---

## 5. Demand & Business Case Management

### 5.1 Idea Submission — **MVP, P0**
- **Purpose:** Capture demand from anywhere in the org — the entry point of the whole lifecycle.
- **User story:** As any user, I want to submit an idea/request, optionally linked to a strategic goal.
- **Business rules:** Idea statuses: `draft → submitted → in_review → approved/rejected`. Any authenticated user can submit.
- **Acceptance criteria:** Given a logged-in user, when they submit an idea with a title, then it appears in the org's idea list with status `submitted`.
- **Status:** MVP.

### 5.2 Business Case — **MVP, P0**
- **Purpose:** Force a minimal cost/benefit justification before approval — this is what makes "evaluation" real.
- **User story:** As a Portfolio Manager, I want to attach a business case (cost, expected benefit) to an idea so its value can be judged.
- **Business rules:** One Business Case per Idea (1:1). `ROI = (estimated_benefit - estimated_cost) / estimated_cost`, computed automatically. Only `portfolio_manager`/`org_admin` can create it.
- **Acceptance criteria:**
  - Given an idea and a cost/benefit input, when a Business Case is saved, then ROI is computed and displayed.
  - Given an idea without a Business Case, when approval is attempted, then it's rejected with a clear error.
- **Status:** MVP. *(NPV, Payback period, full financial modeling: Post-MVP.)*

### 5.3 Approval Workflow — **MVP, P0**
- **Purpose:** Formal decision point converting demand into sanctioned investment.
- **User story:** As a Portfolio Manager, I want to approve or reject an idea with a business case, and see a record of who decided and when.
- **Business rules:** Single-step approval (no multi-stage/quorum workflow in MVP). Every decision creates an immutable `Approval` record (audit trail) in addition to updating the idea's status.
- **Acceptance criteria:**
  - Given an idea with a Business Case in status `submitted`/`in_review`, when a portfolio_manager approves it, then status becomes `approved` and an Approval record is created.
  - Given the same idea, when a portfolio_manager rejects it, then status becomes `rejected` and an Approval record is created.
  - Given a user without the required role, when they attempt to approve/reject, then it's denied (403).
- **Status:** MVP. *(Multi-stage/configurable workflow, delegation, quorum: Post-MVP.)*

### 5.4 Idea → Project Conversion — **MVP, P0 (the critical seam)**
- **Purpose:** Bridge the decision phase to execution — the single feature that proves RicozPortfolio is a portfolio tool, not just a tracker.
- **User story:** As a Portfolio Manager, I want to convert an approved idea into a project within a chosen portfolio.
- **Business rules:** Only `approved` ideas are convertible. The new project pre-fills name/description from the idea and stores `source_idea_id` for permanent traceability. A given idea can only be converted once.
- **Acceptance criteria:**
  - Given an approved idea, when converted, then a new Project is created, linked to the chosen Portfolio, with `source_idea_id` set.
  - Given an idea not yet approved, when conversion is attempted, then it's rejected.
  - Given a project created from an idea, when viewed, then the originating idea and its business case are visible from the project.
- **Status:** MVP.

---

## 6. Portfolio Management

### 6.1 Portfolio CRUD — **MVP, P0**
- **Purpose:** The core grouping concept for projects and the primary lens for portfolio-level decision-making.
- **User story:** As a Portfolio Manager, I want to create portfolios and see which projects sit inside each.
- **Business rules:** A Portfolio belongs to one Organization. Soft-delete (not hard delete) on removal.
- **Acceptance criteria:** Given a portfolio_manager, when they create a portfolio and later view it, then it shows the list of Projects assigned to it.
- **Status:** MVP. *(Programs — a layer between Portfolio and Project: Post-MVP.)*

### 6.2 Portfolio Comparison & Prioritization — **MVP, P1**
- **Purpose:** Let management compare projects within/across portfolios to decide what matters most.
- **User story:** As a Portfolio Manager, I want to see projects side-by-side (status, budget %, health) to compare them.
- **Business rules:** Manual/ordinal comparison via the dashboard list (sortable/filterable); no algorithmic priority score in MVP.
- **Acceptance criteria:** Given a portfolio with multiple projects, when viewed on the dashboard, then projects are listed with sortable status/budget/health columns.
- **Status:** MVP (manual comparison only). *(Weighted priority scoring/ranking algorithm: Post-MVP.)*

---

## 7. Project Management

### 7.1 Project CRUD & Members — **MVP, P0**
- **Purpose:** The execution container where actual work happens.
- **User story:** As a Portfolio/Project Manager, I want to create a project (directly, or via idea conversion) and add team members to it.
- **Business rules:** A project belongs to exactly one Portfolio and one Organization. Statuses: `planned, active, on_hold, completed, cancelled`. Soft-delete on removal. Members have a project-level role (`manager`/`member`) distinct from their org-wide role.
- **Acceptance criteria:**
  - Given a portfolio_manager, when they create a project directly (not from an idea), then it's created with status `planned`.
  - Given a project_manager on a project, when they add a member, then that member gains visibility of the project.
- **Status:** MVP.

### 7.2 Task Management — **MVP, P0**
- **Purpose:** The unit of day-to-day execution work.
- **User story:** As a Project Manager, I want to create and assign tasks; as a Team Member, I want to update the status of tasks assigned to me.
- **Business rules:** Statuses: `todo, in_progress, done`. Priorities: `low, medium, high`. A team_member may only update status on tasks assigned to them; full edit rights belong to project_manager+.
- **Acceptance criteria:**
  - Given a project_manager, when they create and assign a task, then it appears on the assignee's task list.
  - Given a team_member assigned to a task, when they change its status, then the change is saved and reflected on the project dashboard.
- **Status:** MVP. *(Subtasks, task dependencies, Kanban/Gantt/Calendar views: Post-MVP.)*

### 7.3 Milestones — **MVP, P1**
- **Purpose:** Mark significant checkpoints separate from routine tasks.
- **User story:** As a Project Manager, I want to define milestones with due dates and track whether they were achieved.
- **Business rules:** Statuses: `pending, achieved, missed`.
- **Acceptance criteria:** Given a project_manager, when they create a milestone with a due date, then it appears on the project timeline/list and its status can be updated.
- **Status:** MVP.

---

## 8. Financial Management

### 8.1 Project Budget — **MVP, P1**
- **Purpose:** Make planned investment visible and comparable to actuals — a core PPM expectation.
- **User story:** As a Project Manager, I want to set a planned budget for my project.
- **Business rules:** One budget per project (1:1). Currency field, default `USD` `[PROPOSED default]`.
- **Acceptance criteria:** Given a project_manager, when they set a planned budget, then it's stored and visible on the project's Budget tab.
- **Status:** MVP.

### 8.2 Expense Tracking — **MVP, P1**
- **Purpose:** Capture actual spend against the plan.
- **User story:** As a Project Manager, I want to log expenses so actual cost is tracked against the planned budget.
- **Business rules:** Actual spend = `SUM(expenses.amount)` for the project (computed, not separately stored).
- **Acceptance criteria:** Given a project with a planned budget, when expenses are logged, then "planned vs. actual" updates and is visible on the dashboard.
- **Status:** MVP. *(Budget variance analytics, cost forecasting, profitability/ROI-at-completion: Post-MVP.)*

---

## 9. Risk & Governance

### 9.1 Risk Log — **MVP, P1**
- **Purpose:** Make risk exposure visible as a first-class part of project monitoring, not an afterthought.
- **User story:** As a Project Manager, I want to log risks with probability/impact and track their status.
- **Business rules:** Probability/impact each `low/medium/high` (no numeric scoring matrix in MVP). Status: `open, mitigated, closed`.
- **Acceptance criteria:** Given a project_manager, when they log a risk, then it appears in the project's risk list and its status can be updated.
- **Status:** MVP. *(Numeric risk scoring/matrix, mitigation-plan workflow, issue/blocker management, change requests, stage-gate approvals, formal audit/governance history module: Post-MVP.)*

---

## 10. Dashboards & Reporting

### 10.1 Project Dashboard — **MVP, P0**
- **Purpose:** The "so what" screen proving execution data is actually useful, not just stored.
- **User story:** As a Project Manager or stakeholder, I want to see task completion %, budget used, and open risk count for a project at a glance.
- **Business rules:** All values computed live from underlying data (tasks, budget, expenses, risks) — never cached/stale for MVP (see `architecture.md` §7 on caching being deferred).
- **Acceptance criteria:** Given a project with tasks, budget, and risks entered, when the dashboard is viewed, then it reflects real, current values.
- **Status:** MVP.

### 10.2 Portfolio Dashboard — **MVP, P0**
- **Purpose:** The portfolio-level decision view — the payoff of the whole product concept.
- **User story:** As a Portfolio Manager, I want to see all projects in a portfolio with status, budget %, and a simple health flag.
- **Business rules:** Health flag is a simple rule (`[PROPOSED]` e.g., budget-used % vs. time-elapsed %, or any open high-impact risk) — **not** a weighted scoring algorithm.
- **Acceptance criteria:** Given a portfolio with multiple projects, when the dashboard is viewed, then each project shows status, budget %, and a health flag (`on_track`/`at_risk`/`off_track`).
- **Status:** MVP (rule-based flag only). *(Project health scoring engine, delay/bottleneck/budget-overrun detection, executive/cross-portfolio analytics, recommendations, custom report builder: Post-MVP.)*

---

## 11. Explicit MVP Non-Goals

Stated so they are not accidentally built during MVP phases:
- No configurable/multi-stage workflow engine — approval is a hardcoded single step.
- No email/notification delivery.
- No file attachments/document management.
- No mobile app — responsive web only.
- No AI-assisted scoring or recommendations.
- No Programs layer (Portfolio → Project directly for MVP).
- No resource/skills/capacity management module.

---

## 12. Post-MVP Feature Register (for roadmap visibility only — not scheduled in `implementation-plan.md`)

| Feature | Notes |
|---|---|
| Programs (Portfolio → Program → Project) | Adds a hierarchy layer, not needed to prove the concept |
| Task dependencies, Gantt/Calendar views | Real scheduling complexity |
| Multi-stage/configurable approval workflow | Configurability is a scaling feature |
| Strategic alignment scoring, KPI tracking | Needs a scoring engine |
| Weighted priority scoring/ranking algorithm | Manual comparison suffices for MVP |
| Resource capacity/utilization, overallocation detection, skill-based search | Needs a resource data model |
| Budget variance/forecasting, cost forecasting, profitability/ROI-at-completion | Needs historical data MVP won't have |
| Kanban board view | UX enhancement over list view |
| Change requests, stage-gate approvals, formal governance/audit history | Governance depth beyond "approval exists" |
| Comments/activity feed | High value, orthogonal to lifecycle proof |
| Project health scoring engine, delay/bottleneck/overrun detection, recommendations | Explicitly excluded per "no complex automation in MVP" |
| Executive/cross-portfolio analytics, custom report builder | Needs usage data and maturity beyond MVP |
| Notifications/email | No MVP feature requires it |
| File attachments/documents | Not in MVP scope |
| Multi-organization membership per user | Current model is one-email-one-org; documented extension path in `architecture.md` §5 |
| Rate limiting, RLS-based tenant isolation hardening | Post-MVP security hardening |

---

## 13. MVP Definition of Done (product-level)

- [ ] A new organization can register and is fully isolated from all other organizations' data.
- [ ] All 4 roles exist and enforce distinct, tested permissions.
- [ ] A Strategic Goal can be created and referenced by an Idea.
- [ ] An Idea can be submitted, given a Business Case, approved, and converted into a Project — with full traceability preserved.
- [ ] A Project can be placed in a Portfolio, given Members, Tasks, Milestones, a Budget, and Risks.
- [ ] The Project dashboard and Portfolio dashboard both reflect real data entered through the UI.
- [ ] The full journey (Idea → Business Case → Approval → Project → Execution → Dashboard) can be demoed live, start to finish, by someone who is not the developer.
- [ ] No feature from Section 12 (Post-MVP) has crept into the build.
