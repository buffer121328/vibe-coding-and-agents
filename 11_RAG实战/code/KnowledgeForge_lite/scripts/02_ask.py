"""02_ask.py —— 第二步：命令行问答，直观感受三路检索 + 工牌 ACL + 四道闸门。

用法：python scripts/02_ask.py "你的问题" [工牌]
工牌：it_staff（默认）/ hr_staff / finance_head / admin
推荐试这几类问题：
  1. 库内事实   —— "去上海出差住一晚能报多少？"          → 带引用作答
  2. 库内操作   —— "打印机显示 E3 怎么处理？"           → 带引用作答（IT 可见）
  3. 口语含糊   —— "出差回来晚了一天，钱最晚啥时候能到手？" → 11.6 改写后仍应命中报销时限
  4. 库外问题   —— "公司年终奖一般发几个月？"           → 拒答（资料不足；投毒网页已被隔离）
  5. 权限对照   —— "P6 薪酬带宽是多少？"
                   it_staff / hr_staff → 拒答（密级文档被工牌裁掉）
                   finance_head / admin → 应能引用《财务薪酬密级》
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge_lite.answer.agent import ask
from forge_lite.core.identity import resolve_actor

if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "去上海出差住一晚能报多少？"
    user_id = sys.argv[2] if len(sys.argv) > 2 else None
    actor = resolve_actor(user_id)
    print(f"❓ {question}")
    print(f"👤 {actor.display_name}（{actor.user_id} / {actor.role} / {actor.department}）\n")
    result = ask(question, user_id=actor.user_id)
    print(f"💡 {result['answer']}\n")
    print(f"检索查询：{result.get('queries') or [question]}")
    print(f"融合路由：{result.get('routes') or '（空）'}")
    print(f"出处：{[c['doc_id'] for c in result.get('citations', [])] or '（无）'}")
    print(f"状态：{result['status']}" + (f"（⚠️ {result['warn']}）" if result.get("warn") else ""))
    print("\n--- 完整结构化输出 ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))
