import os
import sys
import subprocess
import json
import threading
import time
import traceback
import asyncio
import psutil
from datetime import datetime
from telegram import Update, File
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from flask import Flask
from threading import Thread

TOKEN = "8426678402:AAFZcVu7pJvLSQsWGXXwFpHmfu3tbhUqu80"
ADMIN_ID = 8444268448

UPLOAD_DIR = "gelen_dosyalar"
LOG_DIR = "loglar"
KAYITLAR = "kullanicilar.json"

PORT = int(os.environ.get("PORT", 10000))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

if not os.path.exists(KAYITLAR):
    with open(KAYITLAR, "w") as f:
        json.dump({}, f)

aktif_prosesler = {}
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 ZORDO VDS BOT - RENDER'DA ÇALIŞIYOR"

@app.route('/health')
def health():
    return "OK"

def kullanici_ekle(user_id, username, context=None):
    with open(KAYITLAR, "r") as f:
        data = json.load(f)
    if str(user_id) not in data:
        data[str(user_id)] = {"username": username, "sira": len(data) + 1}
        with open(KAYITLAR, "w") as f2:
            json.dump(data, f2)
        if context:
            context.bot.send_message(ADMIN_ID, f"🆕Yeni kullanıcı: @{username}")
    return data[str(user_id)]["sira"]

def paket_yukle(logpath):
    try:
        with open(logpath, "a", encoding='utf-8') as log:
            log.write("\n📦 PAKETLER YÜKLENİYOR...\n")
            
            paketler = [
                "python-telegram-bot", "telethon", "pyrogram", "aiogram",
                "requests", "aiohttp", "pillow", "pymongo", "redis",
                "beautifulsoup4", "pytz", "python-dotenv", "cryptography"
            ]
            
            for paket in paketler:
                try:
                    log.write(f"  {paket}... ")
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", paket],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0:
                        log.write("✅\n")
                    else:
                        log.write("⚠️\n")
                except:
                    log.write("❌\n")
            
            log.write("✅ PAKETLER YÜKLENDİ\n")
    except Exception as e:
        with open(logpath, "a", encoding='utf-8') as log:
            log.write(f"❌ PAKET HATASI: {str(e)}\n")

def bot_calistir(user_id, filepath):
    logpath = os.path.join(LOG_DIR, f"{user_id}.txt")
    
    def run():
        try:
            with open(logpath, "w", encoding='utf-8') as f:
                f.write(f"🤖 BOT BAŞLATILIYOR\nKullanıcı: {user_id}\nDosya: {os.path.basename(filepath)}\nZaman: {datetime.now()}\n")
            
            paket_yukle(logpath)
            
            with open(logpath, "a", encoding='utf-8') as f:
                f.write("\n🚀 BOT ÇALIŞTIRILIYOR...\n")
            
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            proc = subprocess.Popen(
                [sys.executable, "-u", filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                cwd=os.path.dirname(filepath)
            )
            
            aktif_prosesler[user_id] = proc
            
            with open(logpath, "a", encoding='utf-8') as f:
                f.write(f"✅ Process ID: {proc.pid}\n\n")
                f.write("📝 ÇIKTILAR:\n")
            
            # Çıktıları oku
            def read_output():
                while True:
                    if proc.poll() is not None:
                        break
                    try:
                        line = proc.stdout.readline()
                        if line:
                            with open(logpath, "a", encoding='utf-8') as f:
                                f.write(line)
                        else:
                            time.sleep(0.1)
                    except:
                        break
            
            output_thread = threading.Thread(target=read_output, daemon=True)
            output_thread.start()
            
            proc.wait()
            
            with open(logpath, "a", encoding='utf-8') as f:
                f.write(f"\n📤 BOT DURDU. Çıkış kodu: {proc.returncode}\n")
            
            if user_id in aktif_prosesler:
                aktif_prosesler.pop(user_id, None)
                
        except Exception as e:
            with open(logpath, "a", encoding='utf-8') as f:
                f.write(f"\n💀 HATA: {str(e)}\n")
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sira = kullanici_ekle(user.id, user.username, context)
    await update.message.reply_text(
        f"🤖 ZORDO VDS BOT\n@{user.username} Hoş geldin!\nSıra: #{sira}\n\n"
        f"📌 Nasıl Kullanılır:\n"
        f"1. .py bot dosyanızı gönderin\n"
        f"2. Otomatik paket kurulumu yapılacak\n"
        f"3. Botunuz Render'da çalışacak\n\n"
        f"🔧 Komutlar:\n"
        f"/durum - Bot durumu\n"
        f"/log - Çıktıları gör\n"
        f"/kapat - Botu durdur\n"
        f"/aktifet - Yeniden başlat\n\n"
        f"💬 @zordodestek"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    kullanici_ekle(user.id, user.username, context)
    
    doc = update.message.document
    if not doc.file_name.endswith('.py'):
        await update.message.reply_text("❌ Sadece .py dosyası gönderin!")
        return
    
    if user_id in aktif_prosesler:
        proc = aktif_prosesler[user_id]
        if proc and proc.poll() is None:
            proc.terminate()
            time.sleep(1)
        aktif_prosesler.pop(user_id, None)
    
    filename = f"{user_id}_{int(time.time())}_{doc.file_name}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    await update.message.reply_text("📥 Dosya alınıyor...")
    
    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(filepath)
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {str(e)}")
        return
    
    await update.message.reply_text("🔧 Bot hazırlanıyor...")
    
    bot_calistir(user_id, filepath)
    
    await asyncio.sleep(5)
    await update.message.reply_text("✅ Bot başlatıldı!\n/durum ile kontrol edin.")

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if user_id in aktif_prosesler:
        proc = aktif_prosesler[user_id]
        if proc and proc.poll() is None:
            await update.message.reply_text("🟢 BOT ÇALIŞIYOR\n/log ile çıktıları görün.")
        else:
            await update.message.reply_text("🔴 BOT DURDU\nYeniden başlatmak için .py dosyası gönderin.")
    else:
        await update.message.reply_text("🔴 BOT PASİF\nBaşlatmak için .py dosyası gönderin.")

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    hedef = user_id
    if context.args:
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ Sadece admin!")
            return
        hedef = context.args[0].lstrip('@')
    
    log_file = os.path.join(LOG_DIR, f"{hedef}.txt")
    
    if not os.path.exists(log_file):
        await update.message.reply_text("📭 Log yok!")
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content:
            await update.message.reply_text("📭 Log boş!")
            return
        
        content = content[-1500:]
        
        if len(content) > 4000:
            parts = [content[i:i+4000] for i in range(0, len(content), 4000)]
            for i, part in enumerate(parts, 1):
                await update.message.reply_text(f"📄 Log ({i}/{len(parts)}):\n```\n{part}\n```", parse_mode="Markdown")
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(f"📄 Log:\n```\n{content}\n```", parse_mode="Markdown")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {str(e)}")

async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    hedef = user_id
    if context.args:
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ Sadece admin!")
            return
        hedef = context.args[0].lstrip('@')
    
    if hedef in aktif_prosesler:
        proc = aktif_prosesler[hedef]
        if proc and proc.poll() is None:
            proc.terminate()
            time.sleep(1)
            aktif_prosesler.pop(hedef, None)
            await update.message.reply_text("✅ Bot durduruldu!")
        else:
            await update.message.reply_text("⚠️ Bot zaten durmuş!")
    else:
        await update.message.reply_text("📭 Çalışan bot yok!")

async def aktifet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    hedef = user_id
    if context.args:
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ Sadece admin!")
            return
        hedef = context.args[0].lstrip('@')
    
    files = []
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith(f"{hedef}_") and f.endswith('.py'):
            files.append(f)
    
    if not files:
        await update.message.reply_text("❌ Dosya bulunamadı!")
        return
    
    files.sort(reverse=True)
    last_file = files[0]
    filepath = os.path.join(UPLOAD_DIR, last_file)
    
    if hedef in aktif_prosesler:
        proc = aktif_prosesler[hedef]
        if proc and proc.poll() is None:
            proc.terminate()
            time.sleep(1)
        aktif_prosesler.pop(hedef, None)
    
    await update.message.reply_text("🚀 Bot yeniden başlatılıyor...")
    
    bot_calistir(hedef, filepath)
    
    await asyncio.sleep(5)
    await update.message.reply_text("✅ Bot başlatıldı!")

async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sadece admin!")
        return
    
    with open(KAYITLAR, 'r') as f:
        data = json.load(f)
    
    if not data:
        await update.message.reply_text("📭 Kullanıcı yok!")
        return
    
    message = "👥 KULLANICILAR:\n\n"
    for uid, info in sorted(data.items(), key=lambda x: x[1]['sira']):
        status = "🟢" if uid in aktif_prosesler and aktif_prosesler[uid].poll() is None else "🔴"
        message += f"#{info['sira']} @{info.get('username', uid)} {status}\n"
    
    await update.message.reply_text(message)

def start_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)

def start_telegram_bot():
    app_tg = ApplicationBuilder().token(TOKEN).build()
    
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("durum", durum))
    app_tg.add_handler(CommandHandler("log", log))
    app_tg.add_handler(CommandHandler("kapat", kapat))
    app_tg.add_handler(CommandHandler("aktifet", aktifet))
    app_tg.add_handler(CommandHandler("liste", liste))
    app_tg.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("🤖 Telegram bot başlatılıyor...")
    app_tg.run_polling()

def main():
    print("="*60)
    print("🚀 ZORDO VDS BOT - RENDER EDITION")
    print("="*60)
    
    flask_thread = Thread(target=start_flask, daemon=True)
    telegram_thread = Thread(target=start_telegram_bot, daemon=True)
    
    flask_thread.start()
    time.sleep(2)
    telegram_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Bot kapatılıyor...")
        sys.exit(0)

if __name__ == "__main__":
    main()
