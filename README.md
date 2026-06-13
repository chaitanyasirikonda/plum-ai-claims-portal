# Plum Health Insurance Claims Processing Portal

Plum is a working claims-processing prototype that demonstrates an explainable, policy-driven workflow for health-insurance claims. The system accepts claim submissions, validates required documents early, extracts structured information, evaluates policy rules, and returns a decision with a visible audit trace.

## What is included
- A FastAPI backend with a LangGraph-based claim workflow
- A Next.js UI for claim submission, claim review, and evaluation dashboard
- Architecture and component-contract documentation in the docs folder
- An evaluation runner that executes all 12 assignment test cases and generates an eval report

## Repository structure
```text
backend/                # FastAPI backend and workflow engine
frontend/               # Next.js UI
docs/                   # Architecture and component contract docs
policy_terms.json       # Policy configuration used by the engine
test_cases.json         # Assignment test cases
DEPLOYMENT.md           # Local and hosted deployment guide
```

## Local setup
### Backend
```bash
python -m pip install -r backend/requirements.txt
python backend/app/main.py
```
The API is available at http://localhost:8000.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
The UI is available at http://localhost:3000.

## Documentation
- Architecture: [docs/architecture.md](docs/architecture.md)
- Component contracts: [docs/component_contracts.md](docs/component_contracts.md)
- Deployment guide: [DEPLOYMENT.md](DEPLOYMENT.md)

## Verification
Verified locally with:
- Backend tests: `pytest backend/app/tests -q`
- Frontend build: `npm run build`
- Evaluation suite: `python backend/app/evaluators/eval_runner.py`

Result: 12/12 test cases passed (100%).

## GitHub deployment notes
- Push this repository to GitHub and use the included GitHub Actions workflow for CI.
- For hosted deployment, run the backend on Render/Railway/Fly.io and the frontend on Vercel.
- Set the frontend environment variable `NEXT_PUBLIC_API_URL` to the deployed backend URL.
