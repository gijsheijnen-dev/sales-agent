"""
Freelance PHP-opdrachten: bijhouden wat Gijs al gezien heeft en het dagoverzicht
als ongelezen mail in zijn eigen Postvak IN zetten (via mail_drafts.save_to_inbox).

Gebruik:
    from vacatures import nieuw, mail_overzicht, markeer_gezien

    gevonden = [{
        "titel": "PHP Developer (Laravel)",
        "opdrachtgever": "Voorbeeld BV",
        "via": "freep.nl",                 # platform of bureau
        "locatie": "Eindhoven",
        "werkvorm": "Hybride, 1 dag op locatie",
        "uren": "32",
        "tarief": "max €85/uur",
        "sluit": "30-9-2026",
        "reageren": "Formulier op platform",
        "url": "https://...",
        "waarom": "Laravel + datamigratie, past bij ervaring.",
        "markeringen": [">24u"],           # bv. ">24u", "tarief <€75", "datum onzeker"
        "reactie": "concept in Thunderbird" # of de tekst om in een formulier te plakken
    }]
    nieuwe = nieuw(gevonden)
    mail_overzicht(nieuwe, "16-9-2026")
    markeer_gezien(nieuwe, "16-9-2026")
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from mail_drafts import save_to_inbox

GEZIEN_FILE = Path(__file__).parent / "data" / "vacatures_gezien.json"

def _key(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), "", ""))


def _load() -> dict[str, dict[str, str]]:
    return json.loads(GEZIEN_FILE.read_text()) if GEZIEN_FILE.exists() else {}


def nieuw(vacatures: list[dict]) -> list[dict]:
    """Filtert opdrachten die al eerder gemeld zijn (op URL)."""
    gezien = _load()
    return [v for v in vacatures if _key(v["url"]) not in gezien]


def markeer_gezien(vacatures: list[dict], datum: str) -> None:
    gezien = _load()
    for v in vacatures:
        gezien[_key(v["url"])] = {"titel": v.get("titel", ""), "opdrachtgever": v.get("opdrachtgever", ""), "gemeld": datum}
    GEZIEN_FILE.parent.mkdir(exist_ok=True)
    GEZIEN_FILE.write_text(json.dumps(gezien, ensure_ascii=False, indent=1))


def mail_overzicht(vacatures: list[dict], datum: str, opmerkingen: str = "") -> None:
    """Zet het overzicht als ongelezen mail in Gijs' INBOX. Ook bij 0 nieuwe opdrachten (dan kort)."""
    subject = f"Freelance PHP-opdrachten {datum} ({len(vacatures)} nieuw)"
    e = lambda value: html.escape(str(value or "onbekend"))

    blocks_html, blocks_text = [], []
    for v in vacatures:
        marks = " ".join(f"[{m}]" for m in v.get("markeringen", []))
        reactie = v.get("reactie", "")
        blocks_html.append(
            f'<h3 style="margin-bottom:4px"><a href="{e(v["url"])}">{e(v["titel"])}</a> {e(marks) if marks else ""}</h3>'
            '<table cellspacing="0" cellpadding="2">'
            + "".join(
                f"<tr><td><b>{label}</b></td><td>{e(v.get(key))}</td></tr>"
                for label, key in [("Opdrachtgever", "opdrachtgever"), ("Via", "via"), ("Locatie", "locatie"),
                                   ("Werkvorm", "werkvorm"), ("Uren/week", "uren"), ("Tarief", "tarief"),
                                   ("Sluit", "sluit"), ("Reageren", "reageren"), ("Waarom passend", "waarom")]
            )
            + "</table>"
            + (f'<p><b>Reactie:</b><br>{e(reactie).replace(chr(10), "<br>")}</p>' if reactie else "")
        )
        blocks_text.append(
            f"{v['titel']} {marks}\n{v['url']}\n"
            + "\n".join(f"  {label}: {v.get(key) or 'onbekend'}"
                        for label, key in [("Opdrachtgever", "opdrachtgever"), ("Via", "via"), ("Locatie", "locatie"),
                                           ("Werkvorm", "werkvorm"), ("Uren/week", "uren"), ("Tarief", "tarief"),
                                           ("Sluit", "sluit"), ("Reageren", "reageren"), ("Waarom passend", "waarom")])
            + (f"\n  Reactie:\n{reactie}" if reactie else "")
        )

    intro = "Geen nieuwe passende opdrachten gevonden vandaag." if not vacatures else \
        "Nieuwe freelance PHP-opdrachten die bij je profiel passen. Reactie-concepten met e-mailadres staan in Thunderbird (Drafts); jij beslist en verstuurt."
    html_body = (
        '<!DOCTYPE html><html><head><meta http-equiv="content-type" content="text/html; charset=UTF-8"></head><body>'
        f"<p>{html.escape(intro)}</p>{''.join(blocks_html)}"
        + (f"<hr><p>{html.escape(opmerkingen).replace(chr(10), '<br>')}</p>" if opmerkingen else "")
        + "</body></html>"
    )
    text_body = intro + "\n\n" + "\n\n".join(blocks_text) + (f"\n\n---\n{opmerkingen}" if opmerkingen else "") + "\n"
    save_to_inbox(subject, html_body, text_body)
