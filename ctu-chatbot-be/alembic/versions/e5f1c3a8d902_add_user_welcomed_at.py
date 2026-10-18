"""add users.welcomed_at

Revision ID: e5f1c3a8d902
Revises: d4e9b2a7c611
Create Date: 2026-10-18 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f1c3a8d902'
down_revision: Union[str, Sequence[str], None] = 'd4e9b2a7c611'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('welcomed_at', sa.DateTime(timezone=True), nullable=True))
    # Tài khoản đã có từ trước không phải "người dùng mới": đánh dấu đã chào mừng để không hiện hộp thoại pháo hoa.
    op.execute("UPDATE users SET welcomed_at = created_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'welcomed_at')
