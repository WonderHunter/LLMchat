"""Pièces jointes : ce qui est accepté, et comment c'est transmis aux modèles.

Deux familles :
- les images (PNG, JPEG, GIF, WebP), gardées telles quelles et envoyées aux modèles qui les lisent ;
- les documents (PDF, fichiers texte), dont seul le texte est gardé. Il est inséré dans le
  message, ce qui fonctionne avec n'importe quel modèle.
"""

from collections import defaultdict
from datetime import timedelta
from io import BytesIO

from pypdf import PdfReader
from sqlmodel import Session, col, delete, select

from app.models import Attachment, utcnow
from app.schemas import AttachmentOut

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_PER_MESSAGE = 5
# Un fichier envoyé mais jamais joint à un message est supprimé après ce délai.
PENDING_HOURS = 24

_ACCEPTED = "Sont acceptés : images (PNG, JPEG, GIF, WebP), PDF et fichiers texte."


class AttachmentError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def sniff_image(data: bytes) -> str | None:
    """Type de l'image d'après ses premiers octets : le nom et le type annoncés ne prouvent rien."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise AttachmentError(422, "Ce PDF est protégé par un mot de passe.")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except AttachmentError:
        raise
    except Exception as exc:  # pypdf lève des erreurs variées sur les fichiers abîmés
        raise AttachmentError(422, "Ce PDF est illisible.") from exc


def read_upload(data: bytes) -> tuple[str, str, bytes | None, str | None]:
    """Analyse un fichier reçu : (famille, type, octets de l'image, texte du document)."""
    if len(data) > MAX_FILE_BYTES:
        raise AttachmentError(413, "Fichier trop lourd (10 Mo maximum).")

    if media_type := sniff_image(data):
        if len(data) > MAX_IMAGE_BYTES:
            raise AttachmentError(413, "Image trop lourde (5 Mo maximum).")
        return "image", media_type, data, None

    if data.startswith(b"%PDF"):
        media_type, text = "application/pdf", _pdf_text(data)
        empty = "Ce PDF ne contient pas de texte lisible (document scanné ?)."
    else:
        media_type, empty = "text/plain", "Ce fichier est vide."
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AttachmentError(415, f"Type de fichier non pris en charge. {_ACCEPTED}") from exc
        if "\x00" in text:
            raise AttachmentError(415, f"Type de fichier non pris en charge. {_ACCEPTED}")

    text = text.strip()
    if not text:
        raise AttachmentError(422, empty)
    if len(text) > MAX_TEXT_CHARS:
        # Refusé plutôt que tronqué : le modèle répondrait sur un document incomplet sans le dire.
        raise AttachmentError(
            413,
            f"Ce document est trop long : {_spaced(len(text))} caractères, "
            f"pour {_spaced(MAX_TEXT_CHARS)} au maximum.",
        )
    return "text", media_type, None, text


def _spaced(number: int) -> str:
    return f"{number:,}".replace(",", " ")


def purge_pending(session: Session, user_id: int) -> None:
    """Supprime les fichiers de l'utilisateur envoyés il y a longtemps sans être joints."""
    limit = utcnow() - timedelta(hours=PENDING_HOURS)
    session.exec(
        delete(Attachment).where(
            col(Attachment.user_id) == user_id,
            col(Attachment.message_id).is_(None),
            col(Attachment.created_at) < limit,
        )
    )


def attachments_of(session: Session, message_ids: list[int]) -> dict[int, list[Attachment]]:
    """Pièces jointes complètes (contenu compris), regroupées par message."""
    grouped: dict[int, list[Attachment]] = defaultdict(list)
    if message_ids:
        rows = session.exec(
            select(Attachment)
            .where(col(Attachment.message_id).in_(message_ids))
            .order_by(Attachment.created_at, Attachment.id)
        )
        for row in rows:
            grouped[row.message_id].append(row)
    return grouped


def describe(session: Session, message_ids: list[int]) -> dict[int, list[AttachmentOut]]:
    """Description des pièces jointes par message, sans charger leur contenu."""
    grouped: dict[int, list[AttachmentOut]] = defaultdict(list)
    if message_ids:
        rows = session.exec(
            select(
                Attachment.message_id,
                Attachment.id,
                Attachment.kind,
                Attachment.filename,
                Attachment.media_type,
                Attachment.size,
            )
            .where(col(Attachment.message_id).in_(message_ids))
            .order_by(Attachment.created_at, Attachment.id)
        )
        for message_id, attachment_id, kind, filename, media_type, size in rows:
            grouped[message_id].append(
                AttachmentOut(
                    id=attachment_id, kind=kind, filename=filename, media_type=media_type, size=size
                )
            )
    return grouped
