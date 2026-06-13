# GitHub Deployment Guide

## 1. Push to GitHub
1. Create a new GitHub repository.
2. Initialize Git in the project folder if needed:
   ```bash
   git init
   git branch -M main
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

## 2. Local Run
### Backend
```bash
python -m pip install -r backend/requirements.txt
python backend/app/main.py
```
The API will be available at http://localhost:8000.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
The UI will be available at http://localhost:3000.

## 3. Environment Variables
Copy .env.example to .env and fill in the values you need:
```bash
copy .env.example .env
```

## 4. Hosted Deployment Options
- Vercel for the Next.js frontend
- Render / Railway / Fly.io for the FastAPI backend
- Set NEXT_PUBLIC_API_URL to the deployed backend URL in the frontend environment
- Set CORS_ORIGINS to include the deployed frontend origin

## 5. Verification
The project has been verified with:
- Backend tests: `pytest backend/app/tests -q`
- Frontend build: `npm run build`
- Evaluation suite: `python backend/app/evaluators/eval_runner.py`
