"""Crée le fichier .env à la racine du projet, avec des secrets générés, s'il n'existe pas."""

import secrets
from pathlib import Path

from cryptography.fernet import Fernet

ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        print(f"{env_file} existe déjà, rien n'a été modifié.")
        return
    content = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
    content = content.replace("SECRET_KEY=", f"SECRET_KEY={secrets.token_urlsafe(48)}", 1)
    content = content.replace("FERNET_KEY=", f"FERNET_KEY={Fernet.generate_key().decode()}", 1)
    env_file.write_text(content, encoding="utf-8")
    print(f"{env_file} créé avec des secrets générés.")


if __name__ == "__main__":
    main()
