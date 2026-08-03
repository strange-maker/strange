"""Remove invalid CSCEC leadership tokens created by the legacy parser.

Revision ID: 0004_cscec_event_quality
Revises: 0003_cscec_monitoring
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_cscec_event_quality"
down_revision = "0003_cscec_monitoring"
branch_labels = None
depends_on = None


COMMON_SURNAMES = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻"
    "柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤"
    "滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛"
    "禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危"
    "江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫房裘缪干解应宗"
    "丁宣贲邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊甄曲封芮储靳汲邴糜松"
    "井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符"
    "刘景詹束龙叶幸司韶黎乔苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮"
    "牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎戈廖庾终"
    "暨居衡步都耿满弘匡国文寇广禄阙东欧利蔚越隆师巩厍聂晁勾敖融冷訾辛阚那"
    "简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
COMPOUND_SURNAMES = (
    "欧阳",
    "司马",
    "上官",
    "诸葛",
    "东方",
    "皇甫",
    "尉迟",
    "公孙",
    "慕容",
    "长孙",
    "宇文",
    "司徒",
    "司空",
    "夏侯",
)
STOPWORDS = (
    "股东",
    "如有",
    "任何",
    "内容",
    "不存在",
    "不得",
    "公司",
    "本次",
    "会议",
    "董事",
    "监事",
    "人员",
    "职务",
    "候选",
    "委员",
    "管理",
    "高级",
    "独立",
    "相关",
    "以上",
    "以下",
    "中国",
    "建筑",
    "集团",
    "有限",
)


def _valid_name(value: str | None) -> bool:
    if not value:
        return False
    name = "".join(value.split()).strip("·")
    if not 2 <= len(name.replace("·", "")) <= 8:
        return False
    if not all("\u4e00" <= char <= "\u9fff" or char == "·" for char in name):
        return False
    if any(word in name for word in STOPWORDS):
        return False
    first_part = name.split("·", 1)[0]
    return first_part.startswith(COMPOUND_SURNAMES) or first_part[0] in COMMON_SURNAMES


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cscec_leadership_events" not in inspector.get_table_names():
        return
    rows = bind.execute(
        sa.text("SELECT id, person_name FROM cscec_leadership_events")
    ).mappings()
    invalid_ids = [row["id"] for row in rows if not _valid_name(row["person_name"])]
    if invalid_ids:
        delete = sa.text(
            "DELETE FROM cscec_leadership_events WHERE id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True))
        bind.execute(delete, {"ids": invalid_ids})


def downgrade() -> None:
    # Deleted parser artifacts are intentionally not recreated.
    pass
