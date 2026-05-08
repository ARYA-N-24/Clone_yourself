Clone Yourself

An AI-powered personal digital worker that learns how users communicate, prioritize, schedule, and manage repetitive workflows to improve productivity.


---

Problem Statement

Students, professionals, founders, and teams spend a large amount of time every day on repetitive administrative work such as:

replying to routine emails

scheduling meetings

following up with people

organizing tasks across apps

prioritizing incoming work

switching between multiple productivity tools


Existing tools are fragmented and generic. They assist with isolated tasks but do not understand a user’s personal working style, preferences, or workflow behavior.

As a result, users spend more time managing work rather than doing meaningful work.


---

Solution

Clone Yourself is an AI-powered productivity assistant that acts like a digital worker version of the user.

The platform learns user behavior patterns such as:

communication style

meeting preferences

task priorities

scheduling habits

workflow decisions


Using this information, the system can:

generate AI email replies

suggest meeting schedules

automate follow-ups

prioritize emails

provide productivity analytics

generate daily AI productivity briefs


The goal is not to replace humans, but to multiply their productivity.


---

Key Features

AI Email Assistant

Fetches emails from Gmail

Classifies emails as urgent, normal, or low priority

Generates personalized AI replies

Allows one-click reply generation


AI Calendar Assistant

Suggests optimized meeting slots

Integrates with Google Calendar

Creates calendar events automatically


Productivity Dashboard

Displays priority tasks

Shows pending replies and follow-ups

Tracks actions automated and time saved


Analytics Module

Visualizes productivity metrics

Displays activity breakdown graphs

Tracks weekly automation trends


Daily AI Brief

Shows urgent tasks

Highlights follow-ups

Identifies workflow risks



---

Tech Stack

Frontend

Next.js (React)

Tailwind CSS


Backend

FastAPI (Python)


Database

PostgreSQL


AI Layer

Ollama (Phi-3 / Mistral)

OpenAI compatible architecture


APIs

Gmail API

Google Calendar API



---

System Architecture

Frontend (Next.js)
        ↓
FastAPI Backend
        ↓
Behavior Engine + AI Layer
        ↓
PostgreSQL Database
        ↓
Google APIs (Gmail + Calendar)


---

Setup Instructions

1. Clone Repository

git clone <repository-url>
cd clone-yourself


---

Backend Setup

2. Create Python Environment

python -m venv venv

Activate environment:

Windows

venv\Scripts\activate

Linux/Mac

source venv/bin/activate


---

3. Install Backend Dependencies

cd backend
pip install -r requirements.txt


---

4. Configure Environment Variables

Create .env

DATABASE_URL=postgresql://postgres:password@localhost:5432/cloneyourself

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

JWT_SECRET_KEY=
TOKEN_ENCRYPTION_KEY=

FRONTEND_URL=http://localhost:3000

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi3


---

5. Setup PostgreSQL Database

Create database:

CREATE DATABASE cloneyourself;

Run migrations:

alembic upgrade head


---

6. Run Backend

uvicorn main:app --reload

Backend runs on:

http://localhost:8000


---

Frontend Setup

7. Install Frontend Dependencies

cd frontend
npm install


---

8. Configure Frontend Environment

Create .env.local

NEXTAUTH_URL=http://localhost:3000

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

NEXT_PUBLIC_API_URL=http://localhost:8000


---

9. Run Frontend

npm run dev

Frontend runs on:

http://localhost:3000


---

Ollama Setup (Local AI)

Install Ollama

Download: Ollama


---

Pull AI Model

ollama pull phi3


---

Run Model

ollama run phi3


---

Google API Setup

Enable:

Gmail API

Google Calendar API


From: Google Cloud Console

Add redirect URIs:

http://localhost:8000/auth/callback
http://localhost:3000/api/auth/callback/google


---

Usage

AI Email Workflow

1. Login with Google


2. Open Emails module


3. AI classifies emails automatically


4. Click “Generate Reply”


5. Review or send AI-generated response




---

Calendar Workflow

1. Open Calendar module


2. AI suggests meeting slots


3. Confirm preferred slot


4. Event automatically added to Google Calendar




---

Analytics Workflow

1. Open Analytics tab


2. View:

actions automated

emails classified

replies sent

productivity trends





---

Future Scope

WhatsApp integration

Voice assistant mode

Cross-platform automation

Enterprise workflow copilots

Smart follow-up automation

Personalized productivity memory engine



---

Team

Team Name: Stephan Walking
Institution: M S Ramaiah Institute of Technology


---

Pitch Line

> “We don’t replace people. We multiply them.”