# SpendSense AI

An AI money companion for students and young adults worldwide, with India as the first and best-supported market. SpendSense tells you whether you can afford something **before** you spend, and warns you **before** you run out of money.

## Stage 1 Setup (Foundation & UI Shell)

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

### 4. Run the development server

```bash
uvicorn app.main:app --reload --port 3000
```

Then open `http://localhost:3000` in your browser.

### 5. Run tests

```bash
pytest
```
