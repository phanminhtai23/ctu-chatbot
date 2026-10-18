"""add feedback.question / feedback.answer snapshot

Revision ID: a1c7e4d9b3f6
Revises: e5f1c3a8d902
Create Date: 2026-10-18 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7e4d9b3f6'
down_revision: Union[str, Sequence[str], None] = 'e5f1c3a8d902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('feedback', sa.Column('question', sa.Text(), nullable=True))
    op.add_column('feedback', sa.Column('answer', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('feedback', 'answer')
    op.drop_column('feedback', 'question')
