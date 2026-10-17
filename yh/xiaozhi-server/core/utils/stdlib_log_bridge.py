#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stdlib logging → loguru 桥接

项目日志走 loguru（data/app.log），而 root logger 无 handler 且
effective level=30（WARNING），导致使用 ``logging.getLogger(__name__)``
的模块 INFO 日志全部丢失（壁纸链路曾因此无任何可观测日志）。

用法（模块级调用一次即可）::

    from core.utils.stdlib_log_bridge import install_stdlib_log_bridge
    install_stdlib_log_bridge(__name__)

与 ``core/services/push_scheduler.py`` 内的桥接实现一致（InterceptHandler 标准写法），
抽出为公共工具避免各模块重复粘贴。
"""
import logging

_installed = set()


def install_stdlib_log_bridge(name: str, level: int = logging.INFO) -> None:
    """把 stdlib logger ``name`` 的输出转发到 loguru，并放开到 ``level``。

    幂等：同一 logger 重复调用不会叠加 handler。
    loguru 不可用时静默跳过（保持 stdlib 原状，WARNING+ 仍可经 lastResort 输出）。
    """
    if not name or name in _installed:
        return
    try:
        from loguru import logger as _loguru_logger

        class _InterceptHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    log_level = _loguru_logger.level(record.levelname).name
                except ValueError:
                    log_level = record.levelno
                frame, depth = logging.currentframe(), 2
                while frame and frame.f_code.co_filename == logging.__file__:
                    frame = frame.f_back
                    depth += 1
                _loguru_logger.opt(
                    depth=depth, exception=record.exc_info
                ).log(log_level, record.getMessage())

        stdlib_logger = logging.getLogger(name)
        stdlib_logger.addHandler(_InterceptHandler())
        stdlib_logger.setLevel(level)
        # 阻断向 root 传播：root 上另有一个默认格式 handler（落 stderr→app.log），
        # 不阻断会出现「loguru 一行 + 默认格式一行」的重复日志。
        stdlib_logger.propagate = False
        _installed.add(name)
    except Exception:  # pragma: no cover - loguru 缺失时降级
        pass
