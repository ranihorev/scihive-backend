"""empty message

Revision ID: 6781303715b5
Revises: bd467b55c522
Create Date: 2020-10-12 07:54:23.265287

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6781303715b5'
down_revision = 'bd467b55c522'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('paper', sa.Column('token', sa.String(), nullable=True))
    op.add_column('paper_version', sa.Column('token', sa.String(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('paper_version', 'token')
    op.drop_column('paper', 'token')
    # ### end Alembic commands ###
