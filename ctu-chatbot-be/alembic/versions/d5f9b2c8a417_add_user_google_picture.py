"""add users.google_picture (original Google avatar kept as the default)

Revision ID: d5f9b2c8a417
Revises: c4e8a1d7f203
Create Date: 2026-10-18 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5f9b2c8a417'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1d7f203'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('google_picture', sa.String(length=500), nullable=True))
    # Tài khoản đang dùng ảnh Google làm ảnh đại diện: ghi nhớ nó là "ảnh gốc" để nút "Mặc định" quay về được.
    op.execute(
        "UPDATE users SET google_picture = avatar_url, avatar_url = NULL "
        "WHERE avatar_url LIKE 'https://%googleusercontent.com/%'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE users SET avatar_url = google_picture WHERE avatar_url IS NULL AND google_picture IS NOT NULL")
    op.drop_column('users', 'google_picture')
