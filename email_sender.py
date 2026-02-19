"""
Envoi d'emails transactionnels MyStrow via SMTP Hostinger.
Utilise smtplib stdlib — pas de dépendance externe.
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

try:
    from smtp_config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
except ImportError:
    SMTP_HOST = SMTP_PORT = SMTP_USER = SMTP_PASSWORD = SMTP_FROM = None


# ---------------------------------------------------------------
# Envoi bas niveau
# ---------------------------------------------------------------

def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """
    Envoie un email HTML via SMTP SSL.
    Retourne True si succès, lève une Exception sinon.
    """
    if not SMTP_HOST:
        raise Exception("smtp_config.py introuvable — email non envoyé.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = to

    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as smtp:
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.sendmail(SMTP_USER, to, msg.as_string())
    return True


# ---------------------------------------------------------------
# Templates
# ---------------------------------------------------------------

_BASE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8">
<style>
  body {{ margin:0; padding:0; background:#f4f4f4; font-family:'Segoe UI',Arial,sans-serif; }}
  .wrap {{ max-width:560px; margin:32px auto; background:#1a1a1a; border-radius:8px; overflow:hidden; }}
  .header {{ background:#111111; padding:24px 32px; border-bottom:2px solid #00d4ff; }}
  .header h1 {{ margin:0; color:#00d4ff; font-size:22px; letter-spacing:1px; }}
  .body {{ padding:28px 32px; color:#dddddd; font-size:14px; line-height:1.7; }}
  .body h2 {{ color:#ffffff; font-size:16px; margin-top:0; }}
  .highlight {{ background:#2a2a2a; border-left:3px solid #00d4ff; padding:12px 16px;
                border-radius:4px; margin:16px 0; color:#ffffff; font-size:13px; }}
  .btn {{ display:inline-block; margin:20px 0; padding:12px 28px; background:#00d4ff;
          color:#000000; font-weight:bold; text-decoration:none; border-radius:4px; font-size:14px; }}
  .footer {{ background:#111111; padding:14px 32px; color:#555555; font-size:11px;
             border-top:1px solid #2a2a2a; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header"><h1>MyStrow</h1></div>
  <div class="body">{content}</div>
  <div class="footer">MyStrow · Logiciel de contrôle lumière professionnel<br>
  Cet email est envoyé automatiquement, merci de ne pas y répondre.</div>
</div>
</body></html>"""


def _render(content: str) -> str:
    return _BASE_HTML.format(content=content)


def _fmt_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m/%Y")


# ---------------------------------------------------------------
# Emails métier
# ---------------------------------------------------------------

def send_welcome(to: str, expiry_ts: float, temp_password: str) -> bool:
    """
    Email de bienvenue avec identifiants de connexion.
    Envoyé lors de la création d'un compte client.
    """
    exp_str = _fmt_date(expiry_ts)
    content = f"""
<h2>Bienvenue sur MyStrow !</h2>
<p>Votre licence professionnelle vient d'être activée.
Voici vos identifiants de connexion :</p>
<div class="highlight">
  ✉️ &nbsp;<b>Email :</b> {to}<br>
  🔑 &nbsp;<b>Mot de passe :</b> <span style="font-family:monospace;font-size:14px;">{temp_password}</span><br>
  📅 &nbsp;<b>Licence valide jusqu'au :</b> {exp_str}
</div>
<p>Lancez MyStrow, cliquez sur <b>Se connecter</b> et entrez ces identifiants.</p>
<p>Vous pourrez changer votre mot de passe depuis votre espace compte.</p>
<p style="color:#888;font-size:12px;">
  Si vous n'avez pas demandé ce compte, ignorez cet email.
</p>"""
    text = (
        f"Bienvenue sur MyStrow !\n\n"
        f"Email       : {to}\n"
        f"Mot de passe: {temp_password}\n"
        f"Licence valide jusqu'au : {exp_str}\n\n"
        "Lancez MyStrow et connectez-vous avec ces identifiants.\n"
    )
    return send_email(to, "Bienvenue sur MyStrow — Vos identifiants de connexion", _render(content), text)


def send_renewal(to: str, expiry_ts: float) -> bool:
    """Email envoyé après renouvellement de licence."""
    exp_str = _fmt_date(expiry_ts)
    content = f"""
<h2>Votre licence a été renouvelée</h2>
<p>Bonne nouvelle ! Votre licence MyStrow vient d'être prolongée.</p>
<div class="highlight">
  📅 &nbsp;<b>Nouvelle date d'expiration :</b> {exp_str}
</div>
<p>Vous pouvez continuer à utiliser MyStrow normalement.
Aucune action de votre part n'est requise.</p>"""
    text = (
        f"Votre licence MyStrow a été renouvelée.\n"
        f"Nouvelle expiration : {exp_str}\n"
    )
    return send_email(to, "MyStrow — Licence renouvelée", _render(content), text)


def send_expiry_warning(to: str, expiry_ts: float, days_left: int) -> bool:
    """Email de rappel d'expiration imminente."""
    exp_str = _fmt_date(expiry_ts)
    content = f"""
<h2>Votre licence expire bientôt</h2>
<p>Il vous reste <b>{days_left} jour{'s' if days_left > 1 else ''}</b>
avant l'expiration de votre licence MyStrow.</p>
<div class="highlight">
  📅 &nbsp;<b>Date d'expiration :</b> {exp_str}
</div>
<p>Contactez votre revendeur pour renouveler votre licence et
continuer à utiliser MyStrow sans interruption.</p>"""
    text = (
        f"Votre licence MyStrow expire dans {days_left} jour(s) ({exp_str}).\n"
        "Contactez votre revendeur pour renouveler.\n"
    )
    return send_email(to, f"MyStrow — Licence expire dans {days_left} jour(s)", _render(content), text)
