"""
内容生成器
提供每日问候、提醒等内容生成功能
"""

import random
from datetime import datetime
from typing import Optional


class ContentGenerator:
    """内容生成器"""

    # 问候语模板
    GREETING_MORNINGS = [
        "早上好！新的一天开始了，祝你元气满满！",
        "早安！记得吃早餐，开启美好一天～",
        "早上好！今天的你也要加油哦！",
        "清晨的第一缕阳光送给你，早安！",
    ]

    GREETING_NOON = [
        "中午好！休息一下，保持活力～",
        "午安！记得小憩片刻哦！",
        "中午好，补充能量继续奋斗！",
    ]

    GREETING_EVENING = [
        "晚上好！辛苦了一天，好好休息吧～",
        "傍晚好，忙碌了一天该放松一下了！",
        "夜幕降临，愿你有个美好的夜晚！",
    ]

    # 提醒模板
    REMINDER_TEMPLATES = [
        "⏰ 提醒：{message}",
        "📌 别忘了：{message}",
        "💡 温馨提示：{message}",
    ]

    # 祝福语
    BLESSINGS = [
        "祝你今天心情愉快！",
        "愿好运常伴你身边！",
        "加油，你可以的！",
        "今天也要开开心心的哦～",
    ]

    def __init__(self):
        self._cache = {}

    async def generate_daily_greeting(self, user_id: str) -> str:
        """
        生成每日问候语

        Args:
            user_id: 用户ID

        Returns:
            问候语文本
        """
        hour = datetime.now().hour

        if 6 <= hour < 12:
            greeting = random.choice(self.GREETING_MORNINGS)
        elif 12 <= hour < 18:
            greeting = random.choice(self.GREETING_NOON)
        else:
            greeting = random.choice(self.GREETING_EVENING)

        blessing = random.choice(self.BLESSINGS)

        return f"{greeting} {blessing}"

    async def generate_reminder(self, user_id: str, template: str, **kwargs) -> str:
        """
        生成提醒内容

        Args:
            user_id: 用户ID
            template: 提醒模板，支持 {message} 占位符
            **kwargs: 其他替换变量

        Returns:
            提醒内容
        """
        # 如果有自定义模板，直接使用
        if template:
            try:
                return template.format(message=kwargs.get("message", ""), **kwargs)
            except KeyError:
                # 格式化失败，返回原始模板
                return template

        # 使用默认提醒模板
        default_template = random.choice(self.REMINDER_TEMPLATES)
        message = kwargs.get("message", "该完成任务啦！")
        return default_template.format(message=message, **kwargs)

    async def generate_special_message(self, user_id: str, event: str) -> str:
        """
        生成特殊事件消息

        Args:
            user_id: 用户ID
            event: 事件类型（birthday/holiday/announcement）

        Returns:
            事件消息
        """
        messages = {
            "birthday": "🎂 生日快乐！愿你岁岁平安，年年有余！",
            "holiday": "🎉 节日快乐！愿你度过一个美好的时光！",
            "announcement": "📢 重要通知：请注意查看相关公告～",
        }

        return messages.get(event, "你好！")

    async def generate_weekly_summary(self, user_id: str, stats: dict) -> str:
        """
        生成周报摘要

        Args:
            user_id: 用户ID
            stats: 统计数据字典

        Returns:
            周报内容
        """
        lines = ["📊 本周总结", ""]

        if "tasks_completed" in stats:
            lines.append(f"✅ 完成任务：{stats['tasks_completed']} 项")
        if "tasks_failed" in stats:
            lines.append(f"❌ 失败任务：{stats['tasks_failed']} 项")
        if "success_rate" in stats:
            lines.append(f"📈 成功率：{stats['success_rate']:.1%}")

        lines.append("")
        lines.append("继续努力，下周会更棒！💪")

        return "\n".join(lines)

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
