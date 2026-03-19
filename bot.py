import os
import logging
import asyncio
import uuid
import time
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(_name_)

# Récupération des variables d'environnement
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')  # Fourni automatiquement par Render

# Constantes
DEPOSIT_AMOUNTS = [3000, 5000, 10000, 15000, 25000, 35000, 45000]
REWARD_PERCENTAGE = 35
MIN_WITHDRAWAL = 1500
DEPOSIT_PHONE = "+237652870191"

# Stockage temporaire (remplace la base de données pour l'exemple)
user_balances = {}  # {user_id: balance}
user_deposits = {}  # {user_id: total_deposited}
user_state = {}     # État des conversations

# Initialisation de l'application Telegram
application = Application.builder().token(BOT_TOKEN).build()

# ============================================
# HANDLERS DU BOT
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    # Initialiser le solde si nouveau
    if user_id not in user_balances:
        user_balances[user_id] = 0
        user_deposits[user_id] = 0
    
    keyboard = [
        [InlineKeyboardButton("💰 Mon solde", callback_data="balance"),
         InlineKeyboardButton("📝 Corriger", callback_data="correct")],
        [InlineKeyboardButton("💳 Déposer", callback_data="deposit"),
         InlineKeyboardButton("💸 Retirer", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Mon profil", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Bienvenue {first_name} !\n\n"
        "📌 Comment ça marche ?\n"
        "1. Effectuez un dépôt (3000F à 45000F)\n"
        "2. Recevez 2 textes par jour à corriger\n"
        "3. Gagnez 35% de votre dépôt initial par correction réussie\n"
        "4. Retirez vos gains dès 1500F",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "balance":
        balance = user_balances.get(user_id, 0)
        total = user_deposits.get(user_id, 0)
        await query.edit_message_text(
            f"💰 Votre solde actuel : *{balance} FCFA*\n"
            f"📈 Total déposé : *{total} FCFA*",
            parse_mode="Markdown"
        )
    
    elif data == "deposit":
        # Créer les boutons pour les montants
        keyboard = []
        row = []
        for i, amount in enumerate(DEPOSIT_AMOUNTS):
            row.append(InlineKeyboardButton(f"{amount}F", callback_data=f"deposit_{amount}"))
            if (i + 1) % 2 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="start")])
        
        await query.edit_message_text(
            "Choisissez le montant à déposer :",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "start":
        # Retour au menu principal
        keyboard = [
            [InlineKeyboardButton("💰 Mon solde", callback_data="balance"),
             InlineKeyboardButton("📝 Corriger", callback_data="correct")],
            [InlineKeyboardButton("💳 Déposer", callback_data="deposit"),
             InlineKeyboardButton("💸 Retirer", callback_data="withdraw")],
            [InlineKeyboardButton("📊 Mon profil", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"👋 Menu principal",
            reply_markup=reply_markup
        )
    
    elif data.startswith("deposit_"):
        amount = int(data.split("_")[1])
        reference = f"DEP_{user_id}_{uuid.uuid4().hex[:8].upper()}"
        
        # Stocker l'état
        user_state[user_id] = {
            'action': 'waiting_payment',
            'amount': amount,
            'reference': reference
        }
        
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="deposit")]]
        await query.edit_message_text(
            f"💳 *Dépôt de {amount} FCFA*\n\n"
            f"📱 *Instructions :*\n"
            f"1️⃣ Envoyez *{amount} FCFA* au numéro suivant :\n"
            f"   *{DEPOSIT_PHONE}*\n\n"
            f"2️⃣ Une fois le paiement effectué, *envoyez la capture d'écran*\n"
            f"   ou *le code de transaction* dans ce chat.\n\n"
            f"3️⃣ Votre compte sera crédité après vérification.\n\n"
            f"📌 *Référence :* {reference}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "correct":
        if user_balances.get(user_id, 0) < DEPOSIT_AMOUNTS[0]:
            await query.edit_message_text(
                "❌ Vous devez d'abord effectuer un dépôt minimum de 3000 FCFA.\n\n"
                "Utilisez /start pour revenir au menu."
            )
            return
        
        # Textes à corriger (simplifié)
        texts = [
            {"id": 1, "text": "Je m'appel Jean et j'habite à Paris.", "correct": "Je m'appelle Jean et j'habite à Paris."},
            {"id": 2, "text": "Les enfants jouent dans le jardin. Ils sont content.", "correct": "Les enfants jouent dans le jardin. Ils sont contents."},
            {"id": 3, "text": "Elle c'est levé tôt ce matin.", "correct": "Elle s'est levée tôt ce matin."},
            {"id": 4, "text": "Nous allons à la plage avec des amis.", "correct": "Nous allons à la plage avec des amis."}
        ]
        import random
        text_data = random.choice(texts)
        
        user_state[user_id] = {
            'action': 'correcting',
            'text_id': text_data['id'],
            'correct_text': text_data['correct']
        }
        
        keyboard = [[InlineKeyboardButton("🔙 Annuler", callback_data="start")]]
        await query.edit_message_text(
            f"📝 *Texte à corriger*\n\n"
            f"{text_data['text']}\n\n"
            f"Envoyez votre version corrigée :",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "withdraw":
        balance = user_balances.get(user_id, 0)
        if balance < MIN_WITHDRAWAL:
            await query.edit_message_text(
                f"❌ Solde insuffisant. Minimum requis : {MIN_WITHDRAWAL} FCFA\n"
                f"Votre solde : {balance} FCFA\n\n"
                f"Utilisez /start pour revenir au menu."
            )
            return
        
        user_state[user_id] = {'action': 'waiting_withdraw_amount'}
        keyboard = [[InlineKeyboardButton("🔙 Annuler", callback_data="start")]]
        await query.edit_message_text(
            f"💸 Votre solde : *{balance} FCFA*\n\n"
            f"Montant minimum : {MIN_WITHDRAWAL} FCFA\n\n"
            f"Veuillez entrer le montant à retirer :",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "profile":
        balance = user_balances.get(user_id, 0)
        total = user_deposits.get(user_id, 0)
        keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="start")]]
        await query.edit_message_text(
            f"📊 *Votre Profil*\n\n"
            f"👤 ID : {user_id}\n"
            f"💰 Solde : *{balance} FCFA*\n"
            f"📈 Total déposé : *{total} FCFA*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Vérifier si l'utilisateur est dans un état particulier
    if user_id in user_state:
        state = user_state[user_id]
        
        if state.get('action') == 'waiting_payment':
            await update.message.reply_text(
                f"✅ Reçu ! Votre demande sera vérifiée par l'administrateur.\n"
                f"Référence: {state['reference']}\n\n"
                f"Vous recevrez une confirmation sous 24h."
            )
            logger.info(f"Paiement en attente - User: {user_id}, Montant: {state['amount']}")
            # Notifier l'admin (simplifié)
            if ADMIN_ID:
                try:
                    await context.bot.send_message(
                        ADMIN_ID,
                        f"💰 Nouveau dépôt en attente !\n"
                        f"Utilisateur: {user_id}\n"
                        f"Montant: {state['amount']} FCFA\n"
                        f"Réf: {state['reference']}"
                    )
                except:
                    pass
            del user_state[user_id]
        
        elif state.get('action') == 'correcting':
            is_correct = text.strip().lower() == state['correct_text'].lower()
            
            if is_correct:
                total = user_deposits.get(user_id, 0)
                reward = (total * REWARD_PERCENTAGE) / 100
                if reward < 100:  # Minimum si pas de dépôt
                    reward = 100
                user_balances[user_id] = user_balances.get(user_id, 0) + reward
                
                await update.message.reply_text(
                    f"✅ *Correction réussie !*\n\n"
                    f"🎉 Vous avez gagné *{reward:.0f} FCFA* !\n"
                    f"💰 Nouveau solde : *{user_balances[user_id]:.0f} FCFA*\n\n"
                    f"Utilisez /start pour continuer.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ *Correction incorrecte.*\n\n"
                    f"La version correcte était :\n_{state['correct_text']}_\n\n"
                    f"Utilisez /start pour réessayer.",
                    parse_mode="Markdown"
                )
            del user_state[user_id]
        
        elif state.get('action') == 'waiting_withdraw_amount':
            try:
                amount = float(text)
                balance = user_balances.get(user_id, 0)
                
                if amount < MIN_WITHDRAWAL:
                    await update.message.reply_text(f"❌ Minimum : {MIN_WITHDRAWAL} FCFA")
                elif amount > balance:
                    await update.message.reply_text(f"❌ Solde insuffisant. Maximum: {balance} FCFA")
                else:
                    user_state[user_id] = {'action': 'waiting_withdraw_phone', 'amount': amount}
                    await update.message.reply_text(
                        f"📱 Veuillez entrer votre numéro Mobile Money (format: 6XXXXXXXX) :"
                    )
            except ValueError:
                await update.message.reply_text("❌ Montant invalide. Veuillez entrer un nombre.")
        
        elif state.get('action') == 'waiting_withdraw_phone':
            phone = text.strip().replace(' ', '')
            if phone.startswith('6') and len(phone) == 9 and phone.isdigit():
                amount = state['amount']
                user_balances[user_id] -= amount
                await update.message.reply_text(
                    f"✅ *Demande de retrait envoyée !*\n\n"
                    f"💰 Montant : {amount} FCFA\n"
                    f"📱 Numéro : {phone}\n\n"
                    f"Vous serez payé sous 24-48h.\n"
                    f"Utilisez /start pour revenir au menu."
                )
                logger.info(f"Retrait demandé - User: {user_id}, Montant: {amount}, Tél: {phone}")
                # Notifier l'admin
                if ADMIN_ID:
                    try:
                        await context.bot.send_message(
                            ADMIN_ID,
                            f"💸 Nouveau retrait demandé !\n"
                            f"Utilisateur: {user_id}\n"
                            f"Montant: {amount} FCFA\n"
                            f"Tél: {phone}"
                        )
                    except:
                        pass
                del user_state[user_id]
            else:
                await update.message.reply_text("❌ Numéro invalide. Format: 6XXXXXXXX (9 chiffres)")
    
    else:
        await update.message.reply_text("Utilisez /start pour afficher le menu.")

# ============================================
# COMMANDES ADMIN
# ============================================
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        parts = update.message.text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Format: /approve user_id amount")
            return
        
        user_id = int(parts[1])
        amount = float(parts[2])
        
        if user_id in user_balances:
            user_balances[user_id] += amount
            user_deposits[user_id] = user_deposits.get(user_id, 0) + amount
            await update.message.reply_text(f"✅ {amount} FCFA crédités à l'utilisateur {user_id}")
            
            # Notifier l'utilisateur
            try:
                await context.bot.send_message(
                    user_id,
                    f"✅ Votre dépôt de {amount} FCFA a été approuvé !\n"
                    f"💰 Nouveau solde : {user_balances[user_id]} FCFA"
                )
            except:
                pass
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {e}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total_users = len(user_balances)
    total_balance = sum(user_balances.values())
    total_deposits = sum(user_deposits.values())
    active_sessions = len(user_state)
    
    await update.message.reply_text(
        f"📊 *Statistiques*\n\n"
        f"👥 Utilisateurs : {total_users}\n"
        f"💰 Solde total : {total_balance:.0f} FCFA\n"
        f"📈 Dépôts totaux : {total_deposits:.0f} FCFA\n"
        f"🔄 Sessions actives : {active_sessions}",
        parse_mode="Markdown"
    )

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande admin pour envoyer un message à tous les utilisateurs"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("❌ Usage: /broadcast votre message")
        return
    
    sent = 0
    failed = 0
    for user_id in user_balances.keys():
        try:
            await context.bot.send_message(user_id, f"📢 *Annonce*\n\n{message}", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1
    
    await update.message.reply_text(f"✅ Message envoyé à {sent} utilisateurs\n❌ Échec: {failed}")

# ============================================
# SERVEUR FLASK POUR HEALTH CHECK ET WEBHOOK
# ============================================
flask_app = Flask(_name_)
loop = None  # Sera initialisé dans main()

@flask_app.route('/health')
def health():
    """Endpoint pour Render - vérifie que le bot tourne"""
    return jsonify({
        'status': 'healthy',
        'bot_running': True,
        'timestamp': time.time(),
        'users': len(user_balances),
        'active_sessions': len(user_state)
    }), 200

@flask_app.route('/')
def home():
    """Page d'accueil simple"""
    return jsonify({
        'name': 'Moneyman Bot',
        'status': 'online',
        'message': 'Bot Telegram actif ✅',
        'version': '2.0',
        'users': len(user_balances)
    })

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Point d'entrée pour Telegram webhook"""
    if request.method == 'POST':
        try:
            update = Update.de_json(request.get_json(force=True), application.bot)
            asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
            return 'OK', 200
        except Exception as e:
            logger.error(f"Erreur webhook: {e}")
            return 'Error', 500
    return 'Method not allowed', 405

def run_flask():
    """Fonction pour lancer Flask dans un thread"""
    flask_app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ============================================
# FONCTION PRINCIPALE (corrigée)
# ============================================
async def main():
    global loop
    
    # Récupérer la boucle asyncio
    loop = asyncio.get_running_loop()
    
    # Ajouter les handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CommandHandler("approve", admin_approve))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    
    logger.info("🚀 Démarrage du bot avec webhook...")
    logger.info(f"🌐 Port utilisé: {PORT}")
    logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}/webhook")
    
    # Initialiser le bot
    await application.initialize()
    
    # Configurer le webhook (supprime l'ancien s'il existe)
    await application.bot.delete_webhook()
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook configuré: {webhook_url}")
    
    # Démarrer Flask dans un thread séparé
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Serveur Flask démarré (thread séparé)")
    
    # Démarrer l'application
    await application.start()
    
    # Garder le processus en vie
    logger.info("✅ Bot prêt à recevoir des messages!")
    try:
        # Garder le programme en vie avec une boucle
        while True:
            await asyncio.sleep(60)
            # Log périodique pour montrer que le bot est actif
            logger.debug(f"Bot actif - Utilisateurs: {len(user_balances)}, Sessions: {len(user_state)}")
    except asyncio.CancelledError:
        pass
    finally:
        await application.stop()

if _name_ == "_main_":
    try:
        # Vérifications rapides
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN manquant dans les variables d'environnement!")
            exit(1)
        if not WEBHOOK_URL:
            logger.error("❌ RENDER_EXTERNAL_URL manquant! Cette variable est automatiquement fournie par Render.")
            logger.error("   Vérifiez que votre service est bien configuré comme Web Service.")
            exit(1)
        
        logger.info("=" * 50)
        logger.info("🤖 Moneyman Bot - Démarrage")
        logger.info(f"🔑 Token: présent")
        logger.info(f"👤 Admin ID: {ADMIN_ID}")
        logger.info(f"🌐 Port: {PORT}")
        logger.info(f"🔗 Webhook base: {WEBHOOK_URL}")
        logger.info("=" * 50)
        
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot arrêté manuellement")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
