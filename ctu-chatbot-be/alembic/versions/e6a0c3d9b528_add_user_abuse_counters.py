"""add users.spam_count and users.profanity_count

Revision ID: e6a0c3d9b528
Revises: d5f9b2c8a417
Create Date: 2026-10-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a0c3d9b528'
down_revision: Union[str, Sequence[str], None] = 'd5f9b2c8a417'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('spam_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('profanity_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'profanity_count')
    op.drop_column('users', 'spam_count')
