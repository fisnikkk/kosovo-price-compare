from alembic import op
import sqlalchemy as sa

revision = '716dd556fa0e'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('store_items', sa.Column('brand', sa.String(length=120), nullable=True))
    op.add_column('store_items', sa.Column('category', sa.String(length=120), nullable=True))

def downgrade():
    op.drop_column('store_items', 'category')
    op.drop_column('store_items', 'brand')
