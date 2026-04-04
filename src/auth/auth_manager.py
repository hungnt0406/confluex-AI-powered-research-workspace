"""
Authentication manager using streamlit-authenticator.
Wraps credential management and provides login/logout helpers.
"""

import streamlit as st
import streamlit_authenticator as stauth
from src.db.session import get_session
from src.db.models import User


def get_credentials_from_db() -> dict:
    """Load user credentials from PostgreSQL into the format
    expected by streamlit-authenticator."""
    credentials = {"usernames": {}}
    with get_session() as session:
        users = session.query(User).all()
        for user in users:
            credentials["usernames"][user.username] = {
                "email": user.email,
                "name": user.username,
                "password": user.password_hash,
            }
    return credentials


def create_authenticator() -> stauth.Authenticate:
    """Create and return a configured Authenticate instance."""
    credentials = get_credentials_from_db()
    return stauth.Authenticate(
        credentials=credentials,
        cookie_name="litreview_auth",
        cookie_key="litreview_secret_key_change_in_prod",
        cookie_expiry_days=7,
    )


def ensure_admin_exists():
    """Create a default admin user if no users exist in the database."""
    with get_session() as session:
        user_count = session.query(User).count()
        if user_count == 0:
            hashed_pw = stauth.Hasher(["admin123"]).generate()[0]
            admin = User(
                username="admin",
                email="admin@litreview.local",
                password_hash=hashed_pw,
                role="admin",
            )
            session.add(admin)
            session.commit()


def require_auth() -> dict | None:
    """Run the login flow. Returns user info dict if authenticated, None otherwise.

    Usage in Streamlit pages:
        user = require_auth()
        if user is None:
            st.stop()
        # ... rest of page
    """
    authenticator = create_authenticator()
    name, authentication_status, username = authenticator.login(
        location="main",
        fields={
            "Form name": "Login",
            "Username": "Username",
            "Password": "Password",
            "Login": "Sign In",
        },
    )

    if authentication_status is False:
        st.error("Username or password is incorrect.")
        return None
    elif authentication_status is None:
        st.info("Please enter your username and password.")
        return None
    else:
        # Authenticated — store authenticator in session for logout
        st.session_state["authenticator"] = authenticator
        st.session_state["username"] = username

        # Fetch full user record
        with get_session() as session:
            user = session.query(User).filter_by(username=username).first()
            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                }
        return None


def logout():
    """Logout the current user."""
    authenticator = st.session_state.get("authenticator")
    if authenticator:
        authenticator.logout("Logout", "sidebar")
