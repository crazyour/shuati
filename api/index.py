"""Vercel entrypoint for the Flask application."""

from webapp.server import create_app


app = create_app()
