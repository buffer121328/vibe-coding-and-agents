"""一次性数据脚本：灌种子、抓素材、城市名对照。

这些脚本**运行期不参与**，只在开发 / 部署时手动跑一次：

    uv run python -m infra.scripts.seed_cn_data     # 重建国内数据集（机场/航班/酒店/租车/景点/旅客）
    uv run python -m infra.scripts.fetch_assets     # 抓城市照片与底图，并生成署名清单
    uv run python -m infra.scripts.location_trans   # 单独跑：中文城市名 → 库里存的英文名

`location_trans` 例外：它同时被业务工具 import（模型说「成都」，库里存 `Chengdu`），
所以它是这一层里唯一有运行期调用方的脚本——放在 scripts/ 只是因为它的另一半身份是
「数据清洗小工具」。
"""
