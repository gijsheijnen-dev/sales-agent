"""
Zet e-mailconcepten klaar in de map Drafts van info@gijsheijnen.dev (IMAP bij
TransIP). Thunderbird synchroniseert die map, dus de concepten verschijnen daar
vanzelf. Gijs opent ze, past ze eventueel aan en verstuurt ze zelf.

Deze module kan bewust NIETS versturen: er zit geen SMTP in. Alleen IMAP APPEND
naar Drafts (regel 1 in CLAUDE.md).

Wachtwoord (eenmalig): zet in `credentials/imap.env` de regel
    IMAP_PASSWORD=...
Optioneel ook IMAP_HOST, IMAP_USER, IMAP_DRAFTS_FOLDER, IMAP_SENT_FOLDER en
THUNDERBIRD_PREFS (standaardwaarden hieronder).

Opmaak: concepten worden HTML-mails zoals Thunderbird ze zelf maakt. De handtekening
(met foto) en het opstel-lettertype worden bij elke aanroep uit Thunderbirds prefs.js
gelezen, dus wijzigingen in Thunderbird worden automatisch overgenomen. `body` is
platte tekst zonder handtekening; alinea's scheiden met een lege regel.

Gebruik:
    from mail_drafts import save_draft

    save_draft(
        lead="Antum",
        subject="Even terugkomen op mijn bericht",
        body="Hoi, ...",
        to="info@antum.nl",  # optioneel; zonder adres moet de organisatienaam in het onderwerp
    )

    # Follow-up als antwoord op de eerder verzonden mail (zelfde conversatie):
    save_reply_draft(lead="CodeCrunch", to_address="hallo@codecrunch.nl", body="Hoi, ...")
"""

from __future__ import annotations

import email.policy
import html
import json
import re
import email.utils
import imaplib
import os
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path

ENV_FILE = Path(__file__).parent / "credentials" / "imap.env"

DEFAULTS = {
    "IMAP_HOST": "imap.transip.email",
    "IMAP_USER": "info@gijsheijnen.dev",
    "IMAP_DRAFTS_FOLDER": "Drafts",
    "IMAP_SENT_FOLDER": "Sent",
    "FROM_NAME": "Gijs Heijnen",
    "THUNDERBIRD_PREFS": str(Path.home() / "snap/thunderbird/common/.thunderbird/bn8jp660.default/prefs.js"),
}


def _config() -> dict[str, str]:
    config = dict(DEFAULTS)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    config.update({k: v for k, v in os.environ.items() if k in DEFAULTS or k == "IMAP_PASSWORD"})
    if not config.get("IMAP_PASSWORD"):
        raise RuntimeError(f"Geen IMAP_PASSWORD gevonden in {ENV_FILE} of in de omgeving.")
    return config


def _connect(config: dict[str, str]) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(config["IMAP_HOST"], 993)
    conn.login(config["IMAP_USER"], config["IMAP_PASSWORD"])
    return conn


def _list_drafts(conn: imaplib.IMAP4_SSL, config: dict[str, str]) -> list[dict[str, str]]:
    conn.select(f'"{config["IMAP_DRAFTS_FOLDER"]}"', readonly=True)
    _, data = conn.search(None, "ALL")
    drafts = []
    for num in data[0].split():
        _, msg_data = conn.fetch(num, "(BODY.PEEK[HEADER.FIELDS (TO SUBJECT X-SALES-AGENT-LEAD)])")
        headers = email.message_from_bytes(msg_data[0][1])
        drafts.append({
            "lead": str(make_header(decode_header(headers.get("X-Sales-Agent-Lead", "")))),
            "to": str(make_header(decode_header(headers.get("To", "")))),
            "subject": str(make_header(decode_header(headers.get("Subject", "")))),
        })
    return drafts


def list_drafts() -> list[dict[str, str]]:
    """Geeft lead, aan en onderwerp van alle concepten in Drafts terug, om dubbele concepten te voorkomen."""
    config = _config()
    conn = _connect(config)
    try:
        return _list_drafts(conn, config)
    finally:
        conn.logout()


# ---------- Thunderbird-instellingen (handtekening + lettertype) ----------

def _thunderbird_prefs(config: dict[str, str]) -> dict[str, object]:
    prefs: dict[str, object] = {}
    path = Path(config["THUNDERBIRD_PREFS"])
    if not path.exists():
        raise RuntimeError(f"Thunderbird prefs.js niet gevonden: {path}")
    for match in re.finditer(r'^user_pref\("([^"]+)",\s*(.*)\);\s*$', path.read_text(), re.MULTILINE):
        raw = match.group(2)
        prefs[match.group(1)] = json.loads(raw, strict=False) if raw.startswith('"') else json.loads(raw)
    return prefs


def _compose_settings(config: dict[str, str]) -> dict[str, object]:
    """Handtekening en lettertype van de identiteit die bij IMAP_USER hoort."""
    prefs = _thunderbird_prefs(config)
    identity = next(
        (k.split(".")[2] for k, v in prefs.items()
         if k.startswith("mail.identity.") and k.endswith(".useremail") and str(v).lower() == config["IMAP_USER"].lower()),
        None,
    )
    if identity is None:
        raise RuntimeError(f"Geen Thunderbird-identiteit gevonden voor {config['IMAP_USER']}")
    ident = lambda key, default=None: prefs.get(f"mail.identity.{identity}.{key}", default)

    sig_text = str(ident("htmlSigText", ""))
    if sig_text and not ident("htmlSigFormat", False):
        sig_text = html.escape(sig_text).replace("\n", "<br>\n")
    return {
        "compose_html": ident("compose_html", True),
        "signature_html": sig_text,
        "font_face": str(prefs.get("msgcompose.font_face", "")),  # leeg = Thunderbird-standaard ("Variable Width")
        "font_size": str(prefs.get("msgcompose.font_size", "")),  # leeg/medium = standaard
        "text_color": str(prefs.get("msgcompose.text_color", "")) if not prefs.get("msgcompose.default_colors", True) else "",
    }


def _linkify(fragment: str) -> str:
    """Zoals Thunderbird bij versturen: e-mailadressen en www-adressen klikbaar maken (buiten bestaande tags)."""
    parts = re.split(r"(<[^>]+>)", fragment)
    for i, part in enumerate(parts):
        if part.startswith("<"):
            continue
        part = re.sub(r"\b([\w.+-]+@[\w-]+\.[\w.-]+)\b",
                      r'<a class="moz-txt-link-abbreviated" href="mailto:\1">\1</a>', part)
        part = re.sub(r"(?<![/@\w.])(www\.[\w-]+\.[\w./-]*[\w/])",
                      r'<a class="moz-txt-link-abbreviated" href="http://\1">\1</a>', part)
        parts[i] = part
    return "".join(parts)


def _html_to_text(fragment: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</(p|tr|div)>", "\n", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _text_to_paragraphs(body: str) -> str:
    paragraphs = re.split(r"\n\s*\n", body.replace("\r\n", "\n").strip())
    return "\n".join(
        "    <p>" + "<br>\n      ".join(html.escape(line, quote=False) for line in p.split("\n")) + "</p>"
        for p in paragraphs
    )


def _build_message(config: dict[str, str], body: str, quote_html: str = "", quote_text: str = "") -> EmailMessage:
    settings = _compose_settings(config)
    sig_html = settings["signature_html"]
    body_plain = body.replace("\r\n", "\n").strip()

    plain = body_plain
    if sig_html:
        plain += "\n\n-- \n" + _html_to_text(sig_html)
    if quote_text:
        plain += "\n\n" + quote_text

    msg = EmailMessage()
    msg.set_content(plain + "\n")
    if not settings["compose_html"]:
        return msg

    style = []
    if settings["font_face"]:
        style.append(f"font-family: {settings['font_face']}")
    if settings["font_size"] and settings["font_size"] != "medium":
        style.append(f"font-size: {settings['font_size']}")
    if settings["text_color"]:
        style.append(f"color: {settings['text_color']}")
    body_attr = f' style="{"; ".join(style)}"' if style else ""

    signature = f'    <div class="moz-signature">-- <br>\n{_linkify(sig_html)}\n    </div>\n' if sig_html else ""
    html_doc = (
        "<!DOCTYPE html>\n<html>\n  <head>\n"
        '    <meta http-equiv="content-type" content="text/html; charset=UTF-8">\n'
        f"  </head>\n  <body{body_attr}>\n"
        f"{_text_to_paragraphs(body_plain)}\n"
        f"{signature}"
        f"{quote_html}"
        "  </body>\n</html>\n"
    )
    msg.add_alternative(html_doc, subtype="html")
    return msg


# ---------- Concepten ----------

def save_draft(
    lead: str,
    subject: str,
    body: str,
    to: str = "",
    skip_duplicates: bool = True,
    extra_headers: dict[str, str] | None = None,
    _quote: tuple[str, str] = ("", ""),
) -> bool:
    """Plaatst één concept (HTML + tekst, met Thunderbird-handtekening) in Drafts; `to` mag leeg zijn.

    Zonder `to` moet de naam van de organisatie (`lead`) in het onderwerp staan,
    zodat Gijs ziet voor wie het concept is.
    Geeft False terug als er al een concept voor dezelfde lead met hetzelfde onderwerp staat.
    """
    if not to and lead.strip().lower() not in subject.lower():
        raise ValueError(f"Concept zonder ontvanger: zet '{lead}' in het onderwerp.")

    config = _config()
    msg = _build_message(config, body, quote_html=_quote[0], quote_text=_quote[1])
    msg["From"] = email.utils.formataddr((config["FROM_NAME"], config["IMAP_USER"]))
    if to:
        msg["To"] = to
    msg["Subject"] = subject
    msg["X-Sales-Agent-Lead"] = lead
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=config["IMAP_USER"].split("@")[1])
    msg["X-Sales-Agent"] = "concept - niet verstuurd"
    for name, value in (extra_headers or {}).items():
        msg[name] = value

    conn = _connect(config)
    try:
        if skip_duplicates:
            for draft in _list_drafts(conn, config):
                if draft["lead"].strip().lower() == lead.strip().lower() and draft["subject"].strip() == subject.strip():
                    return False
        status, _ = conn.append(
            f'"{config["IMAP_DRAFTS_FOLDER"]}"',
            r"(\Draft \Seen)",
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(),
        )
        if status != "OK":
            raise RuntimeError(f"IMAP APPEND naar Drafts mislukt: {status}")
        return True
    finally:
        conn.logout()


def find_sent(to_address: str) -> list[dict[str, str]]:
    """Zoekt verzonden mails aan een adres (of deel ervan, bv. 'codecrunch.nl'), oudste eerst."""
    config = _config()
    conn = _connect(config)
    try:
        conn.select(f'"{config["IMAP_SENT_FOLDER"]}"', readonly=True)
        _, data = conn.uid("SEARCH", None, "TO", f'"{to_address}"')
        found = []
        for uid in data[0].split():
            _, msg_data = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (TO SUBJECT DATE MESSAGE-ID)])")
            headers = email.message_from_bytes(msg_data[0][1])
            found.append({
                "uid": uid.decode(),
                "to": str(make_header(decode_header(headers.get("To", "")))),
                "subject": str(make_header(decode_header(headers.get("Subject", "")))),
                "date": headers.get("Date", ""),
                "message_id": headers.get("Message-ID", "").strip(),
            })
        return found
    finally:
        conn.logout()


def save_reply_draft(lead: str, to_address: str, body: str, skip_duplicates: bool = True) -> bool:
    """Zet een follow-up als antwoord (Re:) op de laatst verzonden mail aan `to_address` in Drafts.

    Opgebouwd zoals een Thunderbird-antwoord: eigen tekst bovenaan, dan de handtekening,
    dan "On <datum>, <naam> wrote:" met de oorspronkelijke mail als citaat. Het concept hangt
    in dezelfde conversatie (In-Reply-To/References).
    """
    config = _config()
    conn = _connect(config)
    try:
        conn.select(f'"{config["IMAP_SENT_FOLDER"]}"', readonly=True)
        _, data = conn.uid("SEARCH", None, "TO", f'"{to_address}"')
        uids = data[0].split()
        if not uids:
            raise LookupError(f"Geen verzonden mail aan {to_address} gevonden in Sent.")
        _, msg_data = conn.uid("FETCH", uids[-1], "(BODY.PEEK[])")
        original = email.message_from_bytes(msg_data[0][1], policy=email.policy.default)
    finally:
        conn.logout()

    sent_at = email.utils.parsedate_to_datetime(original["Date"])
    from_name = email.utils.parseaddr(str(original["From"]))[0] or str(original["From"])
    prefix = f"On {sent_at.month}/{sent_at.day}/{sent_at:%y} {sent_at:%H:%M}, {from_name} wrote:"

    html_part = original.get_body(preferencelist=("html",))
    text_part = original.get_body(preferencelist=("plain",))
    original_text = text_part.get_content() if text_part else ""
    if html_part:
        inner = html_part.get_content()
        match = re.search(r"(?is)<body[^>]*>(.*)</body>", inner)
        inner = match.group(1) if match else inner
    else:
        inner = f'<pre class="moz-quote-pre" wrap="">{html.escape(original_text)}</pre>'
    quote_html = (
        f'    <div class="moz-cite-prefix">{html.escape(prefix)}<br>\n    </div>\n'
        f'    <blockquote type="cite" cite="mid:{original["Message-ID"].strip("<> ")}">\n{inner}\n    </blockquote>\n'
    )
    quote_text = prefix + "\n" + "\n".join(
        ("> " + line) if line else ">" for line in original_text.replace("\r\n", "\n").rstrip().splitlines()
    )

    subject = str(original["Subject"])
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    references = f'{original.get("References", "")} {original["Message-ID"]}'.strip()
    return save_draft(
        lead=lead,
        subject=subject,
        body=body,
        to=str(original["To"]),
        skip_duplicates=skip_duplicates,
        extra_headers={"In-Reply-To": original["Message-ID"], "References": references},
        _quote=(quote_html, quote_text),
    )


def save_to_inbox(subject: str, html_body: str, text_body: str) -> None:
    """Zet een melding voor Gijs zelf (bv. het vacature-overzicht) als ongelezen mail in zijn INBOX.

    Dit is geen versturen: het bericht wordt via IMAP APPEND direct in de eigen mailbox gezet,
    van en aan info@gijsheijnen.dev, zonder SMTP en zonder dat het de server verlaat.
    """
    config = _config()
    msg = EmailMessage()
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    own = email.utils.formataddr(("Sales-agent", config["IMAP_USER"]))
    msg["From"] = own
    msg["To"] = email.utils.formataddr((config["FROM_NAME"], config["IMAP_USER"]))
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=config["IMAP_USER"].split("@")[1])
    msg["X-Sales-Agent"] = "melding aan Gijs - niet verstuurd"

    conn = _connect(config)
    try:
        status, _ = conn.append('"INBOX"', "()", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if status != "OK":
            raise RuntimeError(f"IMAP APPEND naar INBOX mislukt: {status}")
    finally:
        conn.logout()


def delete_drafts(lead: str, subject: str | None = None) -> int:
    """Verwijdert concepten die de agent zelf voor `lead` heeft gemaakt (optioneel alleen met dit onderwerp).

    Raakt alleen berichten met de kopregel X-Sales-Agent-Lead aan, nooit concepten van Gijs zelf.
    """
    config = _config()
    conn = _connect(config)
    try:
        conn.select(f'"{config["IMAP_DRAFTS_FOLDER"]}"')
        _, data = conn.uid("SEARCH", None, "HEADER", "X-Sales-Agent-Lead", f'"{lead}"')
        uids = []
        for uid in data[0].split():
            _, msg_data = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT X-SALES-AGENT-LEAD)])")
            headers = email.message_from_bytes(msg_data[0][1])
            if str(make_header(decode_header(headers.get("X-Sales-Agent-Lead", "")))).strip().lower() != lead.strip().lower():
                continue
            if subject is not None and str(make_header(decode_header(headers.get("Subject", "")))).strip() != subject.strip():
                continue
            uids.append(uid)
        if uids:
            uid_set = b",".join(uids)
            conn.uid("STORE", uid_set, "+FLAGS", r"(\Deleted)")
            conn.uid("EXPUNGE", uid_set)  # UIDPLUS: alleen deze berichten
        return len(uids)
    finally:
        conn.logout()


if __name__ == "__main__":
    # Verbindingstest: toont het aantal concepten in Drafts, verandert niets.
    print(f"{len(list_drafts())} concept(en) in Drafts")
