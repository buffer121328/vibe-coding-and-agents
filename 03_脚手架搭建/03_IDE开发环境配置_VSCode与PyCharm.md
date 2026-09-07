# 3.3 开发环境配置：编辑器、解释器与项目依赖

给每道菜准备独立的配料盒，做饭时就不容易拿错材料。项目环境也需要这种区分：编辑器负责打开和修改代码，解释器负责执行代码，依赖包提供额外功能。三者装在电脑上，不代表已经正确连接。

这一节的目标是让你能够运行一个文件，并知道它究竟由哪一个 Python 环境执行。

## 编辑器怎样选

[VS Code](https://code.visualstudio.com)适合通过扩展配置不同语言；[PyCharm](https://www.jetbrains.com/pycharm/)围绕 Python 项目提供集成开发功能。若已经在使用 [Cursor](https://cursor.com) 或 [Trae](https://www.trae.ai)，也可以先在现有工具中完成练习，无需重复安装所有编辑器。

<!-- 图表源文件：img/diagrams/03-diagram-01.mmd；视觉风格：Vercel 黑白 -->
<p align="center">
  <a href="img/diagrams/03-diagram-01.svg">
    <img src="img/diagrams/03-diagram-01.svg" alt="本节概念与流程示意图 1" width="960">
  </a>
</p>

选择时先看三个问题：是否方便打开完整项目，能否选择解释器，能否查看终端与错误信息。具体免费功能、账户要求和界面位置，以当前版本为准。

## 先安装 Python，再配置编辑器

从 [Python 官网](https://www.python.org/downloads/)安装适合系统和项目要求的版本。打开新终端检查：

macOS / Linux：

```bash
python3 --version
```

Windows：

```powershell
py --version
```

能显示版本说明命令可用，但仍要确认符合项目要求。遇到“找不到命令”，先检查是否安装完成、是否需要重新打开终端，以及系统路径设置，不要急着修改项目代码。

## VS Code 的基础扩展

从扩展市场按名称和发布者核对安装。可以先使用微软的 [Python 扩展](https://marketplace.visualstudio.com/items?itemName=ms-python.python)与 [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)。需要中文界面时，再安装 [简体中文语言包](https://marketplace.visualstudio.com/items?itemName=MS-CEINTL.vscode-language-pack-zh-hans)。

其他扩展按需要添加。比如 [Prettier](https://prettier.io/docs/)主要服务于它支持的前端与文档格式，不能默认当作 Python 格式化工具。编辑器里没有红线，也不能证明程序运行正确。

## 为每个项目建立虚拟环境

虚拟环境主要隔离依赖包，避免项目 A 升级一个库后影响项目 B。它不像虚拟机那样提供独立操作系统，也不会阻止程序读写电脑上的其他文件。

<!-- 图表源文件：img/diagrams/03-diagram-02.mmd；视觉风格：Notion 简洁 -->
<p align="center">
  <a href="img/diagrams/03-diagram-02.svg">
    <img src="img/diagrams/03-diagram-02.svg" alt="本节概念与流程示意图 2" width="960">
  </a>
</p>

先打开自己的项目文件夹，在该目录的终端中创建 `.venv`。

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install requests python-dotenv
```

Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install requests python-dotenv
```

如果 PowerShell 不允许执行激活脚本，可以直接使用虚拟环境中的解释器，不必为了练习放宽全局脚本策略：

```powershell
.\.venv\Scripts\python.exe -m pip install requests python-dotenv
```

这里使用 `python -m pip`，是为了让安装工具与当前 Python 对应。[requests](https://requests.readthedocs.io/)用于 HTTP 请求，[python-dotenv](https://github.com/theskumar/python-dotenv)用于加载本地环境配置。

## 确认编辑器和终端使用同一个环境

在 VS Code 的命令面板搜索 `Python: Select Interpreter`，选择项目 `.venv` 中的解释器；PyCharm 则在项目解释器设置中选择对应环境。VS Code 的具体说明可查[官方环境文档](https://code.visualstudio.com/docs/python/environments)。

创建 `check_env.py`：

```python
import sys
from pathlib import Path

print("解释器：", sys.executable)
print("Python 版本：", sys.version.split()[0])
print("工作目录：", Path.cwd())
```

在编辑器中运行一次，再在终端运行 `python check_env.py`。解释器都指向当前项目的 `.venv`，说明主要设置一致。工作目录也要留意：相对路径从工作目录开始寻找，不一定从脚本所在目录开始。

## 可选：使用 uv 管理项目

[uv](https://docs.astral.sh/uv/)可以管理 Python、环境和依赖。已经用 `venv` 完成练习的读者不必立刻迁移；准备使用 uv 时，先按官方安装说明安装，然后在一个新的练习目录中执行：

```bash
uv init
uv add requests python-dotenv
uv run python -c "import sys; print(sys.executable)"
```

在这套[项目工作流](https://docs.astral.sh/uv/guides/projects/)里，`pyproject.toml` 描述依赖要求，`uv.lock` 记录解析结果，`uv run` 在项目环境中运行命令。不要同时随意混用多个依赖管理方式，否则实际环境可能与记录不一致。

## 依赖怎样交给别人复现

虚拟环境目录不适合直接复制到别人的电脑。应保存依赖说明，让对方在自己的环境重新安装。使用 uv 项目时，可以根据项目文件执行 `uv sync`；使用传统方式时，则按照项目维护的 `requirements.txt` 安装。

不要把整个个人电脑的包列表当作项目依赖。如果确实通过 `pip freeze` 生成清单，应确保是在这个项目的干净虚拟环境中，并检查是否混入无关包或带凭据的私有地址。

## 常见问题排查

| 现象 | 常见原因 | 检查方法 |
| :--- | :--- | :--- |
| 已安装包，却提示找不到模块 | 安装与运行用了不同解释器 | 比较 `sys.executable` 与安装位置 |
| 终端能跑，编辑器不能 | 编辑器选错解释器 | 重新选择 `.venv` 环境 |
| 相对路径找不到文件 | 当前工作目录不对 | 输出 `Path.cwd()` |
| 刚升级就报错 | 依赖版本变化或接口调整 | 对照项目版本记录与迁移说明 |
| 终端关闭后服务停止 | 服务就是该终端启动的进程 | 按项目部署方式管理长期进程 |

完成后应能解释三件事：代码由谁执行，依赖装在哪里，文件从哪个目录读取。这比把所有扩展都装齐更重要。
