"""04_ragas_eval.py —— 体检层：Ragas 0.4 三指标。门禁层请跑 03_evaluate.py。

Ragas 0.4 官方写法：``ragas.metrics.collections`` 的三个指标 + ``llm_factory`` /
``embedding_factory``，逐条 ``ascore``。旧的 ``EvaluationDataset`` 与
``from ragas.metrics import faithfulness`` 单例已被官方弃用（v1.0 移除）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.answer.evaluate import evaluate

if __name__ == "__main__":
    evaluate()
