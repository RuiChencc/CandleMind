# -*- coding: utf-8 -*-
"""ws_bot.py — 飞书长连接机器人（双向对话投策 transport 落地）。

用法：python -m pa_agent.feishu.ws_bot
长驻进程：NSSM 托管（PA_Agent 自建服务，如 pa-feishu-bot），不写自启循环（"不启守护"铁律）。

链路：飞书事件（im.message.receive_v1）→ lark_oapi ws.Client →
      longconn.handle_message（指令路由 + 复用 scheduler/FreeChatSession）→
      notify.feishu_notifier.send_chat_text（应用身份回复）。
长连接模式：encrypt_key / verification_token 均传空串（界面文案：无需配置加密策略）。
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

# C343/E298：SDK 在 asyncio loop 内**同步**调用 handler（lark_oapi/ws/client.py:341
# _do_without_validation 无 await/to_thread）→ 阻塞式 run_analysis(~40s) 必须脱离
# loop 执行，否则 keepalive ping 超时断连。有界线程池，每次事件一个 worker。
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _on_message(data) -> None:
    """im.message.receive_v1 处理器：解析文本 → 路由 → 回复。"""
    try:
        msg = data.event.message
    except AttributeError:
        return
    chat_id = getattr(msg, "chat_id", None)
    if not chat_id:
        return
    if getattr(msg, "message_type", None) != "text":
        return  # 只响应文本消息
    try:
        content = json.loads(getattr(msg, "content", None) or "{}")
        text = content.get("text", "")
    except (ValueError, TypeError):
        logger.warning("消息 content 解析失败: chat_id=%s", chat_id)
        return
    if not text:
        return
    logger.info("收到消息 chat_id=%s type=%s text=%s",
                chat_id, getattr(msg, "message_type", "?"), text[:80])

    from pa_agent.feishu.longconn import route_text

    kind, _ = route_text(text)
    # C343/E295：analyze 走真实 LLM（¥0.07/次），PA_AGENT_FEISHU_DRY_RUN=1 时拦截
    dry_run = os.environ.get("PA_AGENT_FEISHU_DRY_RUN") == "1"
    # DRY_RUN 拦截所有 LLM 调用：analyze（¥0.07/次）+ followup（追问 ¥0.02-0.05/次）
    # + dialog 兜底（unknown→单轮 chat，¥0.02-0.07/次；2026-10 P0-3 新增）
    # + track 首跑（追踪注册即分析 ¥0.14/次；track_stop 免费不拦）
    _EXECUTOR.submit(_process_message, chat_id, text, dry_run and kind in ("analyze", "followup", "unknown", "track"))


def _process_message(chat_id: str, text: str, dry_run: bool = False) -> None:
    """worker 线程：路由处理 + 回复发送（不阻塞 SDK 事件循环，防 keepalive 超时）。"""
    from pa_agent.feishu.longconn import handle_message
    from pa_agent.notify.feishu_notifier import send_chat_text

    reply = (
        "DRY_RUN：已跳过 LLM 调用（PA_AGENT_FEISHU_DRY_RUN=1 生效中）"
        if dry_run else handle_message(chat_id, text)
    )
    if reply:
        logger.info("回复 chat_id=%s len=%d", chat_id, len(reply))
        send_chat_text(reply, chat_id)
    else:
        logger.info("无匹配指令，不回复: chat_id=%s text=%s", chat_id, text[:80])


def _sl_watch_loop(interval: float) -> None:
    """SL 巡检线程体：每 interval 秒跑 check_sl（P0-2 三态，幂等）。

    C343：常驻进程一接消息就产生真实副作用（本线程会重挂 SL / 市价平仓）必须
    有显式开关 → 由 PA_AGENT_SL_WATCH_SECONDS 环境变量显式开启（见 main）。
    载体裁定（2026-10）：bot 内线程随 bot 同生死 = 不算另起守护（不启守护铁律
    的豁免项）；schtasks 每 5 分钟做备份（bot 挂时兜底）。daemon 线程 + try/except，
    单次异常不拖垮事件循环。
    """
    import threading
    import time as _t

    from pa_agent.execution.audit_log import AuditLog
    from pa_agent.execution.executor import BinanceSpotExecutor, check_sl

    envf = os.environ.get("BINANCE_TEST_ENV", r"D:\OpenCode\temp\binance_testnet.env")
    env: dict = {}
    for line in open(envf, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); env[k] = v
    key, secret = env.get("BINANCE_TEST_API_KEY"), env.get("BINANCE_TEST_SECRET")
    if not key or not secret:
        logger.error("SL 巡检: 缺少 BINANCE_TEST_API_KEY/SECRET，禁用（检查 binance_testnet.env）")
        return
    ex = BinanceSpotExecutor(key, secret)
    al = AuditLog()
    logger.info("SL 巡检线程启动：interval=%.0fs（PA_AGENT_SL_WATCH_SECONDS）", interval)
    while True:
        try:
            st = check_sl(ex, al)
            if st["scanned"]:
                logger.info("SL 巡检: %s", {k: v for k, v in st.items() if v})
        except Exception as exc:  # noqa: BLE001
            logger.warning("SL 巡检异常: %s", exc)
        _t.sleep(interval)


def _track_watch_loop(interval: float) -> None:
    """追踪巡检线程体：每 interval 秒扫 longconn.track_sweep（到点的标的跑分析）。

    用户主动发「追踪 <币种>」才注册目标（longconn 持久化 records/tracks.json）→
    无追踪目标时 no-op 零成本；有目标按周期烧钱（¥0.14/标的/周期，用户可停止）。
    随 bot 同生死 = 不算另起守护（与 _sl_watch_loop 同一豁免裁定）。
    """
    import time as _t

    from pa_agent.feishu.longconn import _load_tracks, _last_run, _tracks, track_sweep

    _load_tracks()
    now = _t.time()
    # 重启后首个周期从启动时刻起算（防恢复后立即全量重跑烧钱）
    for _c, _d in _tracks.items():
        for _s, _tf in _d.items():
            _last_run[(_c, _s, _tf)] = now
    logger.info("追踪巡检线程启动：interval=%.0fs（追踪目标=%d）",
                interval, sum(len(d) for d in _tracks.values()))
    while True:
        try:
            done = track_sweep()
            if done:
                logger.info("追踪巡检执行: %s", done)
        except Exception as exc:  # noqa: BLE001
            logger.warning("追踪巡检异常: %s", exc)
        _t.sleep(interval)


def main(log_level: str = "INFO") -> int:
    """启动长连接客户端（阻塞保持连接，直到进程终止）。

    C343 显式开关：设 PA_AGENT_SL_WATCH_SECONDS=30（秒，min 5）时启动
    SL 巡检线程（默认不启动）；bot 常驻即巡检常驻，schtasks 备份见 docs。
    """
    from pa_agent.config.paths import SETTINGS_JSON_PATH
    from pa_agent.config.settings import load_settings

    settings = load_settings(SETTINGS_JSON_PATH)
    feishu = getattr(settings, "feishu", None)
    if feishu is None or not (feishu.app_id or "").strip() or not (feishu.app_secret or "").strip():
        logger.error("settings.json 未配置 feishu.app_id/app_secret（重置后的凭证填这里），退出")
        return 1

    from lark_oapi.ws import Client
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

    handler = (
        EventDispatcherHandler.builder(encrypt_key="", verification_token="")
        .register_p2_im_message_receive_v1(_on_message)
        .build()
    )

    client = Client(
        app_id=feishu.app_id,
        app_secret=feishu.app_secret,
        event_handler=handler,
        auto_reconnect=True,
    )
    # C343：SL 巡检线程须显式开关（缺省不启动）——PA_AGENT_SL_WATCH_SECONDS 秒级
    _sl_watch_raw = os.environ.get("PA_AGENT_SL_WATCH_SECONDS", "").strip()
    if _sl_watch_raw:
        try:
            _sl_watch_interval = max(5.0, float(_sl_watch_raw))
        except ValueError:
            _sl_watch_interval = 30.0
        import threading
        _t = threading.Thread(target=_sl_watch_loop, args=(_sl_watch_interval,),
                              daemon=True, name="sl-watch")
        _t.start()
        logger.info("飞书长连接启动：app_id=%s（SL 巡检线程开启，%.0fs）",
                    feishu.app_id[:10] + "...", _sl_watch_interval)
    else:
        logger.info("飞书长连接启动：app_id=%s（SL 巡检未开启：PA_AGENT_SL_WATCH_SECONDS 未设）",
                    feishu.app_id[:10] + "...")
    # 追踪巡检线程（随 bot 同生死；无追踪目标 no-op 零成本，无需显式开关）
    import threading
    _tt = threading.Thread(target=_track_watch_loop, args=(60.0,),
                           daemon=True, name="track-watch")
    _tt.start()
    client.start()  # 阻塞；连接成功后飞书后台「验证连接状态」即通过
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    raise SystemExit(main())
