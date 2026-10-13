SVSA SECURITY AGENCY MANAGEMENT SYSTEM — FULL-STACK NETLIFY PACKAGE

This package contains:
- frontend/: React + Vite website, configured for Netlify build output in frontend/dist
- backend/: Flask REST API, SQLAlchemy models, JWT authentication, role checks, and payroll/attendance logic

IMPORTANT: This is a deployable starter project, not a claim that every listed feature has been production-certified. Review the limitations below before using real employee/payroll data.

LOCAL DEVELOPMENT
1. Install Node.js 20+ and Python 3.11+.
2. Backend:
   cd backend
   python -m venv .venv
   Windows PowerShell: .venv\Scripts\Activate.ps1
   macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   Copy .env.example to .env and set a strong JWT_SECRET and BOOTSTRAP_ADMIN_PASSWORD.
   Load environment variables into your shell (or use a local dotenv runner) and run: python app.py
   API health check: http://localhost:5000/api/health
3. Frontend:
   cd frontend
   npm install
   Create frontend/.env with VITE_API_BASE_URL=http://localhost:5000
   npm run dev
4. Open the Vite local URL printed in the terminal.

NETLIFY FRONTEND DEPLOYMENT
1. Push the contents to a Git repository.
2. In Netlify choose Add new site > Import an existing project.
3. Base directory: frontend
4. Build command: npm run build
5. Publish directory: dist
6. Set environment variable VITE_API_BASE_URL to the deployed backend base URL (for example https://your-api-service.example.com).
7. Redeploy after changing environment variables.
8. Update frontend/netlify.toml's example proxy target if using the proxy; otherwise configure VITE_API_BASE_URL and ensure backend CORS allows the Netlify site origin.

BACKEND DEPLOYMENT
1. Create a compatible Python web service and a PostgreSQL database.
2. Deploy the repository with backend as the root directory.
3. Build command: pip install -r requirements.txt
4. Start command: gunicorn app:app
5. Configure DATABASE_URL, JWT_SECRET, FRONTEND_ORIGIN, BOOTSTRAP_ADMIN_USERNAME, and BOOTSTRAP_ADMIN_PASSWORD as service environment variables.
6. Use a unique long random JWT_SECRET and a strong initial administrator password.
7. After first login, implement/enable a password change flow before production use.
8. Check /api/health and backend logs.
9. Set VITE_API_BASE_URL in Netlify to the backend URL and redeploy.

INITIAL ACCOUNTS
- No default password is embedded in the frontend or source code.
- The backend creates a bootstrap Director account only when BOOTSTRAP_ADMIN_PASSWORD is configured in the backend environment.
- Manager accounts are created by the Director using User Management and must be provisioned with strong temporary passwords. The UI currently expects a temporary password of at least 12 characters. The requested short values like svsa1/svsa2 are too weak for production; if the agency uses them as initial conventions, they must be temporary and changed immediately.
- A change-password API endpoint exists, but the frontend must add a mandatory first-login password-change screen before this project is used with real data.

POLICY DEFAULTS
- Director monthly basic salary is forced to ₹45,000 on employee creation/update.
- Managers have a configurable limit of three sites.
- First two absent days have no absence salary deduction.
- From the third absent day, deduction = (chargeable absences after grace) × (basic salary / configured divisor).
- Approved advances scheduled for a payroll month are eligible for same-month recovery; insufficient salary must be reviewed and must not create an unintended negative net pay.
- PF/ESI rates default to zero and must be verified by a qualified payroll professional before use.
- All salary and attendance rules should be reviewed against applicable law and the agency's written policy.

CURRENT IMPLEMENTATION NOTES / LIMITATIONS
- Core backend models and API routes are included for employees, sites, deployment, attendance, payroll, advances, verification, user management, reports, settings, dashboard and audit.
- The frontend provides role-aware navigation, login, module tables, forms, exports and dashboards.
- The starter currently needs additional engineering and testing before production:
  * The forced first-login password-change UI must be completed.
  * Supervisor/employee self-service restrictions and some module-specific permission details need deeper review.
  * Full CRUD/edit/delete coverage for every module is not complete.
  * Historical assignment handling, bulk attendance, payroll adjustment workflow, robust advance-recovery transactions and statutory calculations need integration tests and refinement.
  * PF/ESI and tax calculations are placeholders/configurable estimates, not legal advice.
  * The initial SQLAlchemy create_all setup is suitable for a starter; use migrations for ongoing schema changes.
  * Add backups, restore procedures, monitoring, HTTPS, rate limiting and production hardening before storing real sensitive data.
- Do not use the starter for real payroll until tests are executed and limitations resolved.
- Never commit .env files or production credentials to Git.
