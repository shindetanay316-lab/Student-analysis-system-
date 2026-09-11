"""Safely change an existing application user's password."""

import argparse
import getpass

from app import app
from models import User, db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Existing username, for example: admin")
    args = parser.parse_args()

    password = getpass.getpass("New password (minimum 8 characters): ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")

    with app.app_context():
        user = User.query.filter_by(username=args.username).first()
        if user is None:
            raise SystemExit(f"User '{args.username}' does not exist. Run seed.py first.")
        user.set_password(password)
        db.session.commit()
        print(f"Password updated for '{args.username}'.")


if __name__ == "__main__":
    main()
