"""
定时任务模型定义
支持 cron/interval/once 三种任务类型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class TaskType(Enum):
    """任务类型枚举"""
    CRON = "cron"          # cron表达式定时
    INTERVAL = "interval"  # 间隔重复
    ONCE = "once"          # 一次性定时


@dataclass
class ScheduleTask:
    """定时任务模型"""

    # 基本字段
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str = ""
    name: str = ""

    # 任务配置
    task_type: TaskType = TaskType.CRON
    cron_expr: str = ""           # cron表达式，如 "0 9 * * *"
    interval_seconds: int = 0     # 间隔秒数，用于INTERVAL类型
    run_at: Optional[datetime] = None  # 执行时间，用于ONCE类型

    # 内容配置
    content: str = ""             # 推送内容或模板
    content_type: str = "text"    # 内容类型：text/template/image

    # 状态字段
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 执行统计
    execution_count: int = 0
    failure_count: int = 0

    def update_next_run(self, next_run: datetime):
        """更新下次执行时间"""
        self.next_run = next_run
        self.updated_at = datetime.now()

    def record_run(self, success: bool = True):
        """记录执行结果"""
        self.last_run = datetime.now()
        self.execution_count += 1
        if not success:
            self.failure_count += 1
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "task_type": self.task_type.value,
            "cron_expr": self.cron_expr,
            "interval_seconds": self.interval_seconds,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "content": self.content,
            "content_type": self.content_type,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleTask":
        """从字典创建任务"""
        task = cls(
            id=data.get("id", uuid.uuid4().hex[:16]),
            user_id=data.get("user_id", ""),
            name=data.get("name", ""),
            task_type=TaskType(data.get("task_type", "cron")),
            cron_expr=data.get("cron_expr", ""),
            interval_seconds=data.get("interval_seconds", 0),
            run_at=datetime.fromisoformat(data["run_at"]) if data.get("run_at") else None,
            content=data.get("content", ""),
            content_type=data.get("content_type", "text"),
            enabled=data.get("enabled", True),
            last_run=datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None,
            next_run=datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            execution_count=data.get("execution_count", 0),
            failure_count=data.get("failure_count", 0),
        )
        return task

    def __repr__(self) -> str:
        return f"ScheduleTask(id={self.id}, name={self.name}, type={self.task_type.value}, enabled={self.enabled})"
