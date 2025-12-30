# Case AI Backend

## Setup (local using docker-compose)

1. Copy `.env` (create one) and set:
   - `JWT_SECRET`
   - `OPENAI_API_KEY`
   - (optional S3 credentials)
   
2. Run Migrations  
   - alembic upgrade head


3. Build and run:
   ```bash
   docker compose up --build


