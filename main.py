"""
Telegram Bot kiểm tra trạng thái Instagram (Live/Die) dùng Playwright
======================================================================
Cập nhật mới:
- Tăng tốc x5 lần nhờ:
  1. Chặn tải Hình ảnh, CSS, Phông chữ, Media.
  2. Rút ngắn thời gian chờ tải trang (DOM ready).
  3. Giảm delay nghỉ giữa các lượt check xuống 0.5s.
- Nút [⏹️ Dừng Check] luôn luôn tự động di chuyển xuống tin nhắn kết quả MỚI NHẤT.
"""

import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from telebot import types
from playwright.sync_api import sync_playwright

# ------------------------------------------------------------------
# 0. WEB SERVER PHỤ - GIÚP RENDER FREE TIER HOẠT ĐỘNG 24/7
# ------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot Playwright is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ---------------- Telegram ----------------
# ---------------- Telegram ----------------
# Đọc Token từ Biến môi trường (Environment Variable) để tránh bị lộ
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("⚠️ Chưa cấu hình BOT_TOKEN trong Environment Variables!")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ---------------- Proxy (tuỳ chọn) ----------------
PROXY_FILE = os.environ.get("PROXY_FILE", "proxies.txt")


def parse_proxy_line(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    if "://" in line:
        line = line.split("://", 1)[1]

    if "@" in line:
        creds, hostport = line.split("@", 1)
        user, pw = creds.split(":", 1)
        return {"server": f"http://{hostport}", "username": user, "password": pw}

    parts = line.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        return {"server": f"http://{ip}:{port}", "username": user, "password": pw}
    if len(parts) == 2:
        return {"server": f"http://{line}"}
    return None


def load_proxies(path: str) -> list:
    if not os.path.exists(path):
        return []
    result = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parsed = parse_proxy_line(line)
            if parsed:
                result.append(parsed)
    return result


PROXIES = load_proxies(PROXY_FILE)
_proxy_index_lock = threading.Lock()
_proxy_index = 0


def next_proxy():
    global _proxy_index
    if not PROXIES:
        return None
    with _proxy_index_lock:
        proxy = PROXIES[_proxy_index % len(PROXIES)]
        _proxy_index += 1
    return proxy


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def extract_username(text: str) -> str:
    text = text.strip()
    if "|" in text:
        return text.split("|", 1)[0].strip()

    match = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", text)
    if match:
        return match.group(1).strip("/")

    return text.lstrip("@").strip("/")


def extract_all_usernames_from_text(raw_text: str) -> list:
    seen = set()
    usernames = []

    pattern = r"(?:^|\s+|SUCCESS\|)\s*([A-Za-z0-9._]{1,30})\|"
    ignored_keys = {
        "sessionid",
        "csrftoken",
        "ds_user_id",
        "rur",
        "mid",
        "datr",
        "wd",
        "ig_did",
        "http",
        "https",
    }

    for uname in re.findall(pattern, raw_text, flags=re.IGNORECASE):
        uname = uname.strip().lstrip("@")
        if uname and uname.lower() not in ignored_keys and uname not in seen:
            if re.match(r"^[A-Za-z0-9._]{1,30}$", uname):
                seen.add(uname)
                usernames.append(uname)

    if not usernames:
        for token in raw_text.split():
            u = extract_username(token)
            if u and u not in seen and u.lower() not in ignored_keys:
                seen.add(u)
                usernames.append(u)

    return usernames


# def check_instagram_status(browser, username: str) -> str:
#     proxy = next_proxy()
#     url = f"https://www.instagram.com/{username}/"

#     context = browser.new_context(
#         user_agent=UA,
#         locale="en-US",
#         proxy=proxy,
#         viewport={"width": 800, "height": 600},
#     )

#     # 🚀 TỐI ƯU 1: Chặn tải Ảnh, CSS, Media, Font chữ
#     context.route(
#         "**/*",
#         lambda route: route.abort()
#         if route.request.resource_type in ["image", "stylesheet", "font", "media"]
#         else route.continue_(),
#     )

#     try:
#         page = context.new_page()
#         try:
#             # 🚀 TỐI ƯU 2: Giảm timeout chờ trang xuống 10s và wait_for_timeout xuống 600ms
#             page.goto(url, wait_until="domcontentloaded", timeout=10000)
#             page.wait_for_timeout(600)

#             title = page.title()
#             body_text = page.inner_text("body")

#             die_signals = [
#                 "profile isn't available",
#                 "sorry, this page isn't available",
#                 "page not found",
#                 "content isn't available",
#                 "link may be broken",
#                 "profile may have been removed",
#             ]
#             body_lower = body_text.lower()
#             title_lower = title.lower()

#             if any(sig in body_lower for sig in die_signals) or any(
#                 sig in title_lower for sig in die_signals
#             ):
#                 return "❌ DIE"

#             return "✅ LIVE"
#         finally:
#             page.close()
#     except Exception as e:
#         return f"⚠️ Lỗi khi mở trang: {e}"
#     finally:
#         context.close()
def check_instagram_status(browser, username: str) -> str:
    proxy = next_proxy()
    url = f"https://www.instagram.com/{username}/"

    context = browser.new_context(
        user_agent=UA,
        locale="en-US",
        proxy=proxy,
        viewport={"width": 800, "height": 600},
    )

    # Chỉ chặn Ảnh, Font, Media (Giữ lại CSS nhẹ để Insta render chữ chuẩn)
    context.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ["image", "font", "media"]
        else route.continue_(),
    )

    try:
        page = context.new_page()
        try:
            # 1. BẮT MÃ RESPONSE HTTP TỪ INSTAGRAM
            response = page.goto(url, wait_until="domcontentloaded", timeout=12000)

            # Nếu Server trả về thẳng 404 -> CHẮC CHẮN DIE
            if response and response.status == 404:
                return "❌ DIE"

            # Chờ 1s cho JS render nội dung
            page.wait_for_timeout(1000)

            current_url = page.url.lower()
            title = page.title().lower()
            body_text = page.inner_text("body").lower()

            # 2. KIỂM TRA BỊ BLOCK IP / CHUYỂN HƯỚNG SANG TRANG LOGIN
            if "accounts/login" in current_url or "log in" in title or "đăng nhập" in title:
                return "⚠️ IP bị Insta Block (Dính trang Login)"

            # 3. CÁC DẤU HIỆU XÁC NHẬN DIE
            die_signals = [
                "profile isn't available",
                "sorry, this page isn't available",
                "page not found",
                "content isn't available",
                "link may be broken",
                "profile may have been removed",
                "trang này không khả dụng",
                "không tìm thấy trang",
            ]

            if any(sig in body_text for sig in die_signals) or any(sig in title for sig in die_signals):
                return "❌ DIE"

            # 4. KIỂM TRA DẤU HIỆU XÁC NHẬN LIVE
            # Trang Live chuẩn phải chứa Username hoặc thông số Posts/Followers
            if (
                username.lower() in title
                or username.lower() in body_text
                or "posts" in body_text
                or "followers" in body_text
                or "instagram photos" in title
            ):
                return "✅ LIVE"

            # Nếu không tìm thấy dấu hiệu rõ ràng -> Mặc định báo DIE để an toàn
            return "❌ DIE"

        finally:
            page.close()
    except Exception as e:
        return f"⚠️ Lỗi kết nối: {e}"
    finally:
        context.close()

# ---------------- Quản lý Session & Tiến trình ----------------
user_sessions = {}
session_lock = threading.Lock()

active_checks = {}
active_checks_lock = threading.Lock()


def get_collect_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🚀 Bắt đầu Check", callback_data="start_check"),
        types.InlineKeyboardButton("❌ Hủy", callback_data="cancel_check"),
    )
    return markup


def get_stop_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("⏹️ Dừng Check", callback_data="stop_check"))
    return markup


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "Xin chào! Các lệnh:\n\n"
        "/check <username hoặc link> — kiểm tra 1 tài khoản\n\n"
        "/checklist — Bật chế độ thu thập danh sách.\n\n"
        "/stop — Dừng tiến trình check đang chạy.",
    )


@bot.message_handler(commands=["stop"])
def handle_stop_command(message):
    chat_id = message.chat.id
    with active_checks_lock:
        if chat_id in active_checks:
            active_checks[chat_id]["stop"] = True
            bot.reply_to(message, "🛑 Đã nhận lệnh dừng! Đang dừng sau lượt này...")
        else:
            bot.reply_to(message, "⚠️ Hiện không có tiến trình check nào đang chạy.")


@bot.message_handler(commands=["check"])
def handle_check(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Cú pháp: /check <username hoặc link Instagram>")
        return

    username = extract_username(parts[1])
    if not username:
        bot.reply_to(message, "Không nhận diện được username, thử lại nhé.")
        return

    bot.reply_to(message, f"Đang chạy @{username}...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            status = check_instagram_status(browser, username)
            browser.close()
    except Exception as e:
        status = f"⚠️ Lỗi hệ thống: {e}"

    bot.reply_to(message, f"👤 @{username}\n{status}")


# 🚀 TỐI ƯU 3: Mặc định giảm delay giữa các lần check xuống 0.5s
CHECK_DELAY_SECONDS = float(os.environ.get("CHECK_DELAY_SECONDS", "0.5"))


@bot.message_handler(commands=["checklist"])
def handle_checklist(message):
    chat_id = message.chat.id

    with active_checks_lock:
        if chat_id in active_checks:
            bot.reply_to(
                message,
                "⚠️ Đang có 1 danh sách đang chạy. Hãy dừng lại trước khi tạo danh sách mới.",
            )
            return

    parts = message.text.split(maxsplit=1)
    buffer_data = []
    if len(parts) > 1:
        buffer_data.append(parts[1])

    sent_msg = bot.reply_to(
        message,
        f"📥 **ĐÃ BẬT CHẾ ĐỘ THU THẬP DANH SÁCH**\n\n"
        f"Hãy dán (paste) các phần dữ liệu vào đây.\n\n"
        f"📊 **Đã nhận:** {len(buffer_data)} phần dữ liệu.\n"
        f"👉 Khi dán xong, bấm **[🚀 Bắt đầu Check]** bên dưới.",
        parse_mode="Markdown",
        reply_markup=get_collect_keyboard(),
    )

    with session_lock:
        user_sessions[chat_id] = {
            "collecting": True,
            "buffer": buffer_data,
            "main_msg_id": sent_msg.message_id,
        }


@bot.message_handler(
    func=lambda msg: user_sessions.get(msg.chat.id, {}).get("collecting", False)
    and not msg.text.startswith("/")
)
def handle_collecting_text(message):
    chat_id = message.chat.id
    main_msg_id = None
    count = 0

    with session_lock:
        if chat_id in user_sessions and user_sessions[chat_id].get("collecting"):
            user_sessions[chat_id]["buffer"].append(message.text)
            count = len(user_sessions[chat_id]["buffer"])
            main_msg_id = user_sessions[chat_id].get("main_msg_id")

    if main_msg_id:
        try:
            bot.edit_message_text(
                f"📥 **ĐÃ BẬT CHẾ ĐỘ THU THẬP DANH SÁCH**\n\n"
                f"Hãy tiếp tục dán các phần dữ liệu còn lại vào đây.\n\n"
                f"📊 **Đã nhận:** {count} phần dữ liệu.\n"
                f"👉 Khi dán xong, bấm **[🚀 Bắt đầu Check]** bên dưới.",
                chat_id=chat_id,
                message_id=main_msg_id,
                parse_mode="Markdown",
                reply_markup=get_collect_keyboard(),
            )
        except Exception:
            pass


def run_check_loop_thread(chat_id: int, usernames: list, control_msg_id: int):
    total = len(usernames)
    live_list, die_list, other_list = [], [], []
    stopped_by_user = False
    last_msg_id = None

    # Sửa tin nhắn điều khiển ban đầu thành thông báo bắt đầu
    try:
        bot.edit_message_text(
            f"🚀 **Đang tiến hành check {total} tài khoản ...**",
            chat_id=chat_id,
            message_id=control_msg_id,
            parse_mode="Markdown",
        )
    except Exception:
        pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for i, uname in enumerate(usernames, 1):
                    # Kiểm tra cờ Dừng
                    with active_checks_lock:
                        if active_checks.get(chat_id, {}).get("stop"):
                            stopped_by_user = True
                            break

                    status = check_instagram_status(browser, uname)

                    # Xóa nút Dừng ở tin nhắn trước đó (nếu có)
                    if last_msg_id:
                        try:
                            bot.edit_message_reply_markup(
                                chat_id=chat_id,
                                message_id=last_msg_id,
                                reply_markup=None,
                            )
                        except Exception:
                            pass

                    # Gửi tin nhắn kết quả MỚI và gắn nút [⏹️ Dừng Check] vào đó
                    is_last = i == total
                    reply_markup = None if is_last else get_stop_keyboard()

                    sent_item_msg = bot.send_message(
                        chat_id,
                        f"[{i}/{total}] 👤 @{uname}\n{status}",
                        reply_markup=reply_markup,
                    )
                    last_msg_id = sent_item_msg.message_id

                    if "DIE" in status:
                        die_list.append(uname)
                    elif "LIVE" in status:
                        live_list.append(uname)
                    else:
                        other_list.append(uname)

                    if not is_last:
                        sleep_intervals = int(CHECK_DELAY_SECONDS * 10)
                        for _ in range(sleep_intervals):
                            time.sleep(0.1)
                            with active_checks_lock:
                                if active_checks.get(chat_id, {}).get("stop"):
                                    stopped_by_user = True
                                    break
                        if stopped_by_user:
                            break
            finally:
                browser.close()
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Có lỗi xảy ra trong tiến trình: {e}")
    finally:
        with active_checks_lock:
            active_checks.pop(chat_id, None)

    # Xóa nút Dừng trên tin nhắn vừa check xong trước khi in tổng kết
    if last_msg_id:
        try:
            bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=last_msg_id, reply_markup=None
            )
        except Exception:
            pass

    checked_count = len(live_list) + len(die_list) + len(other_list)

    if stopped_by_user:
        summary_lines = [
            "🛑 **ĐÃ DỪNG TIẾN TRÌNH CHECK THEO YÊU CẦU!**",
            f"📊 Đã check: {checked_count} / {total}",
            f"🌐 LIVE: {len(live_list)}",
            f"❌ DIE: {len(die_list)}",
        ]
    else:
        summary_lines = [
            "✅ **Đã check xong toàn bộ danh sách!**",
            f"🌐 LIVE: {len(live_list)}",
            f"❌ DIE: {len(die_list)}",
        ]

    if other_list:
        summary_lines.append(f"⚠️ Không xác định: {len(other_list)}")
    if die_list:
        summary_lines.append(
            "\nDanh sách DIE:\n" + "\n".join(f"- @{u}" for u in die_list)
        )

    bot.send_message(chat_id, "\n".join(summary_lines), parse_mode="Markdown")


@bot.callback_query_handler(
    func=lambda call: call.data in ["start_check", "cancel_check", "stop_check"]
)
def handle_callback(call):
    chat_id = call.message.chat.id

    if call.data == "stop_check":
        with active_checks_lock:
            if chat_id in active_checks:
                active_checks[chat_id]["stop"] = True
                bot.answer_callback_query(
                    call.id,
                    "🛑 Đã nhận lệnh dừng! Đang dừng sau lượt này...",
                    show_alert=False,
                )
            else:
                bot.answer_callback_query(
                    call.id, "Không có tiến trình nào đang chạy!"
                )
        return

    if call.data == "cancel_check":
        with session_lock:
            user_sessions.pop(chat_id, None)
        bot.edit_message_text(
            "❌ Đã hủy lệnh check.",
            chat_id=chat_id,
            message_id=call.message.message_id,
        )
        return

    if call.data == "start_check":
        with session_lock:
            session = user_sessions.pop(chat_id, None)

        if not session or not session.get("buffer"):
            bot.edit_message_text(
                "⚠️ Chưa nhận được danh sách nào!",
                chat_id=chat_id,
                message_id=call.message.message_id,
            )
            return

        full_text = "\n".join(session["buffer"])
        usernames = extract_all_usernames_from_text(full_text)

        if not usernames:
            bot.edit_message_text(
                "❌ Không nhận diện được username nào trong danh sách đã gửi.",
                chat_id=chat_id,
                message_id=call.message.message_id,
            )
            return

        with active_checks_lock:
            active_checks[chat_id] = {"stop": False}

        checker_thread = threading.Thread(
            target=run_check_loop_thread,
            args=(chat_id, usernames, call.message.message_id),
        )
        checker_thread.daemon = True
        checker_thread.start()


# ------------------------------------------------------------------
# KHỞI CHẠY BOT VÀ WEB SERVER
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Bật Web Server phụ để giữ Render Free không bị shut down
    threading.Thread(target=run_health_server, daemon=True).start()

    print("🤖 Bot đang chạy...")

    # Xóa Webhook kẹt cũ để chống lỗi 409 Conflict
    try:
        bot.remove_webhook()
    except Exception:
        pass

    bot.infinity_polling(skip_pending=True)