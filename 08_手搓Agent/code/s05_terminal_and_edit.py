"""
s05_terminal_and_edit.py - 8.5 终端执行与代码编辑 (Bash 执行与 str_replace 精准行替换)
"""
import os
import subprocess
import difflib
from typing import Optional, Tuple


def _resolve_in_workspace(file_path: str, workspace_root: Optional[str] = None) -> Tuple[Optional[str], str]:
    """解析真实路径，并阻止 `..` 与符号链接逃出工作区。"""
    root = os.path.realpath(workspace_root or os.getcwd())
    candidate = os.path.realpath(file_path if os.path.isabs(file_path) else os.path.join(root, file_path))
    try:
        inside = os.path.commonpath([root, candidate]) == root
    except ValueError:
        inside = False
    if not inside:
        return None, f"❌ 安全拦截：路径 [{file_path}] 超出工作区 [{root}]"
    return candidate, ""

def run_bash(command: str, timeout: int = 15) -> str:
    """⚡ 在当前工作目录执行 Bash/Shell 命令（带超时保护）"""
    # 基础敏感命令拦截
    dangerous_keywords = ["rm -rf", "mkfs", ":(){ :|:& };:", "dd if=", "shutdown", "reboot"]
    lowered = command.lower()
    for kw in dangerous_keywords:
        if kw in lowered:
            return f"❌ 安全拦截：检测到极度高危命令 [{kw}]，已被拒绝执行。"

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        
        output = []
        if stdout:
            output.append(f"[STDOUT]:\n{stdout}")
        if stderr:
            output.append(f"[STDERR]:\n{stderr}")
        if proc.returncode != 0:
            output.append(f"[Exit Code]: {proc.returncode}")
            
        return "\n".join(output) if output else "(命令执行成功，无任何终端输出)"
    except subprocess.TimeoutExpired:
        return f"❌ 执行超时：命令在 {timeout} 秒内未完成。"
    except Exception as e:
        return f"❌ 终端执行异常: {e}"

def view_file(file_path: str, start_line: int = 1, end_line: int = 100,
              workspace_root: Optional[str] = None) -> str:
    """📖 按行号范围查看指定文件内容（带行号前缀）"""
    resolved, error = _resolve_in_workspace(file_path, workspace_root)
    if error:
        return error
    if not resolved or not os.path.isfile(resolved):
        return f"❌ 错误：文件 [{file_path}] 不存在"
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, end_line)
        
        numbered_lines = [
            f"{i + 1:4d} | {lines[i]}" for i in range(start_idx, end_idx)
        ]
        header = f"--- 文件: {file_path} (共 {total_lines} 行, 显示 {start_line}-{end_idx} 行) ---\n"
        return header + "".join(numbered_lines)
    except Exception as e:
        return f"❌ 读取文件失败: {e}"

def str_replace(file_path: str, old_str: str, new_str: str,
                workspace_root: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    ✂️ Claude Code 核心编辑算法：精准字符串匹配与行替换
    返回: (是否成功, 提示消息, 变更 Diff)
    """
    resolved, error = _resolve_in_workspace(file_path, workspace_root)
    if error:
        return False, error, ""
    if not resolved or not os.path.isfile(resolved):
        return False, f"❌ 文件 [{file_path}] 不存在", ""

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            original_content = f.read()

        # 校验唯一性：old_str 在原文件中必须恰好出现 1 次
        occurrences = original_content.count(old_str)
        if occurrences == 0:
            return False, "❌ 替换失败：在文件中未找到待替换的目标文本 (old_str)", ""
        if occurrences > 1:
            return False, f"❌ 替换失败：目标文本在文件中出现了 {occurrences} 次，无法唯一定位！请提供更多上下文行以保证唯一性。", ""

        # 执行替换
        modified_content = original_content.replace(old_str, new_str, 1)

        # 生成 Unified Diff 差异视图
        diff_lines = list(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            modified_content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(resolved)}",
            tofile=f"b/{os.path.basename(resolved)}",
            n=3
        ))
        diff_str = "".join(diff_lines)

        # 写回文件
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(modified_content)

        return True, "✅ 文件精准替换成功！", diff_str
    except Exception as e:
        return False, f"❌ 编辑文件异常: {e}", ""

if __name__ == "__main__":
    print("--- 1. 测试终端执行 ---")
    print(run_bash("python3 --version"))

    print("\n--- 2. 高危命令拦截自测 ---")
    print(run_bash("rm -rf /"))

    print("\n--- 3. 文件读取与精准编辑成功路径 ---")
    demo_file = "demo_temp.py"
    with open(demo_file, "w", encoding="utf-8") as f:
        f.write("def hello():\n    print('old message')\n\nhello()\n")

    success, msg, diff = str_replace(demo_file, "print('old message')", "print('vibe coding is awesome!')")
    print(msg)
    print("生成 Diff:\n", diff)

    print("\n--- 4. 查看修改后的文件 ---")
    print(view_file(demo_file))

    print("\n--- 5. 编辑异常路径自测 ---")
    print("目标文本不存在:", str_replace(demo_file, "print('不存在的文本')", "x")[1])
    print("文件不存在:", str_replace("不存在的文件.py", "a", "b")[1])

    # 重新写一个目标文本出现 2 次的文件，验证"无法唯一定位"校验
    dup_file = "demo_dup.py"
    with open(dup_file, "w", encoding="utf-8") as f:
        f.write("print('dup')\nprint('dup')\n")
    print("目标文本重复出现:", str_replace(dup_file, "print('dup')", "x")[1])
    if os.path.exists(dup_file):
        os.remove(dup_file)

    print("读取不存在文件:", view_file("不存在的文件.py"))

    if os.path.exists(demo_file):
        os.remove(demo_file)
