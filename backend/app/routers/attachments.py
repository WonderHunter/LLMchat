from pathlib import PurePath

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from sqlmodel import Session

from app.attachments import MAX_FILE_BYTES, AttachmentError, purge_pending, read_upload
from app.deps import CurrentUser, SessionDep
from app.models import Attachment
from app.schemas import AttachmentOut

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def _owned(session: Session, user_id: int, attachment_id: str) -> Attachment:
    attachment = session.get(Attachment, attachment_id)
    # Même réponse qu'elle n'existe pas ou qu'elle appartienne à quelqu'un d'autre.
    if attachment is None or attachment.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pièce jointe introuvable")
    return attachment


# Fonction synchrone : la lecture d'un PDF occupe le processeur, FastAPI la lance dans un fil
# à part pour ne pas bloquer les réponses en cours de streaming.
@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def upload(file: UploadFile, user: CurrentUser, session: SessionDep) -> Attachment:
    """Enregistre un fichier, en attente d'être joint au prochain message."""
    data = file.file.read(MAX_FILE_BYTES + 1)
    try:
        kind, media_type, image, text = read_upload(data)
    except AttachmentError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc

    purge_pending(session, user.id)
    attachment = Attachment(
        user_id=user.id,
        kind=kind,
        filename=PurePath(file.filename or "fichier").name[:200] or "fichier",
        media_type=media_type,
        size=len(data),
        data=image,
        text=text,
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


@router.get("/{attachment_id}")
def download(attachment_id: str, user: CurrentUser, session: SessionDep) -> Response:
    attachment = _owned(session, user.id, attachment_id)
    if attachment.kind == "image":
        content, media_type = attachment.data, attachment.media_type
    else:
        content, media_type = (attachment.text or "").encode(), "text/plain; charset=utf-8"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            # Un fichier envoyé par un utilisateur ne doit rien pouvoir exécuter dans l'app.
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(attachment_id: str, user: CurrentUser, session: SessionDep) -> None:
    """Retire un fichier pas encore envoyé. Ceux d'un message partent avec le message."""
    attachment = _owned(session, user.id, attachment_id)
    if attachment.message_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette pièce jointe fait partie d'un message")
    session.delete(attachment)
    session.commit()
