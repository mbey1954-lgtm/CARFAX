import os
import sys
import subprocess
import json
import threading
import time
import traceback
import asyncio
import signal
import psutil
from datetime import datetime
from telegram import Update, Bot, File
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from flask import Flask, render_template_string
from threading import Thread

TOKEN = "8426678402:AAFZcVu7pJvLSQsWGXXwFpHmfu3tbhUqu80"
ADMIN_ID = 8444268448

UPLOAD_DIR = "gelen_dosyalar"
LOG_DIR = "loglar"
KAYITLAR = "kullanicilar.json"

# Render için gerekli ayarlar
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

if not os.path.exists(KAYITLAR):
    with open(KAYITLAR, "w") as f:
        json.dump({}, f)

aktif_prosesler = {}

# Flask web server (Render için gerekli)
app = Flask(__name__)

@app.route('/')
def home():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 ZORDO VDS BOT</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                padding: 30px;
                border-radius: 15px;
                margin: 20px 0;
            }
            h1 {
                color: white;
                text-align: center;
                font-size: 2.5em;
                margin-bottom: 20px;
            }
            .status {
                background: rgba(255, 255, 255, 0.2);
                padding: 15px;
                border-radius: 10px;
                margin: 15px 0;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: white;
                color: #667eea;
                text-decoration: none;
                border-radius: 5px;
                margin: 5px;
                font-weight: bold;
            }
            .btn:hover {
                background: #f0f0f0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 ZORDO VDS BOT</h1>
            <p><strong>🚀 Telegram Bot Hosting Platformu</strong></p>
            <p>Bu bot sayesinde .py bot dosyalarınızı yükleyebilir ve otomatik olarak çalıştırabilirsiniz.</p>
            
            <div class="status">
                <h3>📊 Sistem Durumu</h3>
                <p>✅ Bot Aktif</p>
                <p>🕒 Server Time: {{ time }}</p>
                <p>📈 Kullanıcı Sayısı: {{ user_count }}</p>
                <p>⚡ Aktif Botlar: {{ active_bots }}</p>
            </div>
            
            <h3>📱 Telegram'da Kullanım:</h3>
            <ol>
                <li>Botu Telegram'da açın: <a href="https://t.me/zordovdsbot" class="btn" target="_blank">@zordovdsbot</a></li>
                <li>/start yazarak başlayın</li>
                <li>.py bot dosyanızı gönderin</li>
                <li>Otomatik kurulum ve çalıştırma!</li>
            </ol>
            
            <h3>🔧 Komutlar:</h3>
            <ul>
                <li><code>/start</code> - Başlangıç</li>
                <li><code>/durum</code> - Bot durumu</li>
                <li><code>/log</code> - Çıktıları gör</li>
                <li><code>/aktifet</code> - Botu başlat</li>
                <li><code>/kapat</code> - Botu durdur</li>
            </ul>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://t.me/zordodestek" class="btn" target="_blank">💬 Destek</a>
                <a href="https://github.com" class="btn" target="_blank">📂 GitHub</a>
            </div>
        </div>
    </body>
    </html>
    """, time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
       user_count=len(json.load(open(KAYITLAR)) if os.path.exists(KAYITLAR) else {}),
       active_bots=len([p for p in aktif_prosesler.values() if p and p.poll() is None]))

@app.route('/health')
def health():
    return {"status": "healthy", "time": datetime.now().isoformat()}

@app.route('/stats')
def stats():
    return {
        "active_processes": len(aktif_prosesler),
        "total_users": len(json.load(open(KAYITLAR)) if os.path.exists(KAYITLAR) else {}),
        "upload_dir_size": sum(os.path.getsize(os.path.join(UPLOAD_DIR, f)) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))) if os.path.exists(UPLOAD_DIR) else 0,
        "log_dir_size": sum(os.path.getsize(os.path.join(LOG_DIR, f)) for f in os.listdir(LOG_DIR) if os.path.isfile(os.path.join(LOG_DIR, f))) if os.path.exists(LOG_DIR) else 0
    }

# ---------------- Kullanıcı Yönetimi ----------------
def kullanici_ekle(user_id, username, context=None):
    with open(KAYITLAR, "r") as f:
        data = json.load(f)
    if str(user_id) not in data:
        data[str(user_id)] = {"username": username, "sira": len(data) + 1, "joined": datetime.now().isoformat()}
        with open(KAYITLAR, "w") as f2:
            json.dump(data, f2)
        if context:
            context.bot.send_message(
                ADMIN_ID,
                f"🆕Yeni kullanıcı: @{username or user_id} (ID: {user_id})\n"
                f"🆕Yeni Kullanıcı : #{data[str(user_id)]['sira']}"
            )
    return data[str(user_id)]["sira"]

# ---------------- RENDER UYUMLU PAKET YÜKLEME ----------------
def render_paket_yukle(logpath, requirements_content=None):
    """Render için optimize edilmiş paket yükleme"""
    try:
        with open(logpath, "a", encoding='utf-8') as log:
            log.write("\n" + "="*50 + "\n")
            log.write("RENDER PAKET KURULUMU BAŞLIYOR\n")
            log.write("="*50 + "\n")
            
            # TEMEL BOT PAKETLERİ
            temel_paketler = [
                "python-telegram-bot>=20.0",
                "telethon>=1.30",
                "pyrogram>=2.0",
                "aiogram>=3.0",
                "requests>=2.28",
                "aiohttp>=3.8",
                "pillow>=9.0",
                "pymongo>=4.0",
                "redis>=4.0",
                "beautifulsoup4>=4.11",
                "pytz>=2022.0",
                "python-dotenv>=0.19",
                "cryptography>=38.0",
                "flask>=2.0",
                "gunicorn>=20.0",
                "psutil>=5.9"
            ]
            
            # Tek tek yükle (Render'da daha kararlı)
            for paket in temel_paketler:
                try:
                    log.write(f"📦 {paket}... ")
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--no-cache-dir", paket],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode == 0:
                        log.write("✅\n")
                    else:
                        log.write(f"⚠️ ({result.returncode})\n")
                except Exception as e:
                    log.write(f"❌ {str(e)[:50]}\n")
            
            # Requirements.txt içeriği varsa onu da yükle
            if requirements_content:
                log.write("\n📄 requirements.txt YÜKLENİYOR\n")
                try:
                    # Geçici requirements dosyası oluştur
                    temp_req = "/tmp/requirements.txt"
                    with open(temp_req, "w") as f:
                        f.write(requirements_content)
                    
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", temp_req, "--no-cache-dir"],
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    log.write(f"requirements.txt sonucu: {result.returncode}\n")
                except Exception as e:
                    log.write(f"requirements.txt hatası: {str(e)}\n")
            
            log.write("\n✅ PAKET KURULUMU TAMAMLANDI\n")
            
    except Exception as e:
        with open(logpath, "a", encoding='utf-8') as log:
            log.write(f"❌ PAKET YÜKLEME HATASI: {str(e)}\n")

# ---------------- RENDER UYUMLU BOT ÇALIŞTIRMA ----------------
def render_bot_calistir(user_id, filepath):
    """Render için optimize edilmiş bot çalıştırma"""
    logpath = os.path.join(LOG_DIR, f"{user_id}.txt")
    
    def run_bot():
        try:
            # Log dosyasını başlat
            with open(logpath, "w", encoding='utf-8') as f:
                f.write(f"{'='*60}\n")
                f.write(f"🤖 RENDER BOT BAŞLATILIYOR\n")
                f.write(f"👤 User ID: {user_id}\n")
                f.write(f"📁 File: {os.path.basename(filepath)}\n")
                f.write(f"⏰ Time: {datetime.now()}\n")
                f.write(f"{'='*60}\n\n")
            
            # 1. Dosyayı analiz et ve requirements çıkar
            requirements_content = None
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Basit requirements tespiti
                imports_to_check = [
                    'import telethon', 'from telethon',
                    'import pyrogram', 'from pyrogram', 
                    'import pymongo', 'from pymongo',
                    'import redis', 'from redis',
                    'import sqlalchemy', 'from sqlalchemy',
                    'import flask', 'from flask',
                    'import django', 'from django',
                    'import fastapi', 'from fastapi',
                ]
                
                found_imports = []
                for imp in imports_to_check:
                    if imp in content.lower():
                        found_imports.append(imp.split()[-1])
                
                if found_imports:
                    requirements_content = "\n".join(found_imports)
                    
            except:
                pass
            
            # 2. Paketleri yükle
            with open(logpath, "a", encoding='utf-8') as f:
                f.write("1️⃣ PAKETLER YÜKLENİYOR...\n")
            
            render_paket_yukle(logpath, requirements_content)
            
            # 3. Botu çalıştır
            with open(logpath, "a", encoding='utf-8') as f:
                f.write("\n2️⃣ BOT ÇALIŞTIRILIYOR...\n")
            
            # Environment setup
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONPATH'] = os.path.dirname(filepath)
            
            # Process başlat
            proc = subprocess.Popen(
                [sys.executable, "-u", filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                cwd=os.path.dirname(filepath)
            )
            
            aktif_prosesler[user_id] = proc
            
            with open(logpath, "a", encoding='utf-8') as f:
                f.write(f"✅ Process ID: {proc.pid}\n\n")
                f.write("📝 BOT ÇIKTILARI:\n")
                f.write("-"*40 + "\n")
            
            # Output'u oku
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
            
            # Process'i bekle
            return_code = proc.wait()
            
            with open(logpath, "a", encoding='utf-8') as f:
                f.write(f"\n{'='*40}\n")
                f.write(f"📤 Process sonlandı: {return_code}\n")
                f.write(f"⏰ Time: {datetime.now()}\n")
            
            # Process'i listeden çıkar
            if user_id in aktif_prosesler:
                aktif_prosesler.pop(user_id, None)
            
        except Exception as e:
            with open(logpath, "a", encoding='utf-8') as f:
                f.write(f"\n💀 KRİTİK HATA: {str(e)}\n")
                f.write(f"Traceback:\n{traceback.format_exc()}\n")
    
    # Thread'i başlat
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    return thread

# ---------------- TELEGRAM HANDLERS (RENDER UYUMLU) ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sira = kullanici_ekle(user.id, user.username, context)
    
    await update.message.reply_text(
        f"🤖 *ZORDO VDS BOT - RENDER EDITION*\n\n"
        f"👋 Hoş geldin @{user.username or user.id}!\n"
        f"📊 Sıra: #{sira}\n\n"
        f"*🚀 NASIL KULLANILIR:*\n"
        f"1. `.py` bot dosyanızı gönderin\n"
        f"2. Otomatik paket kurulumu yapılır\n"
        f"3. Botunuz Render'da çalıştırılır\n\n"
        f"*📋 KOMUTLAR:*\n"
        f"/durum - Bot durumunu kontrol et\n"
        f"/log - Çıktıları gör\n"
        f"/kapat - Botu durdur\n"
        f"/aktifet - Yeniden başlat\n"
        f"/bilgi - Sistem bilgisi\n\n"
        f"🌐 *Web Panel:* https://your-render-app.onrender.com\n"
        f"💬 *Destek:* @zordodestek",
        parse_mode="Markdown"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    kullanici_ekle(user.id, user.username, context)
    
    doc = update.message.document
    if not doc.file_name.endswith('.py'):
        await update.message.reply_text("❌ Sadece `.py` dosyası gönderebilirsiniz!")
        return
    
    # Eski process'i temizle
    if user_id in aktif_prosesler:
        proc = aktif_prosesler[user_id]
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                time.sleep(1)
            except:
                pass
        aktif_prosesler.pop(user_id, None)
    
    # Dosyayı kaydet
    timestamp = int(time.time())
    filename = f"{user_id}_{timestamp}_{doc.file_name}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    await update.message.reply_text("📥 *Dosya alınıyor...*", parse_mode="Markdown")
    
    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(filepath)
    except Exception as e:
        await update.message.reply_text(f"❌ Dosya indirme hatası:\n`{str(e)}`", parse_mode="Markdown")
        return
    
    await update.message.reply_text(
        "🔧 *Render'da hazırlanıyor...*\n\n"
        "1. ⚙️ Paket analizi yapılıyor\n"
        "2. 📦 Gerekli kütüphaneler yükleniyor\n"
        "3. 🚀 Bot başlatılıyor\n\n"
        "⏳ *Bu işlem 1-2 dakika sürebilir*",
        parse_mode="Markdown"
    )
    
    # Botu Render uyumlu şekilde başlat
    render_bot_calistir(user_id, filepath)
    
    await asyncio.sleep(8)
    await update.message.reply_text(
        "✅ *Bot Render'da başlatıldı!*\n\n"
        "📊 *Kontrol komutları:*\n"
        "• `/durum` - Durumunu gör\n"
        "• `/log` - Çıktıları oku\n"
        "• `/kapat` - Durdur\n\n"
        "⚠️ *Not:* Render'da çalışan botlar 24/7 aktif kalır!",
        parse_mode="Markdown"
    )

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if user_id in aktif_prosesler:
        proc = aktif_prosesler[user_id]
        if proc and proc.poll() is None:
            # Process çalışıyor
            try:
                memory_info = psutil.Process(proc.pid).memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                
                await update.message.reply_text(
                    f"🟢 *BOT AKTİF - RENDER*\n\n"
                    f"• 🆔 PID: `{proc.pid}`\n"
                    f"• 💾 Bellek: `{memory_mb:.1f} MB`\n"
                    f"• 📍 Platform: `Render Cloud`\n"
                    f"• ⏰ Uptime: Çalışıyor\n\n"
                    f"📝 Çıktılar: `/log`\n"
                    f"⏹️ Durdur: `/kapat`",
                    parse_mode="Markdown"
                )
            except:
                await update.message.reply_text(
                    "🟢 *BOT ÇALIŞIYOR*\n\n"
                    "Bot Render'da aktif şekilde çalışıyor.\n"
                    "Çıktıları görmek için: `/log`",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                "🔴 *BOT DURDU*\n\n"
                "Bot Render'da durdu.\n"
                "Yeniden başlat: `/aktifet` veya yeni dosya gönderin.",
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text(
            "🔴 *BOT PASİF*\n\n"
            "Render'da çalışan botunuz yok.\n"
            "Başlatmak için `.py` dosyası gönderin.",
            parse_mode="Markdown"
        )

async def log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    hedef = user_id
    if context.args:
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ Yetkiniz yok!")
            return
        hedef = context.args[0].lstrip('@')
    
    log_file = os.path.join(LOG_DIR, f"{hedef}.txt")
    
    if not os.path.exists(log_file):
        await update.message.reply_text("📭 Log bulunamadı!")
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content:
            await update.message.reply_text("📭 Log boş!")
            return
        
        # Son 1500 karakter
        content = content[-1500:]
        
        if len(content) > 4000:
            parts = [content[i:i+4000] for i in range(0, len(content), 4000)]
            for i, part in enumerate(parts, 1):
                await update.message.reply_text(
                    f"📄 *Log ({i}/{len(parts)}):*\n```\n{part}\n```",
                    parse_mode="Markdown"
                )
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(
                f"📄 *Log:*\n```\n{content}\n```",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: `{str(e)}`", parse_mode="Markdown")

async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    
    hedef = user_id
    if context.args:
        if user.id != ADMIN_ID:
            await update.message.reply_text("❌ Yetkiniz yok!")
            return
        hedef = context.args[0].lstrip('@')
    
    if hedef in aktif_prosesler:
        proc = aktif_prosesler[hedef]
        if proc and proc.poll() is None:
            try:
                # Process tree'yi temizle
                parent = psutil.Process(proc.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
                
                time.sleep(2)
                
                if parent.is_running():
