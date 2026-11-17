"""Outbound email. Only system emails to the recipient themselves (invitations, password reset).
No client-facing communications are sent automatically."""
import json
import logging
import smtplib
import uuid
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger("aisv.email")


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body: str


MEMORY_OUTBOX: list[OutgoingEmail] = []


def send_email(msg: OutgoingEmail) -> None:
    s = get_settings()
    if s.email_backend == "memory":
        MEMORY_OUTBOX.append(msg)
    elif s.email_backend == "console":
        # Development only (refused in production by config): prints the body, which may contain a link.
        print(f"--- EMAIL (dev console backend) ---\nTo: {msg.to}\nSubject: {msg.subject}\n\n{msg.body}\n---")  # noqa: T201
    elif s.email_backend == "file":
        d = Path(s.email_file_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{uuid.uuid4()}.json").write_text(json.dumps(asdict(msg)))
    else:
        em = EmailMessage()
        em["From"], em["To"], em["Subject"] = s.smtp_from, msg.to, msg.subject
        em.set_content(msg.body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(em)
        log.info("email sent", extra={"subject": msg.subject})
