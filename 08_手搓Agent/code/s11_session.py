"""
s11_session.py - 8.11 会话持久化与多分支管理 (SessionStore 存档 / fork 分叉 / resume 恢复 / Markdown 导出)
"""
import os
import json
import uuid
import time
import shutil
from typing import List, Dict, Any, Optional

ROLE_ICONS = {"system": "🧠", "user": "👤", "assistant": "🤖", "tool": "🛠️"}


class SessionNode:
    """树状会话节点：一条完整消息历史，可被 fork 分叉出多个子分支"""
    def __init__(self, session_id=None, title="未命名会话", parent_id=None,
                 messages=None, created_at=None):
        self.session_id = session_id or uuid.uuid4().hex[:12]   # 🆔 全局唯一 ID
        self.title = title
        self.parent_id = parent_id                              # 🌳 父分支 ID，None 为根会话
        self.messages = messages if messages is not None else []
        self.created_at = created_at or time.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        """📦 序列化为 JSON 友好字典（存档）"""
        return {"session_id": self.session_id, "title": self.title,
                "parent_id": self.parent_id, "messages": self.messages,
                "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionNode":
        """♻️ 从字典还原节点（读档）"""
        return cls(session_id=data.get("session_id"), title=data.get("title", "未命名会话"),
                   parent_id=data.get("parent_id"), messages=data.get("messages", []),
                   created_at=data.get("created_at"))


class SessionStore:
    """🗄️ 会话仓库：以 JSON 文件持久化会话树，支持存档/读档/分叉/导出"""
    def __init__(self, storage_dir: str = "sessions"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)  # 📁 自动创建会话目录

    def _path(self, session_id: str) -> str:
        return os.path.join(self.storage_dir, f"{session_id}.json")

    def save(self, session: SessionNode) -> None:
        """💾 存档：把会话节点写回磁盘"""
        with open(self._path(session.session_id), "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def create_session(self, title: str, messages: Optional[List[Dict[str, Any]]] = None) -> str:
        """🆕 新建根会话并立即存档，返回 session_id"""
        session = SessionNode(title=title, messages=messages or [])
        self.save(session)
        return session.session_id

    def load(self, session_id: str) -> Optional[SessionNode]:
        """📂 读档：从磁盘恢复指定会话（断点续跑）"""
        path = self._path(session_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return SessionNode.from_dict(json.load(f))

    def list_sessions(self) -> List[Dict[str, Any]]:
        """📋 返回全部会话摘要（按创建时间倒序）"""
        summaries = []
        for fname in os.listdir(self.storage_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.storage_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                summaries.append({"session_id": data.get("session_id"),
                                  "title": data.get("title", "未命名会话"),
                                  "parent_id": data.get("parent_id"),
                                  "message_count": len(data.get("messages", [])),
                                  "created_at": data.get("created_at", "")})
            except Exception:
                continue  # 跳过损坏文件
        summaries.sort(key=lambda s: s["created_at"], reverse=True)
        return summaries

    def fork(self, parent_id: str, new_messages: Optional[List[Dict[str, Any]]] = None) -> SessionNode:
        """🌿 分叉：继承父会话历史并追加新消息，生成指向父节点的子分支"""
        parent = self.load(parent_id)
        if parent is None:
            raise ValueError(f"❌ 未找到父会话: {parent_id}，无法分叉！")
        child = SessionNode(title=f"{parent.title} · 分支", parent_id=parent.session_id,
                            messages=list(parent.messages) + (new_messages or []))
        self.save(child)
        return child

    def export_markdown(self, session_id: str) -> str:
        """📤 把该会话 messages 渲染成可读 Markdown 文本"""
        session = self.load(session_id)
        if session is None:
            return f"(未找到会话: {session_id})"
        lines = [f"# 🗂️ 会话导出：{session.title}", "",
                 f"- **会话 ID**：`{session.session_id}`",
                 f"- **父分支**：`{session.parent_id or '无（根会话）'}`",
                 f"- **创建时间**：{session.created_at}",
                 f"- **消息条数**：{len(session.messages)}", "", "---", ""]
        for i, msg in enumerate(session.messages, 1):
            role = msg.get("role", "unknown")
            lines += [f"### {i}. {ROLE_ICONS.get(role, '📄')} `{role}`", "",
                      str(msg.get("content", "")), ""]
        return "\n".join(lines)

    def delete(self, session_id: str) -> bool:
        """🗑️ 删除指定会话文件"""
        path = self._path(session_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


def demo_tree_branching(store: SessionStore) -> Dict[str, Any]:
    """🎬 演示：创建主会话 → 模拟对话 → 分叉 2 个方案 → 恢复其一 → 导出 Markdown"""
    main_id = store.create_session("修复登录服务内存泄漏", [
        {"role": "system", "content": "你是一名资深 Python 后端工程师，负责诊断并修复 Web 服务内存泄漏。"},
        {"role": "user", "content": "服务连续运行 3 天后，内存占用从 200MB 一路涨到 3GB，帮我定位根因。"},
    ])
    main = store.load(main_id)
    main.messages.append({"role": "assistant", "content": "已初步检查日志：怀疑全局缓存未清理 + 长连接未释放，先深入阅读代码确认。"})
    main.messages.append({"role": "user", "content": "我怀疑是 event_listener 注册表无限增长，帮忙重点排查。"})
    main.messages.append({"role": "assistant", "content": "已 grep 全局注册表，定位到 cache_store 与 ws_pool 两处高度可疑的点。"})
    store.save(main)  # 💾 中途存档，随时可断点续跑

    branch_a = store.fork(main_id, [
        {"role": "assistant", "content": "方案 A：为 cache_store 增加 LRU 容量上限，并注册定时清理任务。"},
        {"role": "user", "content": "可以，按方案 A 继续实施。"},
    ])
    branch_b = store.fork(main_id, [
        {"role": "assistant", "content": "方案 B：改用 WeakValueDictionary 弱引用缓存，让 GC 自动回收。"},
        {"role": "user", "content": "先别改代码，我要先对比 A/B 两套方案的压测数据再拍板。"},
    ])

    resumed = store.load(branch_b.session_id)  # 📂 恢复分支 B（断点续跑）
    resumed.messages.append({"role": "user", "content": "压测完成：方案 B 峰值内存更低、吞吐更稳，决定采用方案 B。"})
    resumed.messages.append({"role": "assistant", "content": "✅ 已按弱引用方案完成重构，内存曲线回归平稳，问题闭环。"})
    store.save(resumed)

    return {"main_id": main_id, "branch_a_id": branch_a.session_id,
            "branch_b_id": branch_b.session_id,
            "export_md": store.export_markdown(resumed.session_id)}


if __name__ == "__main__":
    # 🧪 纯本地自测：不依赖网络与 API Key
    tmp_dir = "sessions_demo"
    store = SessionStore(storage_dir=tmp_dir)
    print("=" * 64 + "\n🧪 8.11 会话持久化与多分支管理 自测\n" + "=" * 64)

    result = demo_tree_branching(store)
    print("\n📚 会话摘要列表（list_sessions）：")
    for s in store.list_sessions():
        parent = s["parent_id"] or "根会话"
        print(f"  - [{s['title']}] id={s['session_id']} 父={parent} 消息数={s['message_count']}")

    print("\n🗂️ 恢复分支 B 导出的 Markdown 预览：\n")
    print(result["export_md"][:500] + "\n...")

    assert store.load(result["main_id"]) and store.load(result["branch_a_id"]), "❌ 读档/分叉失败"
    assert store.delete(result["branch_a_id"]) and store.load(result["branch_a_id"]) is None, "❌ 删除失败"

    print("✅ 读档 / 分叉 / 删除 校验全部通过！")
    shutil.rmtree(tmp_dir, ignore_errors=True)  # 🧹 清理临时会话目录
    print("🎉 自测完成，临时会话目录已清理。")
