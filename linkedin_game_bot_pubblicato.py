import logging
import re
from datetime import datetime
from collections import defaultdict
from statistics import mean
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackQueryHandler, CallbackContext
from supabase import create_client
import threading
from flask import Flask, Response
from functools import wraps



# 👉 Inserisci qui il tuo TOKEN
#TELEGRAM_BOT_TOKEN = '7749557927:AAEqGqcKa7Hd_Ow3WibkIUrz1bJUnvVHLZ0'

# 👉 Supabase credentials
#SUPABASE_URL = "https://kfyihmqughvjgdioyunu.supabase.co"
#SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtmeWlobXF1Z2h2amdkaW95dW51Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA4ODM2MzMsImV4cCI6MjA2NjQ1OTYzM30.QB-bdTWKchIJPQNQ119zx5Smc20YbUoArtFgWadeGqs"


import os

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "2510")  
ADMINS = ["mario"]  


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

classifica_pubblicata = False

# 🔧 Log
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

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
    # Verifica se utente è in lista admin
    if user_name in ADMINS:
        return True
    # Verifica se password admin è passata come argomento al comando
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
            "tempo": tempo
        }).execute()
        return True
    except Exception as e:
        logging.error(f"Errore salvataggio Supabase: {e}")
        return False

def handle_message(update, context):
    user = update.effective_user.first_name
    text = update.message.text

    oggi = datetime.now().date().isoformat()

    # Controlla se la classifica è già pubblicata per oggi
    check_pubblicata = supabase.table("classifica_giornaliera")\
        .select("id")\
        .eq("data", oggi)\
        .limit(1)\
        .execute().data

    if check_pubblicata:
        update.message.reply_text("❌ Non è più possibile inviare risultati per oggi: classifica già pubblicata.")
        return

    gioco, tempo = parse_message(text)

    if gioco and tempo:
        # Controlla se l'utente ha già inviato un risultato per questo gioco oggi
        existing = supabase.table("risultati_giornalieri")\
            .select("id")\
            .eq("utente", user)\
            .eq("gioco", gioco)\
            .gte("timestamp", oggi + "T00:00:00Z")\
            .lte("timestamp", oggi + "T23:59:59Z")\
            .execute().data

        if existing:
            update.message.reply_text(f"⚠️ Hai già inviato un risultato per {gioco} oggi.")
            return

        successo = salva_su_supabase(user, gioco, tempo)
        if successo:
            update.message.reply_text(f"✅ Registrato: {gioco} in {tempo}, {user}!")
        else:
            update.message.reply_text("❌ Errore nel salvataggio. Riprova più tardi.")
    else:
        update.message.reply_text("⚠️ Messaggio non valido. Scrivi il nome del gioco e il tempo (es: Queens 1:23)")

def classifica_command(update: Update, context: CallbackContext):
    oggi = datetime.now().date().isoformat()
    user_id = update.effective_user.id

    # Controllo pubblicazione classifica (come prima)
    check_pubblicata = supabase.table("classifica_giornaliera")\
        .select("id")\
        .eq("data", oggi)\
        .limit(1)\
        .execute().data

    if not check_pubblicata:
        giochi = ["Zip", "Queens", "Tango"]
        giochi_fatti = []

        for gioco in giochi:
            risultati = supabase.table("risultati_giornalieri")\
                .select("id")\
                .eq("user_id", user_id)\
                .eq("gioco", gioco)\
                .gte("timestamp", oggi + "T00:00:00Z")\
                .lte("timestamp", oggi + "T23:59:59Z")\
                .limit(1)\
                .execute().data
            if risultati:
                giochi_fatti.append(gioco)

        if len(giochi_fatti) < 3:
            update.message.reply_text(
                "⚠️ Per vedere la classifica prima della pubblicazione, devi prima caricare tutti e 3 i giochi: Zip, Queens e Tango."
            )
            return

    # Nuovo menu con 3 bottoni
    keyboard = [
        [InlineKeyboardButton("🏆 Classifica Tutte", callback_data='Tutte')],
        [InlineKeyboardButton("🏆 Classifica Campionato", callback_data='Campionato')],
        [InlineKeyboardButton("🏆 Campionato (oggi)", callback_data='Campionato_oggi')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("📊 Quale classifica vuoi vedere?", reply_markup=reply_markup)


def mostra_classifica(update: Update, context: CallbackContext):
    query = update.callback_query
    scelta = query.data
    query.answer()
    oggi = datetime.now().date().isoformat()

    try:
        if scelta == "Tutte":
            text = "📊 Classifiche di oggi\n\n"
            for g in ['Zip', 'Queens', 'Tango']:
                risultati = supabase.table("risultati_giornalieri")\
                    .select("utente, tempo")\
                    .eq("gioco", g)\
                    .gte("timestamp", oggi + "T00:00:00Z")\
                    .lte("timestamp", oggi + "T23:59:59Z")\
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
            # Classifica totale (campionato)
            data = supabase.table("classifica_totale")\
                .select("utente, totale, zip, queens, tango")\
                .order("totale", desc=True)\
                .execute().data

            if not data:
                query.edit_message_text("❌ Nessun dato disponibile per il campionato.")
                return

            text = "🏆 Classifica Campionato (totale)\n\n"
            for i, r in enumerate(data):
                text += f"{i+1}. {r['utente']} - {r['totale']} pt (Zip: {r['zip']}, Queens: {r['queens']}, Tango: {r['tango']})\n"

            query.edit_message_text(text)

        elif scelta == "Campionato_oggi":
            # Qui mostriamo classifica totale con i tempi odierni tra parentesi
            data = supabase.table("classifica_totale")\
                .select("utente, totale, zip, queens, tango")\
                .order("totale", desc=True)\
                .execute().data

            if not data:
                query.edit_message_text("❌ Nessun dato disponibile per il campionato.")
                return

            # Prendiamo i risultati odierni per tutti i giochi, raggruppati per utente e gioco
            risultati_oggi = supabase.table("risultati_giornalieri")\
                .select("utente, gioco, tempo")\
                .gte("timestamp", oggi + "T00:00:00Z")\
                .lte("timestamp", oggi + "T23:59:59Z")\
                .execute().data

            # Organizza i tempi odierni per utente e gioco
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
                # Prepara stringa tempi odierni (o '-' se non presente)
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
    global classifica_pubblicata
    oggi = datetime.now().date().isoformat()
    check_pubblicata = supabase.table("classifica_giornaliera")\
        .select("id")\
        .eq("data", oggi)\
        .limit(1)\
        .execute().data

    if check_pubblicata:
        update.message.reply_text("⚠️ Classifica già pubblicata oggi.")
        return

    giochi = ['Zip', 'Queens', 'Tango']
    classifica_pubblicata = True

    for gioco in giochi:
        try:
            risultati = supabase.table("risultati_giornalieri")\
                .select("utente, tempo")\
                .eq("gioco", gioco)\
                .gte("timestamp", oggi + "T00:00:00Z")\
                .lte("timestamp", oggi + "T23:59:59Z")\
                .execute().data

            if not risultati:
                continue

            risultati.sort(key=lambda r: tempo_to_secondi(r['tempo']))
            punteggi_posizione = [3, 2, 1]
            utenti_punteggi = []
            pos = 1
            idx = 0

            while idx < len(risultati) and pos <= 3:
                gruppo = [risultati[idx]]
                tempo_riferimento = tempo_to_secondi(risultati[idx]['tempo'])
                idx += 1
                while idx < len(risultati) and tempo_to_secondi(risultati[idx]['tempo']) == tempo_riferimento:
                    gruppo.append(risultati[idx])
                    idx += 1

                punti_totali = sum(punteggi_posizione[pos-1:pos-1+len(gruppo)])
                punti_per_utente = round(punti_totali / len(gruppo), 2)

                for utente in gruppo:
                    utenti_punteggi.append({
                        "data": oggi,
                        "gioco": gioco,
                        "posizione": pos,
                        "utente": utente['utente'],
                        "tempo": utente['tempo'],
                        "punti": punti_per_utente
                    })

                    esistente = supabase.table("classifica_totale").select("totale, zip, queens, tango").eq("utente", utente['utente']).execute().data
                    if esistente:
                        riga = esistente[0]
                        nuovo_record = {
                            "utente": utente['utente'],
                            "totale": riga.get("totale", 0) + punti_per_utente,
                            "zip": riga.get("zip", 0) + punti_per_utente if gioco.lower() == "zip" else riga.get("zip", 0),
                            "queens": riga.get("queens", 0) + punti_per_utente if gioco.lower() == "queens" else riga.get("queens", 0),
                            "tango": riga.get("tango", 0) + punti_per_utente if gioco.lower() == "tango" else riga.get("tango", 0)
                        }
                    else:
                        nuovo_record = {
                            "utente": utente['utente'],
                            "totale": punti_per_utente,
                            "zip": punti_per_utente if gioco.lower() == "zip" else 0,
                            "queens": punti_per_utente if gioco.lower() == "queens" else 0,
                            "tango": punti_per_utente if gioco.lower() == "tango" else 0
                        }
                    supabase.table("classifica_totale").upsert(nuovo_record, on_conflict=["utente"]).execute()

                pos += len(gruppo)

            if utenti_punteggi:
                supabase.table("classifica_giornaliera").insert(utenti_punteggi).execute()

        except Exception as e:
            logging.error(f"Errore pubblicazione classifica per {gioco}: {e}")
            update.message.reply_text(f"❌ Errore nel calcolo della classifica per {gioco}.")

    update.message.reply_text("✅ Classifiche pubblicate!")

# def campionato_command(update: Update, context: CallbackContext):
    # try:
        # data = supabase.table("classifica_totale")\
            # .select("utente, totale, zip, queens, tango")\
            # .order("totale", desc=True)\
            # .execute().data

        # if not data:
            # update.message.reply_text("❌ Nessun dato disponibile per il campionato.")
            # return

        # text = "🏆 Classifica Campionato\n\n"
        # for i, r in enumerate(data):
            # text += f"{i+1}. {r['utente']} - {r['totale']} pt (Zip: {r['zip']}, Queens: {r['queens']}, Tango: {r['tango']})\n"

        # update.message.reply_text(text)

    # except Exception as e:
        # logging.error(f"Errore nel recupero classifica totale: {e}")
        # update.message.reply_text("❌ Errore nel recupero della classifica totale.")

@admin_only
def reset_classifica(update: Update, context: CallbackContext):
    try:
        supabase.table("classifica_totale").delete().neq("utente", "").execute()
        update.message.reply_text("🔄 Classifica totale azzerata con successo.")
    except Exception as e:
        logging.error(f"Errore durante il reset della classifica totale: {e}")
        update.message.reply_text("❌ Errore durante il reset della classifica totale.")

def info_command(update: Update, context: CallbackContext):
    text = (
        "ℹ️ Comandi disponibili:\n"
        "/classifica – Mostra le classifiche giornaliere (Tango, Zip, Queens, Tutte).\n"
        "/pubblica – Calcola e pubblica la classifica del giorno.\n"
        "/campionato – Mostra la classifica totale (somma di tutti i giorni).\n"
        "/reset – Azzera completamente la classifica totale.\n\n"
        "Puoi anche inviare un messaggio tipo 'Queens 1:23' per registrare un risultato."
    )
    update.message.reply_text(text)


def is_orario_attivo():
    ora = datetime.now().hour
    return 8 <= ora < 22  # attivo solo tra le 8:00 e le 19:59



def main():

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    
    
    dp.add_handler(CommandHandler("classifica", classifica_command))
    dp.add_handler(CommandHandler("pubblica", pubblica_classifica, pass_args=True))
    dp.add_handler(CommandHandler("campionato", campionato_command))
    dp.add_handler(CommandHandler("reset", reset_classifica, pass_args=True))
    dp.add_handler(CommandHandler("info", info_command))
    dp.add_handler(CallbackQueryHandler(mostra_classifica))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_webhook(
    listen="0.0.0.0",
    port=8080,
    url_path=TELEGRAM_BOT_TOKEN,
    webhook_url=os.environ.get("RENDER_EXTERNAL_URL") + "/" + TELEGRAM_BOT_TOKEN,
)

    print("🤖 Bot attivo.")
    updater.idle()


webserver = Flask('')


@webserver.route('/')
@webserver.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    from telegram import Update
    from telegram.ext import Dispatcher

    update = Update.de_json(request.get_json(force=True), updater.bot)
    dp = updater.dispatcher
    dispatcher = Dispatcher(updater.bot, None, workers=0, use_context=True)
    dispatcher.add_handler(CommandHandler("classifica", classifica_command))
    dispatcher.add_handler(CommandHandler("pubblica", pubblica_classifica))
    # dispatcher.add_handler(CommandHandler("campionato", campionato_command))
    dispatcher.add_handler(CommandHandler("reset", reset_classifica))
    dispatcher.add_handler(CommandHandler("info", info_command))
    dispatcher.add_handler(CallbackQueryHandler(mostra_classifica))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    dispatcher.process_update(update)
    return "OK"

def home():
    return Response("Bot attivo", status=200, mimetype='text/plain')


def run_flask():
    webserver.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    main()
