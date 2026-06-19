"""Add frame_interval_seconds, analysis_prompt, progress to detection_records.

Revision ID: 0001
Revises: None
Create Date: 2026-06-03
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('detection_records', sa.Column(
        'frame_interval_seconds', sa.Integer(), nullable=False,
        server_default='5'
    ))
    op.add_column('detection_records', sa.Column(
        'analysis_prompt', sa.Text(), nullable=True
    ))
    op.add_column('detection_records', sa.Column(
        'progress', sa.Integer(), nullable=False,
        server_default='0'
    ))


def downgrade() -> None:
    op.drop_column('detection_records', 'progress')
    op.drop_column('detection_records', 'analysis_prompt')
    op.drop_column('detection_records', 'frame_interval_seconds')
