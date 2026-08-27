"""
s09_memory_and_skills.py - 8.9 记忆系统与技能挂载 (Memory 持久化与 SKILL.md 动态挂载)
"""
import os
import json
import glob
from typing import Dict, List, Optional

class MemoryStore:
    """🧠 本地 JSON 持久化长期记忆仓库（跨会话偏好沉淀）"""
    def __init__(self, storage_file: str = "agent_memory.json"):
        self.storage_file = storage_file
        self.memories: Dict[str, str] = self._load()

    def _load(self) -> Dict[str, str]:
        """📂 从磁盘加载记忆（文件缺失或损坏时容错返回空字典）"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        """💾 将记忆写回磁盘 JSON 文件"""
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"写入记忆文件失败: {e}")

    def remember(self, key: str, value: str):
        """✍️ 记录一条长期偏好或知识（自动落盘）"""
        self.memories[key] = value
        self.save()

    def recall(self, query_keyword: Optional[str] = None) -> str:
        """🔍 检索相关记忆（支持关键词过滤，无则返回全部）"""
        if not self.memories:
            return "(暂无长期记忆沉淀)"
        if not query_keyword:
            # 返回所有记忆条目
            return "\n".join([f"- [{k}]: {v}" for k, v in self.memories.items()])
        
        matches = [
            f"- [{k}]: {v}" for k, v in self.memories.items()
            if query_keyword.lower() in k.lower() or query_keyword.lower() in v.lower()
        ]
        return "\n".join(matches) if matches else f"(未找到与 [{query_keyword}] 相关的长期记忆)"

class SkillLoader:
    """🎒 动态技能安装包加载器 (扫描并挂载 ./skills/*.md)"""
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self.loaded_skills: Dict[str, str] = {}
        self.reload_skills()

    def reload_skills(self):
        """🔄 扫描并加载目录下的所有 Markdown 技能包"""
        self.loaded_skills.clear()
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)
            
        md_files = glob.glob(os.path.join(self.skills_dir, "*.md"))
        for path in md_files:
            skill_name = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.loaded_skills[skill_name] = f.read().strip()
            except Exception as e:
                print(f"读取技能包 [{path}] 失败: {e}")

    def list_skills(self) -> List[str]:
        """📋 返回所有已加载技能名列表"""
        return list(self.loaded_skills.keys())

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """📄 按技能名获取完整技能内容"""
        return self.loaded_skills.get(skill_name)

    def assemble_system_prompt(self, base_prompt: str, active_skills: List[str], memory_store: Optional[MemoryStore] = None) -> str:
        """🧬 组装注入了记忆和专业技能的增强型系统提示词"""
        prompt = base_prompt + "\n\n"
        
        # 1. 注入长期记忆
        if memory_store:
            mem_text = memory_store.recall()
            prompt += f"🧠 【长期用户偏好与项目规则记忆】:\n{mem_text}\n\n"
            
        # 2. 注入勾选的专业技能
        if active_skills:
            prompt += "🛠️ 【挂载的专业技能插件包 (Skills)】:\n"
            for s_name in active_skills:
                content = self.get_skill_content(s_name)
                if content:
                    prompt += f"\n--- 技能插件: {s_name} ---\n{content}\n"
                    
        return prompt

if __name__ == "__main__":
    mem = MemoryStore("temp_memory.json")
    mem.remember("代码风格偏好", "始终使用 Python 类型注解，注释用中文，遵循 PEP8 规范")
    mem.remember("数据库配置", "生产数据库使用 PostgreSQL 16，本地开发用 SQLite3")

    print("--- 1. 记忆写入与全量召回自测 ---")
    print(mem.recall())

    print("\n--- 2. 关键词过滤召回自测 ---")
    print("检索 '数据库':", mem.recall("数据库"))
    print("检索 '不存在的词':", mem.recall("不存在的词"))

    print("\n--- 3. 跨实例持久化自测 (重新加载磁盘) ---")
    mem2 = MemoryStore("temp_memory.json")
    print("重新加载后条目数:", len(mem2.memories))

    print("\n--- 4. 记忆文件损坏容错自测 ---")
    with open("temp_memory.json", "w", encoding="utf-8") as f:
        f.write("{ 这不是合法 JSON")
    print("损坏文件加载结果:", MemoryStore("temp_memory.json").memories)

    print("\n--- 5. 技能挂载与 Prompt 组装自测 ---")
    loader = SkillLoader()
    print("当前已扫描技能包:", loader.list_skills())
    full_prompt = loader.assemble_system_prompt("你是一个全栈工程师。", loader.list_skills(), mem)
    print("组装后的 Prompt 片段:\n", full_prompt[:200])

    if os.path.exists("temp_memory.json"):
        os.remove("temp_memory.json")
