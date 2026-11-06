"""Shared CLI/Manager parameter definitions; standard library dependencies only."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import Any


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-c", "--config", type=str, help="运行配置路径", default="config/test")
    parser.add_argument("-l", "--loop", action="store_true", help="是否循环", default=False)
    parser.add_argument("--log", action="store_true", help="是否打印日志", default=False)
    parser.add_argument("-s", "--screenshots", action="store_true", help="截图模式", default=False)
    parser.add_argument("--scale", help="与配置所用分辨率的缩放值", default=1.0, type=float)
    parser.add_argument("--scale_image", action="store_true", help="缩放时是否缩放用到的截图", default=False)
    parser.add_argument("--offset", help="搜索时需要的偏移值", default="0;0", type=str)
    parser.add_argument("--run_duration", help="运行时长（分钟）：基础值[;随机增量]，需同时设置 --pause_duration", default="", type=str)
    parser.add_argument("--pause_duration", help="暂停时长（分钟）：基础值[;随机增量]，仅在 main.csv 第一条节点前暂停", default="", type=str)
    parser.add_argument("-t", "--title", help="目标窗口名称,指定后程序运行在后台窗口模式", default=None, type=str)
    parser.add_argument("-m", "--multi_window", action="store_true", help="后台窗口多窗口控件模式", default=False)
    parser.add_argument("--click_move_cursor", action="store_true", help="后台 click 时临时移动真实鼠标到目标点后快速恢复", default=False)
    parser.add_argument("--process", action="store_true", help="获取所有可见窗口名称", default=False)


def default_run_parameters() -> dict[str, Any]:
    parser = argparse.ArgumentParser(add_help=False)
    add_run_arguments(parser)
    return vars(parser.parse_args([]))


def export_run_parameters(args: argparse.Namespace | Mapping[str, Any]) -> dict[str, Any]:
    """Export public parameters, filling missing fields from shared defaults."""
    values = vars(args) if isinstance(args, argparse.Namespace) else args
    return {key: values.get(key, default) for key, default in default_run_parameters().items()}
