#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单管理日报邮件脚本（生产端 /root/xiaozhi-server/tools/）

功能：每天 00:00 查询订单数据库，生成【全量】订单 Excel 报表，通过 QQ 邮箱 SMTP 发送给指定收件人。
      全量 = 订单库全部未删除订单（shipping_status <> '3'，与后台订单管理页一致）。

用法：
    python3 order_report_mailer.py                # 常规发送（全量订单）
    python3 order_report_mailer.py --once         # 立即执行一次（同常规）
    python3 order_report_mailer.py --yesterday    # 只发昨天的订单（旧行为，备用）
    python3 order_report_mailer.py --from 2026-10-01 --to 2026-10-20   # 自定义区间

修改指南：
    - 邮箱账号 / 收件人 / 数据库连接 / 发送时间，全部在 OrderReportMailer.__init__ 的参数数组里改。
    - 支持多邮箱轮询（SMTP 配置数组 smtp_accounts），第一个失败自动切换下一个（冗余兜底）。
    - 支持多收件人（to_addrs 数组），一键批量发送。
    - 列顺序、列宽、状态中文映射在 SheetBuilder 的 COLUMNS 常量里改。
"""
import argparse
import logging
import os
import smtplib
import sys
import tempfile
from datetime import datetime, timedelta
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

# ============================================================
# 全局常量（一般不需要改）
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "order_report.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("order-mailer")


# ============================================================
# 1. 数据库读取层
# ============================================================
class OrderDatabase:
    """订单数据访问：查库 → 返回行数据字典列表。"""

    def __init__(self, host, port, user, password, database):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

    def fetch_orders(self, date_from=None, date_to=None):
        """查询订单：默认全量（排除已删除 shipping_status='3'）；指定区间时按支付时间过滤。"""
        import pymysql
        conn = pymysql.connect(
            host=self.host, port=self.port, user=self.user,
            password=self.password, database=self.database,
            charset="utf8mb4", connect_timeout=10,
        )
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                if date_from and date_to:
                    cur.execute(
                        """
                        SELECT id, user_name, contact, product, amount, pay_time,
                               address, shipping_status, remark, create_time, update_time
                        FROM order_table
                        WHERE pay_time >= %s AND pay_time <= %s
                          AND (shipping_status IS NULL OR shipping_status <> '3')
                        ORDER BY pay_time DESC
                        """,
                        (date_from, date_to),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, user_name, contact, product, amount, pay_time,
                               address, shipping_status, remark, create_time, update_time
                        FROM order_table
                        WHERE (shipping_status IS NULL OR shipping_status <> '3')
                        ORDER BY create_time DESC
                        """
                    )
                return cur.fetchall()
        finally:
            conn.close()


# ============================================================
# 2. Excel 报表生成层
# ============================================================
class SheetBuilder:
    """把订单行数据写成 .xlsx 文件（列顺序/宽度/中文表头集中在这里改）。"""

    # 列配置：(表头, 数据键, 列宽)
    COLUMNS = [
        ("订单号", "id", 34),
        ("客户姓名", "user_name", 12),
        ("联系方式", "contact", 16),
        ("商品描述", "product", 30),
        ("金额(元)", "amount", 10),
        ("支付时间", "pay_time", 20),
        ("收货地址", "address", 36),
        ("订单状态", "shipping_status", 10),
        ("备注", "remark", 24),
        ("创建时间", "create_time", 20),
    ]

    # 订单状态 → 中文（与后台订单管理页一致：0 待处理 / 1 已发货 / 2 已完成 / 3 已取消）
    STATUS_CN = {
        "0": "待处理",
        "1": "已发货",
        "2": "已完成",
        "3": "已取消",
    }

    def status_cn(self, value):
        return self.STATUS_CN.get(str(value), str(value) if value else "")

    def build(self, rows):
        """rows: list[dict] → 返回临时 xlsx 文件路径。"""
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "订单报表"

        # 表头
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="4472C4")
        for col_idx, (title, _key, width) in enumerate(self.COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=title)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[cell.column_letter].width = width

        # 数据行
        for r, row in enumerate(rows, start=2):
            for col_idx, (_title, key, _width) in enumerate(self.COLUMNS, start=1):
                value = row.get(key)
                if key == "shipping_status":
                    value = self.status_cn(value)
                elif value is None:
                    value = ""
                ws.cell(row=r, column=col_idx, value=value).alignment = Alignment(vertical="center")

        ws.freeze_panes = "A2"
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        wb.save(tmp.name)
        return tmp.name


# ============================================================
# 3. 邮件发送层
# ============================================================
class MailSender:
    """QQ SMTP 发送（SSL 465）；支持多账号轮询兜底。"""

    def __init__(self, smtp_accounts, to_addrs, from_display_name="订单管理系统"):
        self.smtp_accounts = smtp_accounts  # [{"user":..., "auth_code":...}, ...]
        self.to_addrs = to_addrs             # ["a@qq.com", "b@qq.com", ...]
        self.from_display_name = from_display_name

    def send(self, subject, body_html, xlsx_path, filename):
        """逐账号尝试发送；全部失败抛 RuntimeError。"""
        errors = []
        for acc in self.smtp_accounts:
            try:
                self._send_once(acc, subject, body_html, xlsx_path, filename)
                log.info(f"发送成功 via {acc['user']} -> {self.to_addrs}")
                return
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{acc['user']}: {exc}")
                log.warning(f"账号 {acc['user']} 发送失败: {exc}，切换下一账号")
        raise RuntimeError("所有 SMTP 账号均发送失败: " + " | ".join(errors))

    def _send_once(self, acc, subject, body_html, xlsx_path, filename):
        msg = MIMEMultipart()
        msg["From"] = formataddr((Header(self.from_display_name, "utf-8").encode(), acc["user"]))
        msg["To"] = ", ".join(self.to_addrs)
        msg["Subject"] = Header(subject, "utf-8")
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with open(xlsx_path, "rb") as f:
            att = MIMEApplication(f.read())
        att.add_header(
            "Content-Disposition", "attachment", filename=("gbk", "", filename)
        )
        msg.attach(att)

        server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30)
        try:
            server.login(acc["user"], acc["auth_code"])
            server.sendmail(acc["user"], self.to_addrs, msg.as_string())
        finally:
            server.quit()


# ============================================================
# 4. 主类：把所有部件装进 __init__，一键 run()
# ============================================================
class OrderReportMailer:
    """订单日报主流程：拉数 → 生成 Excel → 发邮件 → 清理。

    ⚠️ 修改关键参数只动 __init__ 里的数组：
      - DB_CONN ：数据库连接（批量切换环境）
      - SMTP_ACCOUNTS ：邮箱账号数组（冗余兜底）
      - TO_ADDRS ：收件人数组（批量发送）
      - CC_ADDRS ：抄送数组
    """

    def __init__(self):
        # ---- 数据库连接参数 ----
        self.db_params = dict(
            host="127.0.0.1",
            port=3306,
            user="root",
            password="123456",
            database="xiaozhi_esp32_server",
        )

        # ---- 邮箱账号数组（第一个失败自动切换下一个）----
        self.smtp_accounts = [
            {
                "user": "3480877831@qq.com",
                "auth_code": "mbxkmxtyeoylcjha",  # QQ 邮箱 SMTP 授权码（非登录密码）
            },
        ]

        # ---- 收件人 / 抄送数组（批量发送）----
        self.to_addrs = ["wangmingming02677@qq.com"]
        self.cc_addrs = []

        # ---- 邮件外观 ----
        self.subject_prefix = "订单日报"
        self.from_display_name = "订单管理系统"

        # ---- 组装部件 ----
        self.db = OrderDatabase(**self.db_params)
        self.sheet = SheetBuilder()
        self.mailer = MailSender(
            smtp_accounts=self.smtp_accounts,
            to_addrs=self.to_addrs,
            from_display_name=self.from_display_name,
        )

    # ---------- 流程方法 ----------
    def run(self, date_from=None, date_to=None):
        """主入口：查询 → Excel → 邮件。默认全量；失败抛异常（供 cron 日志捕获）。"""
        rows = self.db.fetch_orders(date_from, date_to)
        if date_from:
            range_label = f"{date_from[:10]}~{date_to[:10]}"
            log.info(f"查询到 {len(rows)} 条订单（区间 {range_label}）")
        else:
            range_label = "全量"
            log.info(f"查询到 {len(rows)} 条订单（全量，排除已删除）")

        xlsx_path = self.sheet.build(rows)
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            subject = f"{self.subject_prefix} {today}（{range_label}，共 {len(rows)} 单）"
            body = self.build_body_html(today, range_label, len(rows), rows)
            filename = f"orders_{today.replace('-', '')}_{range_label}.xlsx"
            self.mailer.send(subject, body, xlsx_path, filename)
            log.info("邮件已发送")
        finally:
            if os.path.exists(xlsx_path):
                os.remove(xlsx_path)

    def build_body_html(self, day, range_label, count, rows):
        """邮件正文（纯静态 HTML，无需模板引擎）。含状态分布统计。"""
        # 状态分布
        stat = {}
        for r in rows:
            s = self.sheet.status_cn(r.get("shipping_status")) or "未知"
            stat[s] = stat.get(s, 0) + 1
        stat_html = " / ".join(f"{k} {v}" for k, v in stat.items()) if stat else "无订单"
        return f"""
        <div style="font-family:'Microsoft YaHei',sans-serif;max-width:640px;margin:0 auto;">
          <h2 style="color:#333;border-bottom:2px solid #4472C4;padding-bottom:8px;">
            📦 {self.subject_prefix} · {day}（{range_label}）
          </h2>
          <p style="font-size:15px;color:#555;">订单总数：<b style="color:#c00;">{count}</b> 单</p>
          <p style="font-size:14px;color:#555;">状态分布：{stat_html}</p>
          <p style="font-size:13px;color:#888;">
            报表生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（系统自动发送，请勿直接回复）
          </p>
          <p style="font-size:13px;color:#555;">附件为订单明细（Excel，{range_label}，不含已删除订单），请查收。</p>
        </div>
        """


# ============================================================
# 入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="订单日报邮件（默认全量订单）")
    parser.add_argument("--once", action="store_true", help="立即执行一次（同常规：全量）")
    parser.add_argument("--yesterday", action="store_true", help="只发昨天的订单（旧行为，备用）")
    parser.add_argument("--from", dest="date_from", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="结束日期 YYYY-MM-DD")
    args = parser.parse_args()

    mailer = OrderReportMailer()
    if args.date_from or args.date_to:
        df = args.date_from + " 00:00:00" if args.date_from else None
        dt = args.date_to + " 23:59:59" if args.date_to else None
        mailer.run(date_from=df, date_to=dt)
    elif args.yesterday:
        d = datetime.now() - timedelta(days=1)
        mailer.run(
            date_from=d.strftime("%Y-%m-%d 00:00:00"),
            date_to=d.strftime("%Y-%m-%d 23:59:59"),
        )
    else:
        # 默认（含 --once）：全量订单
        mailer.run()


if __name__ == "__main__":
    main()
