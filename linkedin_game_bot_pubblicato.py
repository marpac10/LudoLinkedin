import logging
import re
from datetime import datetime
from collections import defaultdict
from statistics import mean
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackQueryHandler, CallbackContext
from supabase import create_client
import threading
from flask import Flask, Response, request
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

updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
dp = updater.dispatcher

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
    utente = update.effective_user.first_name


    # Controllo che l'utente abbia caricato tutti e 3 i risultati oggi
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
    oggi = datetime.now().date().isoformat()

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

                # Ordina per tempo convertito in secondi (funzione da definire)
                risultati.sort(key=lambda r: tempo_to_secondi(r['tempo']))
                text += f"🎮 {g}:\n"
                for i, r in enumerate(risultati):
                    text += f"{i+1}. {r['utente']} - {r['tempo']}\n"
                text += "\n"

            query.edit_message_text(text)

        elif scelta == "Campionato":
            # Qui assumo che tu abbia una tabella 'classifica_totale' con questi campi
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
            # Prendiamo la classifica totale come base
            data = supabase.table("classifica_totale")\
                .select("utente, totale, zip, queens, tango")\
                .order("totale", desc=True)\
                .execute().data

            if not data:
                query.edit_message_text("❌ Nessun dato disponibile per il campionato.")
                return

            # Prendiamo i risultati odierni per ogni utente e gioco
            punti_oggi = supabase.table("classifica_giornaliera")\
                .select("utente, gioco, punti")\
                .eq("data", oggi)\
                .execute().data

            # Organizza i risultati in dict[utente][gioco] = punti
            punti_per_utente = {}
            for r in punti_oggi:
                user = r['utente']
                gioco = r['gioco'].capitalize()
                punti = r['punti']
                if user not in punti_per_utente:
                    punti_per_utente[user] = {}
                punti_per_utente[user][gioco] = punti

            text = "🏆 Classifica Campionato (con punti odierni)\n\n"
            for i, r in enumerate(data):
                user = r['utente']
                punti_testo = []
                for g in ['Zip', 'Queens', 'Tango']:
                    t = punti_per_utente.get(user, {}).get(g, 0)
                    punti_testo.append(f"{g}: {t}")
                punti_str = ", ".join(punti_testo)

                text += f"{i+1}. {user} - {r['totale']} pt ({punti_str})\n"

            query.edit_message_text(text)

        else:
            query.edit_message_text("❌ Scelta non riconosciuta.")

    except Exception as e:
        logging.error(f"Errore lettura Supabase: {e}")
        query.edit_message_text("❌ Errore nel recupero classifica.")

@admin_only
def pubblica_classifica(update: Update, context: CallbackContext):
    from datetime import datetime
	global classifica_pubblicata
    
	oggi = datetime.now().date().isoformat()
	giorno_settimana = datetime.now().strftime('%A')  # 'Monday', 'Tuesday', ...
	
	# Imposta il bonus attivo in base al giorno
	bonus_attivo = None
	if giorno_settimana == 'Monday':
		bonus_attivo = "Tango x2"
	elif giorno_settimana == 'Tuesday':
		bonus_attivo = "Queens x2"
	elif giorno_settimana == 'Wednesday':
		bonus_attivo = "Zip x2"
	elif giorno_settimana == 'Thursday':
		bonus_attivo = "Primi x2"
	elif giorno_settimana == 'Friday':
		bonus_attivo = "Tempi veloci x2"
	elif giorno_settimana == 'Saturday':
		bonus_attivo = "Ultimi x2"
	elif giorno_settimana == 'Sunday':
		bonus_attivo = "Top dimezzati"

	
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

    # Dizionario per tenere traccia punti per utente per ogni gioco
    punti_per_utente_per_gioco = {g: {} for g in giochi}

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
            punteggi_posizione = [5,4,3, 2, 1]
            utenti_punteggi = []
            pos = 1
            idx = 0

            while idx < len(risultati) and pos <= 5:
                gruppo = [risultati[idx]]
                tempo_riferimento = tempo_to_secondi(risultati[idx]['tempo'])
                idx += 1
                while idx < len(risultati) and tempo_to_secondi(risultati[idx]['tempo']) == tempo_riferimento:
                    gruppo.append(risultati[idx])
                    idx += 1

                punti_totali = sum(punteggi_posizione[pos-1:pos-1+len(gruppo)])
                punti_per_utente = round(punti_totali / len(gruppo), 2)
				
				# Applica bonus Monday: Tango x2
                if bonus_attivo == "Tango x2" and gioco == "Tango":
                    punti_per_utente *= 2
					
				# Bonus Tuesday: Queens x2
				if bonus_attivo == "Queens x2" and gioco == "Queens":
					punti_per_utente *= 2

				# Bonus Wednesday: Zip x2
				if bonus_attivo == "Zip x2" and gioco == "Zip":
					punti_per_utente *= 2

				# Bonus Thursday: tutti i primi posti x2
				if bonus_attivo == "Primi x2" and pos == 1:
					punti_per_utente *= 2

				# Bonus Friday: tempo sotto soglia
				soglie_tempo = {"Zip": 8, "Tango": 25, "Queens": 15}
				if bonus_attivo == "Tempi veloci x2":
					tempo_sec = tempo_to_secondi(gruppo[0]['tempo'])
					if gioco in soglie_tempo and tempo_sec <= soglie_tempo[gioco]:
						punti_per_utente *= 2

				# Bonus Saturday: ultimi 3 in classifica totale
				if bonus_attivo == "Ultimi x2":
					classifica = supabase.table("classifica_totale").select("utente, totale").order("totale", ascending=True).limit(3).execute().data
					ultimi_utenti = {r['utente'] for r in classifica}
					if gruppo[0]['utente'] in ultimi_utenti:
						punti_per_utente *= 2

				# Bonus Sunday: primi 3 in classifica totale
				if bonus_attivo == "Top dimezzati":
					classifica = supabase.table("classifica_totale").select("utente, totale").order("totale", ascending=False).limit(3).execute().data
					top_utenti = {r['utente'] for r in classifica}
					if gruppo[0]['utente'] in top_utenti:
						punti_per_utente = round(punti_per_utente / 2, 2)




                for utente in gruppo:
                    utenti_punteggi.append({
                        "data": oggi,
                        "gioco": gioco,
                        "posizione": pos,
                        "utente": utente['utente'],
                        "tempo": utente['tempo'],
                        "punti": punti_per_utente
                    })

                    # Salva punti per bonus dopo
                    punti_per_utente_per_gioco[gioco][utente['utente']] = punti_per_utente

                    # Aggiorna la classifica totale
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

    # BONUS: 1 punto extra per chi ha punti in tutti e 3 i giochi
        # BONUS: 1 punto extra per chi ha guadagnato almeno 3 punti in tutti e 3 i giochi
    try:
        # Filtra utenti con almeno 3 punti per ciascun gioco
        utenti_zip = {utente for utente, punti in punti_per_utente_per_gioco['Zip'].items() if punti >= 3}
        utenti_queens = {utente for utente, punti in punti_per_utente_per_gioco['Queens'].items() if punti >= 3}
        utenti_tango = {utente for utente, punti in punti_per_utente_per_gioco['Tango'].items() if punti >= 3}

        # Intersezione: solo chi ha almeno 3 punti in tutti e tre i giochi
        utenti_bonus = utenti_zip & utenti_queens & utenti_tango

        bonus_inserimenti = []
        for utente in utenti_bonus:
            # Inserisci il record bonus nella classifica giornaliera
            bonus_inserimenti.append({
                "data": oggi,
                "gioco": "Bonus",
                "posizione": None,
                "utente": utente,
                "tempo": None,
                "punti": 1
            })

            # Aggiorna classifica totale con +1 punto bonus
            esistente = supabase.table("classifica_totale").select("totale, zip, queens, tango").eq("utente", utente).execute().data
            if esistente:
                riga = esistente[0]
                nuovo_record = {
                    "utente": utente,
                    "totale": riga.get("totale", 0) + 1,
                    "zip": riga.get("zip", 0),
                    "queens": riga.get("queens", 0),
                    "tango": riga.get("tango", 0)
                }
            else:
                nuovo_record = {
                    "utente": utente,
                    "totale": 1,
                    "zip": 0,
                    "queens": 0,
                    "tango": 0
                }
            supabase.table("classifica_totale").upsert(nuovo_record, on_conflict=["utente"]).execute()

        if bonus_inserimenti:
            supabase.table("classifica_giornaliera").insert(bonus_inserimenti).execute()

    except Exception as e:
        logging.error(f"Errore durante l'assegnazione bonus: {e}")
        update.message.reply_text("❌ Errore durante l'assegnazione del bonus extra.")

    update.message.reply_text("✅ Classifiche pubblicate! Bonus assegnati solo ai top 3 di ogni gioco.")




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


    
    
    dp.add_handler(CommandHandler("classifica", classifica_command))
    dp.add_handler(CommandHandler("pubblica", pubblica_classifica, pass_args=True))
  #  dp.add_handler(CommandHandler("campionato", campionato_command))
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


webserver = Flask(__name__)




@webserver.route('/', methods=['GET'])
def home():
    return "Bot attivo e online!"


@webserver.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    from telegram import Update
    from telegram.ext import Dispatcher

    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher = Dispatcher(updater.bot, None, workers=0, use_context=True)

    dispatcher.add_handler(CommandHandler("classifica", classifica_command))
    dispatcher.add_handler(CommandHandler("pubblica", pubblica_classifica))
    dispatcher.add_handler(CommandHandler("reset", reset_classifica))
    dispatcher.add_handler(CommandHandler("info", info_command))
    dispatcher.add_handler(CallbackQueryHandler(mostra_classifica))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    dispatcher.process_update(update)

    return "OK", 200  # ✅ Questo è importante per evitare il 500


def home():
    return Response("Bot attivo", status=200, mimetype='text/plain')




import threading

def run_flask():
    webserver.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    main()  # qui parte anche il bot Telegram
