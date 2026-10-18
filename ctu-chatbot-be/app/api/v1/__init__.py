from fastapi import APIRouter

from app.api.v1 import admin_documents, admin_feedback, admin_stats, admin_users, shares, auth, conversations, documents, donate, feedback, files, health, suggestions, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin_feedback.router)
api_router.include_router(admin_documents.router)
api_router.include_router(admin_stats.router)
api_router.include_router(admin_users.router)
api_router.include_router(donate.router)
api_router.include_router(donate.admin_router)
api_router.include_router(users.router)
api_router.include_router(files.router)
api_router.include_router(conversations.router)
api_router.include_router(shares.owner_router)
api_router.include_router(shares.router)
api_router.include_router(shares.public_router)
api_router.include_router(feedback.router)
api_router.include_router(documents.router)
api_router.include_router(suggestions.router)
