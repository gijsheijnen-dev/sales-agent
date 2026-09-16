# Setup: Sales Manager Agent

## Wat je krijgt

Een Claude Code agent die op jouw laptop draait, dagelijks (als de laptop aan
staat) of op jouw commando de acquisitie voorbereidt: leads opzoeken, follow-ups
signaleren, berichten concipiëren, en je leadlijst in Google Sheets bijwerken.
Hij verstuurt nooit zelf iets — jij verstuurt alles.

## Stap 1 — Projectmap inrichten

1. Maak een map, bijvoorbeeld `~/sales-agent/`.
2. Zet hierin:
   - `CLAUDE.md` (bijgevoegd)
   - `sheets_client.py` (bijgevoegd)
   - `.claude/commands/sales-check.md` (bijgevoegd)
   - `.claude/commands/log-capaciteit.md` (bijgevoegd)
   - Kopieën van je drie strategiedocumenten: `acquisitie-per-doelgroep.md`,
     en je CV-pdf.
3. Open deze map met Claude Code (`claude` in de terminal, in deze map).
   Claude Code leest `CLAUDE.md` automatisch als projectinstructies.

## Stap 2 — Google Sheets API-toegang (eenmalig, ~10 minuten)

Dit geeft de agent schrijfrechten op je Sheet, los van jouw eigen Google-account
(veiliger dan met jouw eigen inloggegevens werken).

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com) en maak
   een nieuw project aan (bijv. "gijs-sales-agent").
2. Ga naar **APIs & Services → Bibliotheek** en schakel in:
   - Google Sheets API
   - Google Drive API
3. Ga naar **APIs & Services → Inloggegevens (Credentials) → Inloggegevens
   maken → Service-account**. Geef het een naam (bijv. "sales-agent").
4. Open het aangemaakte service-account → tabblad **Sleutels (Keys)** → **Sleutel
   toevoegen → JSON**. Er downloadt een `.json`-bestand.
5. Zet dat bestand in je projectmap als `credentials/service-account.json`
   (maak de map `credentials/` aan). **Zet dit bestand niet in git/publiek.**
6. Open het JSON-bestand en kopieer het `client_email`-veld (iets als
   `sales-agent@gijs-sales-agent.iam.gserviceaccount.com`).
7. Open je leadlijst-Sheet in de browser, klik **Delen**, en deel het Sheet met
   dat e-mailadres met rol **Bewerker**.

Vanaf nu kan `sheets_client.py` met dit bestand inloggen en het Sheet lezen én
bewerken.

## Stap 3 — Dependencies installeren

Ubuntu/Debian staat `pip install` buiten een virtual environment niet toe
(`externally-managed-environment`). Gebruik daarom een venv in de projectmap:

```bash
sudo apt install python3.12-venv   # eenmalig
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Draai scripts daarna met `.venv/bin/python sheets_client.py` (of activeer eerst
met `source .venv/bin/activate`).

## Stap 4 — Nieuwe tabbladen aanmaken

Bij de eerste run laat je de agent (via `/sales-check` of een losse instructie)
het tabblad **Onderwijs** en het tabblad **Capaciteit** aanmaken — de logica
hiervoor staat al in `sheets_client.py` (`create_tab_if_missing`,
`log_capaciteit`) en de kolomstructuur staat beschreven in `CLAUDE.md`.

Geef de agent bijvoorbeeld de opdracht:
> "Maak het tabblad Onderwijs aan met dezelfde structuur als de andere
> doelgroep-tabbladen, en het tabblad Capaciteit. Log daarna mijn huidige
> capaciteit: 0 actieve opdrachten, 0 uur, €0."

## Stap 5 — Dagelijks automatisch laten draaien (optioneel)

Op macOS gebruik je `launchd`, op Linux `cron`. Voorbeeld met cron (elke
werkdag 8:00, alleen als de laptop op dat moment aan staat):

```bash
crontab -e
```

Voeg toe:

```
0 8 * * 1-5 cd ~/sales-agent && claude -p "/sales-check" >> ~/sales-agent/log.txt 2>&1
```

Dit start Claude Code non-interactief met het `/sales-check`-commando en logt
de output. Staat je laptop uit op dat moment, dan slaat cron de run simpelweg
over — er gebeurt niets vervelends.

Wil je het liever alleen handmatig triggeren? Open de map in Claude Code en typ
`/sales-check` wanneer je wilt.

## Stap 6 — Capaciteit bijhouden

Zodra je een opdracht toezegt, werk je het Capaciteit-tabblad bij — handmatig in
het Sheet, of via het commando `/log-capaciteit` (de agent vraagt dan naar je
actieve opdrachten, uren en omzet). Zodra 24 uur/week of €1.800/week is bereikt,
zet de agent zelf de status op "Acquireren UIT" en pauzeert nieuwe outreach.

## Wat nu al is ingevuld (standaardwaarden — pas aan in CLAUDE.md indien gewenst)

| Instelling | Standaardwaarde |
|---|---|
| Max. capaciteit | 24 uur/week óf €1.800/week (wat eerst komt) |
| Ondergrens tarief | €75/uur ex btw |
| Uitgesloten branches | E-commerce |
| Nieuwe eerste-contacten/dag | 3–5 |
| Follow-up na | 5 werkdagen zonder reactie |
| Max. follow-ups | 2, daarna status "Geen interesse" |
| Berichten versturen | Nooit automatisch — altijd concept, jij verstuurt |
| Rapportage | Kort na elke run, uitgebreid elke maandag |

## Openstaande keuzes voor jou

- **Scholen-aanpak:** ik heb een eerste insteek in `CLAUDE.md` gezet (automatisering
  van werkprocessen, ICT-coördinator/directie als ingang, OERknal-case als bewijs).
  Wil je dit aanscherpen of eerst een paar losse gesprekken voeren om te testen
  wat aanslaat voordat de agent dit op schaal doet?
- **Aantal nieuwe contacten/dag (nu 3–5):** dit bepaalt hoe snel je pipeline vult.
  Wil je sneller of juist rustiger opbouwen?
- **Wekelijkse rapportage:** wil je die als chatbericht in Claude Code, of liever
  als los overzicht (bijvoorbeeld een klein dashboard-bestand dat elke maandag
  wordt bijgewerkt)?

## Stap 7 — E-mailconcepten in Thunderbird (optioneel)

De agent kan e-mailconcepten direct in de map **Drafts** van info@gijsheijnen.dev
zetten (via IMAP bij TransIP). Thunderbird laat ze dan vanzelf zien. Versturen
kan de agent niet: `mail_drafts.py` bevat geen SMTP.

1. Maak `credentials/imap.env` aan (valt al onder `.gitignore`) met:
   ```
   IMAP_PASSWORD=jouw-mailboxwachtwoord
   ```
2. Zet de rechten dicht: `chmod 600 credentials/imap.env`
3. Test de verbinding (dit leest alleen): `.venv/bin/python mail_drafts.py`
