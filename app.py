"""
app.py — ZZPbot Flask Server
Routes: / | /intake | /download/monitor | /webhook | /activity | /upload | /health
"""

import io
import json
import logging
import os
import smtplib
import threading
import uuid
import zipfile
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from flask import (Flask, jsonify, redirect, render_template,
                   request, send_file, url_for)

load_dotenv()

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "zzpbot-dev-secret-change-me")

BASE_DIR    = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"
UPLOADS_DIR  = BASE_DIR / "uploads"
REPORTS_DIR  = BASE_DIR / "reports"

for d in [PROFILES_DIR, UPLOADS_DIR, REPORTS_DIR]:
    d.mkdir(exist_ok=True)

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:5000")


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def save_profile(profile: dict) -> None:
    path = PROFILES_DIR / f"{profile['client_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def load_profile(client_id: str) -> dict | None:
    path = PROFILES_DIR / f"{client_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def send_report_email(profile: dict, report_path: str) -> bool:
    """Stuur het PDF-rapport naar de founder en NextEnabler."""
    smtp_host  = os.getenv("SMTP_HOST")
    smtp_port  = int(os.getenv("SMTP_PORT", 587))
    smtp_user  = os.getenv("SMTP_USER")
    smtp_pass  = os.getenv("SMTP_PASS")

    if not all([smtp_host, smtp_user, smtp_pass]):
        logger.warning("SMTP niet geconfigureerd — e-mail overgeslagen")
        return False

    naam    = profile.get("naam", "Klant")
    client_id = profile.get("client_id", "?")
    uurtarief = profile.get("uurtarief", 0)

    recipients = [
        r for r in [
            os.getenv("FOUNDER_EMAIL"),
            os.getenv("NEXTENABLER_EMAIL"),
        ] if r
    ]
    if not recipients:
        logger.warning("Geen e-mailontvangers geconfigureerd")
        return False

    subject = f"ZZPbot Rapport — {naam} (ID: {client_id})"
    body = (
        f"Nieuw ZZPbot rapport gegenereerd!\n\n"
        f"Klant:     {naam}\n"
        f"Type:      {profile.get('bedrijfstype', '-')}\n"
        f"Uurtarief: €{uurtarief}\n"
        f"Client ID: {client_id}\n"
        f"Datum:     {datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
        f"NextEnabler link: {os.getenv('NEXTENABLER_URL', 'https://nextenabler.com/scan')}?ref={client_id}\n"
    )

    try:
        msg = MIMEMultipart()
        msg["From"]    = smtp_user
        msg["To"]      = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Bijlage
        with open(report_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="zzpbot_rapport_{naam.lower().replace(" ", "_")}.pdf"',
        )
        msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())

        logger.info(f"Rapport gemaild naar {recipients}")
        return True

    except Exception as e:
        logger.error(f"E-mail fout: {e}")
        return False


def generate_and_cleanup(client_id: str, activity_data: dict) -> str | None:
    """
    Genereer PDF-rapport en verwijder ruwe data nadien.
    Geeft het pad naar de PDF terug, of None bij fout.
    """
    from analyzer import analyze_activity
    from pdf_generator import generate_report

    profile = load_profile(client_id)
    if not profile:
        logger.error(f"Profiel {client_id} niet gevonden")
        return None

    try:
        logger.info(f"Analyse starten voor {client_id}")
        analysis = analyze_activity(profile, activity_data)

        report_path = str(REPORTS_DIR / f"{client_id}.pdf")
        logger.info(f"PDF genereren: {report_path}")
        generate_report(profile, activity_data, analysis, report_path)

        # E-mail versturen
        send_report_email(profile, report_path)

        logger.info(f"Rapport klaar: {report_path}")
        return report_path

    except Exception as e:
        logger.exception(f"Fout bij rapportgeneratie voor {client_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "GET":
        return render_template("intake.html")

    # POST — verwerk intakeformulier
    f = request.form
    naam = f.get("naam", "").strip()
    if not naam:
        return render_template("intake.html", error="Vul je naam in.")

    client_id = str(uuid.uuid4())[:8].upper()

    # Bekende tools als lijst
    tools_raw = f.get("huidige_tools", "")
    tools_list = [t.strip() for t in tools_raw.split(",") if t.strip()]

    profile = {
        "client_id":        client_id,
        "naam":             naam,
        "email":            f.get("email", "").strip(),
        "bedrijfstype":     f.get("bedrijfstype", "").strip(),
        "huidige_tools":    tools_raw,
        "tools_list":       tools_list,
        "uurtarief":        float(f.get("uurtarief", 85) or 85),
        "maatwerksoftware": f.get("maatwerksoftware", "").strip(),
        "werktijden":       f.get("werktijden", "09:00-17:00").strip(),
        "uitdagingen":      f.get("uitdagingen", "").strip(),
        "aangemaakt":       datetime.now().isoformat(),
    }
    save_profile(profile)

    # Monitor-configbestand
    config = {
        "client_id":        client_id,
        "naam":             naam,
        "server_url":       SERVER_URL,
        "maatwerksoftware": profile["maatwerksoftware"],
        "werktijden":       profile["werktijden"],
    }
    config_name = f"zzpbot_{naam.lower().replace(' ', '_')}.json"
    config_path = UPLOADS_DIR / config_name
    with open(config_path, "w", encoding="utf-8") as fp:
        json.dump(config, fp, indent=2, ensure_ascii=False)

    logger.info(f"Nieuw profiel aangemaakt: {client_id} ({naam})")
    return redirect(url_for("succes", client_id=client_id))


@app.route("/succes/<client_id>")
def succes(client_id: str):
    """Toon succes-pagina na intake met download-knop voor het startpakket."""
    client_id = client_id.upper()
    profile = load_profile(client_id)
    if not profile:
        return redirect(url_for("intake"))
    return render_template("succes.html", profile=profile, client_id=client_id)


@app.route("/download/bundle/<client_id>")
def download_bundle(client_id: str):
    """
    Maak een ZIP-startpakket met de monitor config + (optioneel) monitor.exe.
    Eén download, dubbelklikken, klaar.
    """
    client_id = client_id.upper()
    profile = load_profile(client_id)
    if not profile:
        return jsonify({"error": "Client ID niet gevonden"}), 404

    naam = profile.get("naam", "klant")
    config_name = f"zzpbot_{naam.lower().replace(' ', '_')}.json"

    # Config JSON opnieuw opbouwen
    config = {
        "client_id":        client_id,
        "naam":             naam,
        "server_url":       SERVER_URL,
        "maatwerksoftware": profile.get("maatwerksoftware", ""),
        "werktijden":       profile.get("werktijden", "09:00-17:00"),
    }
    config_bytes = json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8")

    # ZIP in-memory aanmaken
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(config_name, config_bytes)

        # README voor de gebruiker
        readme = (
            f"ZZPbot Startpakket — {naam}\n"
            "================================\n\n"
            "Stappen:\n"
            f"1. Zet monitor.exe en {config_name} in dezelfde map\n"
            "2. Dubbelklik op monitor.exe\n"
            "3. Laat het een week draaien terwijl je normaal werkt\n"
            "4. Het monitoringbestand wordt automatisch bijgehouden\n\n"
            f"Je Client ID: {client_id}\n"
            f"Upload na een week via: {SERVER_URL}/upload\n\n"
            "Vragen? Neem contact op via NextEnabler.com\n"
        )
        zf.writestr("LEES_MIJ.txt", readme.encode("utf-8"))

        # Voeg monitor.exe toe als die beschikbaar is
        exe_path = BASE_DIR / "dist" / "monitor.exe"
        if exe_path.exists():
            zf.write(exe_path, "monitor.exe")

    buf.seek(0)
    zip_name = f"zzpbot_startpakket_{naam.lower().replace(' ', '_')}.zip"
    return send_file(
        buf,
        as_attachment=True,
        download_name=zip_name,
        mimetype="application/zip",
    )


@app.route("/download/monitor")
def download_monitor():
    """Serveert de monitor.exe (alleen aanwezig na PyInstaller build)."""
    exe_path = BASE_DIR / "dist" / "monitor.exe"
    if not exe_path.exists():
        return (
            "<h2>Monitor nog niet beschikbaar</h2>"
            "<p>Bouw de monitor eerst met: <code>pyinstaller build_monitor.spec</code></p>",
            404,
        )
    return send_file(exe_path, as_attachment=True, download_name="monitor.exe")


@app.route("/activity", methods=["POST"])
def activity():
    """Ontvangt live activiteitsdata van de monitor (elke 5 minuten)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Geen JSON data"}), 400

    client_id = data.get("client_id")
    if not client_id:
        return jsonify({"error": "client_id ontbreekt"}), 400

    # Opslaan in uploads/{client_id}/
    act_dir = UPLOADS_DIR / client_id
    act_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (act_dir / f"live_{ts}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.debug(f"Live data ontvangen: {client_id}")
    return jsonify({"status": "ok", "ontvangen": ts})


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    # POST — verwerk geüploade monitoring data
    client_id = request.form.get("client_id", "").strip().upper()
    if not client_id:
        return render_template("upload.html", error="Voer je Client ID in.")

    if "data_file" not in request.files or not request.files["data_file"].filename:
        return render_template("upload.html", error="Selecteer je monitoring_data.json bestand.")

    profile = load_profile(client_id)
    if not profile:
        return render_template(
            "upload.html",
            error=f"Client ID '{client_id}' niet gevonden. Controleer je ID.",
        )

    # Lees geüploade data
    try:
        raw = request.files["data_file"].read()
        activity_data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        return render_template("upload.html", error=f"Ongeldig bestand: {e}")

    # Genereer rapport (synchroon zodat we de PDF kunnen terugsturen)
    report_path = generate_and_cleanup(client_id, activity_data)

    if not report_path or not Path(report_path).exists():
        return render_template(
            "upload.html",
            error="Rapport kon niet worden gegenereerd. Probeer opnieuw of neem contact op.",
        )

    naam = profile.get("naam", "klant")
    download_name = f"zzpbot_rapport_{naam.lower().replace(' ', '_')}.pdf"
    return send_file(
        report_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf",
    )


@app.route("/rapport/<client_id>")
def download_rapport(client_id: str):
    """Directe link om een al gegenereerd rapport te downloaden."""
    client_id = client_id.upper()
    report_path = REPORTS_DIR / f"{client_id}.pdf"
    if not report_path.exists():
        return jsonify({"error": "Rapport niet gevonden"}), 404
    profile = load_profile(client_id) or {}
    naam = profile.get("naam", "klant")
    return send_file(
        report_path,
        as_attachment=True,
        download_name=f"zzpbot_rapport_{naam.lower().replace(' ', '_')}.pdf",
        mimetype="application/pdf",
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    """WhatsApp webhook via Twilio (optioneel)."""
    try:
        from twilio.twiml.messaging_response import MessagingResponse
        inkomend = request.form.get("Body", "").strip().upper()
        resp = MessagingResponse()

        profile = load_profile(inkomend) if inkomend else None
        if profile:
            rapport_url = f"{SERVER_URL}/rapport/{inkomend}"
            resp.message(
                f"✅ Hoi {profile['naam']}! Je rapport is klaar:\n{rapport_url}"
            )
        else:
            resp.message(
                "👋 Welkom bij ZZPbot!\n"
                "Stuur je *Client ID* (8 tekens) om je rapportstatus te checken.\n"
                "Of ga naar zzpbot.nl om te beginnen."
            )
        return str(resp), 200, {"Content-Type": "text/xml"}
    except ImportError:
        return "Twilio niet geconfigureerd", 501


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "profielen": len(list(PROFILES_DIR.glob("*.json"))),
        "rapporten": len(list(REPORTS_DIR.glob("*.pdf"))),
    })


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("index.html"), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({"error": "Interne serverfout"}), 500


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    logger.info(f"ZZPbot server start op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
