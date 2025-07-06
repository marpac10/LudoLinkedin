import logging
import re
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackQueryHandler, CallbackContext
from supabase import create_client
import os
from functools import wraps

# Configurazione da environment
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "2510")
ADMINS = ["mario"]  # usa sempre first_name minuscolo per gli admin

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

def tempo_to_secondi(tempo):
    m, s = map(int, tempo.split(":"))
    return m * 60 + s

def parse_message(text):
    gioco_match = re.search(r'\b(zip|queens|tango)\b', text, re.IGNORECASE)
    gioco = gioco_match.group(1).capitalize() if gioco_match else None
    tempo_match = re.search(r'\b\d{1,2}:\d{2}\b', text)
    tempo = tempo_match.group(0) if tempo_match else None
    return gioco, tempo

def is_admin(update, context):
    user_name = update.effective_user.first_name.lower()
    if user_name in ADMINS:
        return True
    if context.args and context.args[0] == ADMIN_PASSWORD:
        return True
    return False

def admin_only(func):
    @wraps(func)
    def wrapper(update, context, *args, **kwargs):
        if not is_admin(update, context):
            update.message.reply_text("❌ Comando riservato agli admin. Usa /comando password_segreta")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

def salva_su_supabase(utente, gioco, tempo):
    try:
        supabase.table("risultati_giornalieri").insert({
            "utente": utente,
            "gioco": gioco,
            "tempo": tempo,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }).execute()
        return True
    except Exception as e:
        logging.error(f"Errore salvataggio Supabase: {e}")
        return False

def handle_message(update, context):
    user = update.effective_user.first_name
    text = update.message.text
    oggi = datetime.utcnow().date().isoformat()

    # Controllo classifica già pubblicata oggi
    check_pubblicata = supabase.table("classifica_giornaliera")\
        .select("id")\
        .eq("data", oggi)\
        .limit(1).execute().data
    if check_pubblicata:
        update.message.reply_text("❌ Non è più possibile inviare risultati per oggi: classifica già pubblicata.")
        return

    gioco, tempo = parse_message(text)
    if not (gioco and tempo):
        update.message.reply_text("⚠️ Messaggio non valido. Scrivi il nome del gioco e il tempo (es: Queens 1:23)")
        return

    # Controllo se l'utente ha già inviato risultato per questo gioco oggi
    existing = supabase.table("risultati_giornalieri")\
        .select("id")\
        .eq("utente", user)\
        .eq("gioco", gioco)\
        .gte("timestamp", f"{oggi}T00:00:00Z")\
        .lte("timestamp", f"{oggi}T23:59:59Z")\
        .execute().data

    if existing:
        update.message.reply_text(f"⚠️ Hai già inviato un risultato per {gioco} oggi.")
        return

    successo = salva_su_supabase(user, gioco, tempo)
    if successo:
        update.message.reply_text(f"✅ Registrato: {gioco} in {tempo}, {user}!")
    else:
        update.message.reply_text("❌ Errore nel salvataggio. Riprova più tardi.")

def classifica_command(update: Update, context: CallbackContext):
    oggi = datetime.utcnow().date().isoformat()
    utente = update.effective_user.first_name

    giochi = ["Zip", "Queens", "Tango"]
    giochi_fatti = []

    for gioco in giochi:
        risultati = supabase.table("risultati_giornalieri")\
            .select("id")\
            .eq("utente", utente)\
            .eq("gioco", gioco)\
            .gte("timestamp", f"{oggi}T00:00:00Z")\
            .lte("timestamp", f"{oggi}T23:59:59Z")\
            .limit(1)\
            .execute().data
        if risultati:
            giochi_fatti.append(gioco)

    if len(giochi_fatti) < 3:
        update.message.reply_text(
            "⚠️ Per vedere la classifica prima della pubblicazione, devi prima caricare tutti e 3 i giochi: Zip, Queens e Tango."
        )
        return

    keyboard = [
        [InlineKeyboardButton("🏆 Classifica Tutte", callback_data='Tutte')],
        [InlineKeyboardButton("🏆 Classifica Campionato", callback_data='Campionato')],
        [InlineKeyboardButton("🏆 Campionato (oggi)", callback_data='Campionato_oggi')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("📊 Quale classifica vuoi vedere?", reply_markup=reply_markup)

def mostra_classifica(update: Update, context: CallbackContext):
    query = update.callback_query
    scelta = query.data
    query.answer()
    oggi = datetime.utcnow().date().isoformat()

    try:
        if scelta == "Tutte":
            text = "📊 Classifiche di oggi\n\n"
            for g in ['Zip', 'Queens', 'Tango']:
                risultati = supabase.table("risultati_giornalieri")\
                    .select("utente, tempo")\
                    .eq("gioco", g)\
                    .gte("timestamp", f"{oggi}T00:00:00Z")\
                    .lte("timestamp", f"{oggi}T23:59:59Z")\
                    .execute().data

                if not risultati:
                    text += f"❌ Nessun risultato per {g}.\n\n"
                    continue

                risultati.sort(key=lambda r: tempo_to_secondi(r['tempo']))
                text += f"🎮 {g}:\n"
                for i, r in enumerate(risultati):
                    text += f"{i+1}. {r['utente']} - {r['tempo']}\n"
                text += "\n"

            query.edit_message_text(text)

        elif scelta == "Campionato":
            data = supabase.table("classifica_totale")\
                .select("utente, totale, zip, queens, tango")\
                .order("totale", desc=True)\
                .execute().data

            if not data:
                query.edit_message_text("❌ Nessun dato disponibile per il campionato.")
                return

            text = "🏆 Classifica Campionato (totale)\n\n"
            for i, r in enumerate(data):
                text += (f"{i+1}. {r['utente']} - {r['totale']} pt "
                         f"(Zip: {r['zip']}, Queens: {r['queens']}, Tango: {r['tango']})\n")

            query.edit_message_text(text)

        elif scelta == "Campionato_oggi":
            data = supabase.table("classifica_totale")\
                .select("utente, totale, zip, queens, tango")\
                .order("totale", desc=True)\
                .execute().data

            if not data:
                query.edit_message_text("❌ Nessun dato disponibile per il campionato.")
                return

            risultati_oggi = supabase.table("risultati_giornalieri")\
                .select("utente, gioco, tempo")\
                .gte("timestamp", f"{oggi}T00:00:00Z")\
                .lte("timestamp", f"{oggi}T23:59:59Z")\
                .execute().data

            tempi_per_utente = {}
            for r in risultati_oggi:
                user = r['utente']
                gioco = r['gioco']
                tempo = r['tempo']
                if user not in tempi_per_utente:
                    tempi_per_utente[user] = {}
                tempi_per_utente[user][gioco] = tempo

            text = "🏆 Classifica Campionato (con tempi odierni)\n\n"
            for i, r in enumerate(data):
                user = r['utente']
                tempi_testo = []
                for g in ['Zip', 'Queens', 'Tango']:
                    t = tempi_per_utente.get(user, {}).get(g, '-')
                    tempi_testo.append(f"{g}: {t}")
                tempi_str = ", ".join(tempi_testo)

                text += f"{i+1}. {user} - {r['totale']} pt ({tempi_str})\n"

            query.edit_message_text(text)

        else:
            query.edit_message_text("❌ Scelta non riconosciuta.")

    except Exception as e:
        logging.error(f"Errore lettura Supabase: {e}")
        query.edit_message_text("❌ Errore nel recupero classifica.")

@admin_only
def pubblica_classifica(update: Update, context: CallbackContext):
    oggi = datetime.utcnow().date().isoformat()

    # Controlla se già pubblicata
    check_pubblicata = supabase.table("classifica_giornaliera")\
        .select("id")\
        .eq("data", oggi)\
        .limit(1).execute().data

    if check_pubblicata:
        update.message.reply_text("⚠️ Classifica già pubblicata oggi.")
        return

    giochi = ['Zip', 'Queens', 'Tango']

    for gioco in giochi:
        try:
            risultati = supabase.table("risultati_giornalieri")\
                .select("utente, tempo")\
                .eq("gioco", gioco)\
                .gte("timestamp", f"{oggi}T00:00:00Z")\
                .lte("timestamp", f"{oggi}T23:59:59Z")\
                .execute().data

            if not risultati:
                continue

            risultati.sort(key=lambda r: tempo_to_secondi(r['tempo']))

            for i, r in enumerate(risultati):
                punti = len(risultati) - i
                supabase.table("classifica_giornaliera").insert({
                    "data": oggi,
                    "utente": r['utente'],
                    "gioco": gioco,
                    "posizione": i + 1,
                    "punti": punti
                }).execute()

        except Exception as e:
            logging.error(f"Errore pubblica_classifica per {gioco}: {e}")
            update.message.reply_text(f"Errore nella pubblicazione per {gioco}")
            return

    # Calcolo classifica totale aggiornata
    try:
        totale_agg = supabase.table("classifica_giornaliera")\
            .select("utente, gioco, punti")\
            .gte("data", oggi)\
            .lte("data", oggi)\
            .execute().data

        punti_per_utente = {}

        for r in totale_agg:
            ut = r['utente']
            gioco = r['gioco'].lower()
            punti = r['punti']
            if ut not in punti_per_utente:
                punti_per_utente[ut] = {"zip": 0, "queens": 0, "tango": 0, "totale": 0}
            punti_per_utente[ut][gioco] += punti
            punti_per_utente[ut]['totale'] += punti

        # Prima svuota o aggiorna tutta la tabella classifica_totale per oggi
        supabase.table("classifica_totale").delete().neq("utente", "").execute()

        # Inserisci nuova classifica_totale
        for ut, p in punti_per_utente.items():
            supabase.table("classifica_totale").insert({
                "utente": ut,
                "zip": p['zip'],
                "queens": p['queens'],
                "tango": p['tango'],
                "totale": p['totale']
            }).execute()

        supabase.table("classifica_giornaliera").insert({
            "data": oggi,
            "utente": "Sistema",
            "gioco": "Pubblicazione",
            "posizione": 0,
            "punti": 0
        }).execute()

        update.message.reply_text("✅ Classifica pubblicata con successo!")

    except Exception as e:
        logging.error(f"Errore calcolo classifica totale: {e}")
        update.message.reply_text("❌ Errore nel calcolo della classifica totale.")

def reset_giornaliero(update: Update, context: CallbackContext):
    oggi = datetime.utcnow().date().isoformat()
    supabase.table("risultati_giornalieri").delete()\
        .gte("timestamp", f"{oggi}T00:00:00Z")\
        .lte("timestamp", f"{oggi}T23:59:59Z").execute()
    update.message.reply_text("🗑️ Risultati di oggi resettati.")

def info_command(update: Update, context: CallbackContext):
    update.message.reply_text("🤖 Bot per gestione classifiche giochi LinkedIn.")

def get_user_id(update: Update):
    # Uniforma user id per salvataggi e ricerche
    return update.effective_user.first_name

def main():
    updater = Updater(TELEGRAM_BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("classifica", classifica_command))
    dp.add_handler(CallbackQueryHandler(mostra_classifica))
    dp.add_handler(CommandHandler("pubblica", pubblica_classifica))
    dp.add_handler(CommandHandler("reset", reset_giornaliero))
    dp.add_handler(CommandHandler("info", info_command))

    logging.info("Bot pronto e in ascolto...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
