"""Create the complete initial ProofStack schema.

Revision ID: 0001_initial
Revises: None
"""

from alembic import op
from proofstack_api import models as proofstack_models

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    proofstack_models.Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    proofstack_models.Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
