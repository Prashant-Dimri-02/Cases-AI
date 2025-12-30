# app/api/api_router.py
from fastapi import APIRouter
from app.api.v1 import auth, users, cases, files, qa

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/v1/users", tags=["users"])
api_router.include_router(cases.router, prefix="/v1/cases", tags=["cases"])
api_router.include_router(files.router, prefix="/v1/files", tags=["files"])
api_router.include_router(qa.router, prefix="/v1/qa", tags=["qa"])
