"""日志：全项目统一的 loguru 配置。

为什么单独一层：日志是「换个环境就得换」的东西（本地要看屏、线上要落文件），
所以它不该散在每个模块里自己配一遍。全项目只有这一处配置，别处一律 `from infra.logging import log`。

用法：
    from infra.logging import log
    log.info("启动完成")
    log.exception(exc)      # 记异常连带栈
"""
from __future__ import annotations

import os
import sys

from loguru import logger

from infra.paths import LOG_DIR

# 日志目录跟着仓库走：<项目根>/logs（不存在就建）
os.makedirs(LOG_DIR, exist_ok=True)


class MyLogger:
    """把 loguru 收成一个统一出口。

    只在模块末尾实例化一次；类本身留着是为了以后要挂第二个 handler（文件、JSON）时
    有地方加，不用去动每个调用点。
    """

    def __init__(self) -> None:
        """装配唯一的控制台 handler：时间 / 进程 / 线程 / 模块.函数:行 / 等级 / 内容。"""
        self.logger = logger
        self.logger.remove()          # 先清掉 loguru 自带的默认 handler，格式才由我们说了算
        self.logger.add(
            sys.stdout,
            level="DEBUG",
            format="<green>{time:YYYYMMDD HH:mm:ss}</green> | "
                   "{process.name} | "
                   "{thread.name} | "
                   "<cyan>{module}</cyan>.<cyan>{function}</cyan>"
                   ":<cyan>{line}</cyan> | "
                   "<level>{level}</level>: "
                   "<level>{message}</level>",
        )

    def get_logger(self):
        """返回配置好的 logger 对象（供模块级 `log = ...` 取用）。"""
        return self.logger


log = MyLogger().get_logger()
