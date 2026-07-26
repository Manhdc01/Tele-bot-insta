import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
import telebot

# ------------------------------------------------------------------
# 0. TẠO WEB SERVER TÍ HON ĐỂ LÁCH MẸO RENDER FREE TIER
# ------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ------------------------------------------------------------------
# 1. CẤU HÌNH BOT TELEGRAM
# ------------------------------------------------------------------
BOT_TOKEN = "DÁN_TOKEN_BOT_TELEGRAM_CỦA_BẠN_VÀO_ĐÂY"
bot = telebot.TeleBot(BOT_TOKEN)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# ------------------------------------------------------------------
# 2. XỬ LÝ PROXY
# ------------------------------------------------------------------
proxy_index = 0

def load_proxies():
    if not os.path.exists("proxies.txt"):
        return []
    with open("proxies.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_next_proxy():
    global proxy_index
    proxies = load_proxies()
    if not proxies:
        return None

    proxy_str = proxies[proxy_index % len(proxies)]
    proxy_index += 1

    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        formatted = f"http://{user}:{pw}@{ip}:{port}"
    elif len(parts) == 2:
        ip, port = parts
        formatted = f"http://{ip}:{port}"
    else:
        formatted = proxy_str if proxy_str.startswith("http") else f"http://{proxy_str}"

    return {"http": formatted, "https": formatted}

# ------------------------------------------------------------------
# 3. HÀM CHECK INSTAGRAM STATUS
# ------------------------------------------------------------------
def check_instagram(username: str) -> str:
    username = username.strip().replace("@", "")
    url = f"https://www.instagram.com/{username}/"

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }

    proxies = get_next_proxy()

    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=7, allow_redirects=True)

        if response.status_code == 404:
            return "❌ DIE"

        if "accounts/login" in response.url or "challenge" in response.url:
            return "⚠️ BỊ BLOCK IP / RATE LIMIT"

        if response.status_code == 200:
            text = response.text.lower()
            die_signals = [
                "sorry, this page isn't available",
                "profile isn't available",
                "page not found",
                "link may be broken",
            ]
            if any(sig in text for sig in die_signals):
                return "❌ DIE"
            
            return "✅ LIVE"

        return f"⚠️ Lỗi HTTP {response.status_code}"

    except requests.exceptions.ProxyError:
        return "⚠️ Proxy Lỗi"
    except requests.exceptions.Timeout:
        return "⚠️ Proxy Timeout"
    except Exception:
        return "⚠️ Lỗi Kết Nối"

# ------------------------------------------------------------------
# 4. LỆNH TELEGRAM BOT
# ------------------------------------------------------------------
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    welcome_text = (
        "🤖 **Bot Check Instagram Live/Die**\n\n"
        "📌 **Cú pháp sử dụng:**\n"
        "1️⃣ `/check username` - Check 1 tài khoản\n"
        "2️⃣ `/checklist uid|pass|2fa...` - Check danh sách nhiều tài khoản"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=["check"])
def handle_check(message):
    text = message.text.replace("/check", "").strip()
    if not text:
        bot.reply_to(message, "⚠️ Vui lòng nhập Username! Ví dụ: `/check instagram`", parse_mode="Markdown")
        return

    msg = bot.reply_to(message, f"🔍 Đang kiểm tra @{text}...")
    status = check_instagram(text)
    bot.edit_message_text(f"👤 Account: @{text}\nTrạng thái: {status}", message.chat.id, msg.message_id)

@bot.message_handler(commands=["checklist"])
def handle_checklist(message):
    raw_text = message.text.replace("/checklist", "").strip()
    if not raw_text:
        bot.reply_to(message, "⚠️ Vui lòng nhập danh sách nick! Ví dụ:\n`/checklist user1|pass1\nuser2|pass2`", parse_mode="Markdown")
        return

    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    total = len(lines)

    msg = bot.reply_to(message, f"🚀 **Đang tiến hành check {total} tài khoản...**", parse_mode="Markdown")

    live_count, die_count, unknown_count = 0, 0, 0
    die_list = []

    for idx, line in enumerate(lines, 1):
        username = line.split("|")[0].strip().replace("@", "")
        status = check_instagram(username)

        if "LIVE" in status:
            live_count += 1
        elif "DIE" in status:
            die_count += 1
            die_list.append(f"@{username}")
        else:
            unknown_count += 1

        bot.send_message(message.chat.id, f"[{idx}/{total}] 👤 @{username}\n{status}")
        time.sleep(random.uniform(1.5, 3.0))

    summary = (
        f"✅ **Đã check xong toàn bộ danh sách!**\n"
        f"🌐 LIVE: {live_count}\n"
        f"❌ DIE: {die_count}\n"
        f"⚠️ Không xác định: {unknown_count}\n"
    )
    if die_list:
        summary += "\n**Danh sách DIE:**\n" + "\n".join(die_list)

    bot.send_message(message.chat.id, summary, parse_mode="Markdown")

# ------------------------------------------------------------------
# 5. KHỞI CHẠY BOT
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Chạy Web Server ở luồng phụ
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print("🤖 Bot đang chạy...")
    bot.infinity_polling()