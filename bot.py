import asyncio
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yt_dlp
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

LINK_REGEX = r"(https?://(?:vm|vt|www)\.tiktok\.com/[^\s]+|https?://(?:www\.)?instagram\.com/(?:p|reel)/[^\s]+)"


# --- RENDER KEEP-ALIVE SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running 24/7!")


def run_health_server():
    # Render assigns a temporary dynamic port to the 'PORT' environment variable
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Health check server listening on port {port}...")
    server.serve_forever()


# --------------------------------


async def download_media(url: str, output_path: str) -> str:
    if "instagram.com" in url:
        url = url.replace("/reel/", "/p/")
    ydl_opts: dict[str, any] = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"instagram": {"embed": True}},
    }
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore
        await loop.run_in_executor(None, lambda: ydl.download([url]))
    return output_path


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    links = re.findall(LINK_REGEX, text)
    if links:
        target_url = links[0]
        chat_id = update.message.chat_id
        message_id = update.message.message_id
        platform = "Instagram Reel" if "instagram.com" in target_url else "TikTok"
        status_msg = await update.message.reply_text(
            f"⏳ Processing {platform} video..."
        )
        filename = f"video_{message_id}.mp4"
        try:
            await download_media(target_url, filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                with open(filename, "rb") as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        reply_to_message_id=message_id,
                        caption="Here is your video! 🎬",
                    )
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Failed to process this video.")
        except Exception as e:
            print(f"Error: {e}")
            await status_msg.edit_text("⚠️ Could not download video.")
        finally:
            if os.path.exists(filename):
                os.remove(filename)


def main():
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Error: TELEGRAM_BOT_TOKEN environment variable not set!")

    # Start the web server in a separate thread so it doesn't block the bot
    threading.Thread(target=run_health_server, daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot is successfully running...")
    application.run_polling()


if __name__ == "__main__":
    main()
