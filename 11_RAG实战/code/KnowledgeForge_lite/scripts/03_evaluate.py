"""03_evaluate.py —— 门禁层：行为对不对、期望文档召回了没有。

用法：python scripts/03_evaluate.py

这一步**不调 Ragas**。改完切块 / 检索 / 闸门，应该跑的是它——快，而且不把黄金题
写进会话柜。裁判三指标（Faithfulness / ContextRecall / AnswerRelevancy）走
``04_ragas_eval.py``，那条要请阅卷模型，八条黄金集可能要几十分钟。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.answer.evaluation import run_gate

if __name__ == "__main__":
    raise SystemExit(0 if run_gate() else 1)
