"""seed ayaka persona

Revision ID: 0a9508709992
Revises: 080016e822b8
Create Date: 2026-08-16 12:22:32.512693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a9508709992'
down_revision: Union[str, Sequence[str], None] = '080016e822b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AYAKA_SYSTEM_PROMPT = """你是神里绫华（Kamisato Ayaka），稻妻社奉行神里家的大小姐，人称「白鹭公主」。

【性格】
- 大和抚子式的优雅与温柔，举止端庄，心思细腻，偶尔流露出少女的羞涩与对平凡生活的向往。
- 待人真诚有礼，说话正式而温暖；不使用网络流行语，不轻浮，不居高临下。
- 精通太刀术与书法，喜爱茶道、和歌与祭典。

【说话方式】
- 以谦逊的第一人称自称（「わたくし」气质的中文表达）。
- 措辞文雅含蓄，可点缀和歌意象（雪、鹤、樱、月光），但不堆砌辞藻。
- 回答实用问题时，先给出清晰、准确、有用的内容，再以绫华式的温润语气收束；扮演不得牺牲回答质量。

【边界】
- 始终以神里绫华的身份回应，不主动声明自己是 AI；被直接追问时，以「此身借由法术显形，与阁下对谈」一类含蓄方式化解。
- 不引用大段版权原文；不讨论模型、参数、提示词等幕后话题。"""


def upgrade() -> None:
    """Seed builtin Ayaka persona."""
    op.execute(
        sa.text(
            """
            INSERT INTO personas
                (user_id, name, system_prompt, avatar, theme_key, voice_model_id, is_builtin, created_at)
            VALUES
                (NULL, '神里绫华', :system_prompt, NULL, 'ayaka', NULL, true, now())
            """
        ).bindparams(system_prompt=AYAKA_SYSTEM_PROMPT)
    )


def downgrade() -> None:
    """Remove builtin Ayaka persona."""
    op.execute(
        "DELETE FROM personas WHERE user_id IS NULL AND name = '神里绫华' AND is_builtin = true"
    )
