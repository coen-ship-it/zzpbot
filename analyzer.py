"""
analyzer.py — ZZPbot AI Analyse Module
Stuurt activiteitsdata + intakeprofiel naar OpenRouter (Claude),
ontvangt gestructureerde JSON met automatiseringskansen en ROI-berekeningen.
"""

import json
import os
import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# OpenRouter client (OpenAI-compatible)
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-5-haiku")

# ---------------------------------------------------------------------------
# App categorisatie (lokaal, zonder API-call)
# ---------------------------------------------------------------------------

APP_CATEGORIES: dict[str, list[str]] = {
    "Email": ["outlook.exe", "thunderbird.exe", "mailbird.exe", "postman"],
    "Browser": ["chrome.exe", "firefox.exe", "msedge.exe", "brave.exe", "opera.exe", "iexplore.exe"],
    "Spreadsheets": ["excel.exe", "sheets.google", "libreoffice calc"],
    "Tekstverwerker": ["winword.exe", "wordpad.exe", "docs.google", "notion.exe"],
    "Projectbeheer": ["notion.exe", "todoist.exe", "trello", "asana", "monday", "clickup"],
    "Communicatie": ["teams.exe", "slack.exe", "zoom.exe", "skype.exe", "discord.exe", "whatsapp.exe"],
    "Boekhouding": ["quickbooks", "moneybird", "exact.exe", "twinfield", "snelstart", "e-boekhouden"],
    "CRM": ["salesforce", "hubspot", "pipedrive", "zoho"],
    "Design": ["photoshop.exe", "illustrator.exe", "figma.exe", "canva", "sketch.exe", "affinity"],
    "Ontwikkeling": ["code.exe", "pycharm64.exe", "idea64.exe", "webstorm64.exe", "git", "github"],
    "PDF": ["acrobat.exe", "acrord32.exe", "foxit.exe", "sumatra"],
    "Bestandsbeheer": ["explorer.exe"],
    "Administratie": ["onenote.exe", "evernote.exe", "obsidian.exe"],
    "Planning": ["calendar.exe", "outlook.exe"],
}


def categorize_process(process_name: str, window_title: str) -> str:
    """Categoriseer een applicatie op basis van procesnaam en venstertitel."""
    p = process_name.lower()
    t = window_title.lower()
    for category, keywords in APP_CATEGORIES.items():
        for kw in keywords:
            if kw in p or kw in t:
                return category
    return "Overig"


def enrich_summary_with_categories(activity_data: dict) -> dict:
    """Voeg categorieën toe aan de samenvatting op basis van procesnamen."""
    sessions = activity_data.get("sessions", [])
    by_category: dict[str, float] = {}

    for session in sessions:
        cat = session.get("category") or categorize_process(
            session.get("process", ""),
            session.get("title", ""),
        )
        session["category"] = cat
        by_category[cat] = by_category.get(cat, 0) + session.get("duration_seconds", 0)

    # Converteer seconden naar uren
    total_seconds = sum(by_category.values())
    category_hours = {
        cat: {
            "uren_per_week": round(secs / 3600, 1),
            "percentage": round((secs / total_seconds * 100) if total_seconds else 0, 1),
        }
        for cat, secs in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    }

    activity_data["by_category"] = category_hours
    activity_data["total_hours"] = round(total_seconds / 3600, 1)
    return activity_data


# ---------------------------------------------------------------------------
# Analyse prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Je bent een senior AI-automatisering consultant gespecialiseerd in ZZP-ondernemers.
Je analyseert computeractiviteitsdata en identificeert concrete, waardevolle automatiseringskansen.

Regels:
- Wees specifiek en praktisch — geen vage adviezen
- Baseer kansen op bewijs uit de data
- Bereken ROI conservatief
- Schrijf in het Nederlands
- Return ALLEEN geldige JSON, geen markdown codeblokken
"""

ANALYSIS_PROMPT = """Analyseer de volgende ZZP-ondernemer en zijn computeractiviteit van de afgelopen week.

## KLANTPROFIEL
{profile}

## COMPUTERACTIVITEIT (afgelopen week)
Totaal getrackt: {total_hours} uur
Verdeling per categorie:
{category_breakdown}

Top processen:
{top_processes}

## OPDRACHT
Genereer een gedetailleerde automatiseringsscan. Return exact deze JSON-structuur (geen markdown):

{{
  "readiness_score": {{
    "totaal": <0-100>,
    "tijdsbesparing_potentieel": <0-100>,
    "procesherhaalbaarheid": <0-100>,
    "toolkoppeling": <0-100>,
    "datakwaliteit": <0-100>,
    "toelichting": "<2-3 zinnen uitleg van de totaalscore>"
  }},
  "kansen": [
    {{
      "titel": "<Korte, pakkende titel>",
      "beschrijving": "<2-3 zinnen wat de ondernemer nu handmatig doet en waarom dit automatiseerbaar is>",
      "bewijs": "<Specifiek bewijs uit de monitordata: welke apps, hoeveel tijd, welk patroon>",
      "agent_briefing": {{
        "input": "<Wat de agent als invoer krijgt>",
        "logica": "<Wat de agent doet, stap voor stap>",
        "output": "<Wat de agent oplevert>"
      }},
      "tijdsbesparing_percentage": <0-100>,
      "tijdsbesparing_uren_per_week": <getal>,
      "euros_bespaard_per_maand": <getal op basis van uurtarief {uurtarief}>,
      "implementatie_inspanning": "<Laag|Middel|Hoog>",
      "terugverdientijd": "<bijv. '2 weken' of '1 maand'>"
    }}
  ],
  "roi_samenvatting": {{
    "totale_uren_bespaard_per_week": <getal>,
    "totale_euros_bespaard_per_maand": <getal>,
    "totale_euros_bespaard_per_jaar": <getal>,
    "aanbevolen_eerste_stap": "<Concrete, uitvoerbare eerste actie voor de ondernemer>"
  }},
  "data_completeness": {{
    "percentage_onbekend": <getal>,
    "waarschuwing": <true|false>
  }}
}}

Genereer 3 tot 6 kansen, gesorteerd op hoogste ROI. Wees specifiek en realistisch."""


def build_prompt(profile: dict, activity_data: dict) -> str:
    """Bouw de analyse prompt op basis van profiel en activiteitsdata."""
    uurtarief = profile.get("uurtarief", 85)
    total_hours = activity_data.get("total_hours", 0)

    # Categorieoverzicht
    by_cat = activity_data.get("by_category", {})
    cat_lines = "\n".join(
        f"  - {cat}: {info['uren_per_week']} uur/week ({info['percentage']}%)"
        for cat, info in by_cat.items()
    )

    # Top processen (uit summary of sessions)
    summary = activity_data.get("summary", {})
    by_process = summary.get("by_process", {})
    top = sorted(by_process.items(), key=lambda x: x[1], reverse=True)[:10]
    proc_lines = "\n".join(
        f"  - {p}: {round(s/3600, 1)} uur" for p, s in top
    ) if top else "  (geen procesdata beschikbaar)"

    # Profiel compact
    profile_text = "\n".join([
        f"Naam: {profile.get('naam', 'Onbekend')}",
        f"Bedrijfstype: {profile.get('bedrijfstype', 'Onbekend')}",
        f"Huidige tools: {profile.get('huidige_tools', 'Onbekend')}",
        f"Uurtarief: €{uurtarief}",
        f"Maatwerksoftware: {profile.get('maatwerksoftware', 'Geen')}",
        f"Werktijden: {profile.get('werktijden', 'Onbekend')}",
    ])

    return ANALYSIS_PROMPT.format(
        profile=profile_text,
        total_hours=total_hours,
        category_breakdown=cat_lines or "  (geen categoriedata)",
        top_processes=proc_lines,
        uurtarief=uurtarief,
    )


# ---------------------------------------------------------------------------
# Fallback analyse (als API faalt)
# ---------------------------------------------------------------------------

def fallback_analysis(profile: dict, activity_data: dict) -> dict:
    """Genereer een basis-analyse zonder API-call als fallback."""
    logger.warning("Fallback analyse actief (geen OpenRouter verbinding)")
    uurtarief = profile.get("uurtarief", 85)
    by_cat = activity_data.get("by_category", {})

    # Bereken percentage onbekend
    total = sum(v["uren_per_week"] for v in by_cat.values()) or 1
    overig = by_cat.get("Overig", {}).get("uren_per_week", 0)
    pct_onbekend = round((overig / total) * 100, 1)

    return {
        "readiness_score": {
            "totaal": 65,
            "tijdsbesparing_potentieel": 70,
            "procesherhaalbaarheid": 65,
            "toolkoppeling": 60,
            "datakwaliteit": 65,
            "toelichting": "Score gebaseerd op algemene patronen in de activiteitsdata.",
        },
        "kansen": [
            {
                "titel": "E-mail automatisering",
                "beschrijving": "Een groot deel van de werktijd gaat naar e-mailverwerking. "
                                "AI kan routinematige mails automatisch sorteren, beantwoorden en opvolgen.",
                "bewijs": f"E-mail applicaties zijn zichtbaar in de activiteitsdata.",
                "agent_briefing": {
                    "input": "Inkomende e-mails",
                    "logica": "Categoriseer, prioriteer en genereer conceptantwoorden",
                    "output": "Gesorteerde inbox + conceptantwoorden ter goedkeuring",
                },
                "tijdsbesparing_percentage": 40,
                "tijdsbesparing_uren_per_week": 3.0,
                "euros_bespaard_per_maand": round(3.0 * uurtarief * 4, 0),
                "implementatie_inspanning": "Laag",
                "terugverdientijd": "2 weken",
            }
        ],
        "roi_samenvatting": {
            "totale_uren_bespaard_per_week": 3.0,
            "totale_euros_bespaard_per_maand": round(3.0 * uurtarief * 4, 0),
            "totale_euros_bespaard_per_jaar": round(3.0 * uurtarief * 48, 0),
            "aanbevolen_eerste_stap": "Start met het automatiseren van terugkerende e-mails.",
        },
        "data_completeness": {
            "percentage_onbekend": pct_onbekend,
            "waarschuwing": pct_onbekend > 10,
        },
    }


# ---------------------------------------------------------------------------
# Hoofd analyse functie
# ---------------------------------------------------------------------------

def analyze_activity(profile: dict, activity_data: dict) -> dict:
    """
    Analyseer activiteitsdata + klantprofiel via OpenRouter.
    Geeft gestructureerde dict terug met kansen, scores en ROI.
    """
    # Verrijkt data met categorieën
    activity_data = enrich_summary_with_categories(activity_data)

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error("Geen OPENROUTER_API_KEY gevonden")
        return fallback_analysis(profile, activity_data)

    prompt = build_prompt(profile, activity_data)

    try:
        logger.info(f"OpenRouter analyse starten (model: {MODEL})")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.3,
            extra_headers={
                "HTTP-Referer": os.getenv("SERVER_URL", "https://zzpbot.nl"),
                "X-Title": "ZZPbot",
            },
        )

        raw = response.choices[0].message.content.strip()

        # Verwijder markdown codeblokken als Claude die toch meestuurt
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        result = json.loads(raw)
        logger.info("Analyse succesvol ontvangen")

        # Voeg gecategoriseerde uren toe aan resultaat
        result["app_categorieen"] = activity_data.get("by_category", {})
        result["total_hours_tracked"] = activity_data.get("total_hours", 0)

        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse fout in API response: {e}")
        return fallback_analysis(profile, activity_data)
    except Exception as e:
        logger.error(f"OpenRouter API fout: {e}")
        return fallback_analysis(profile, activity_data)
