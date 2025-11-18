"""Authentication module for admin dashboard."""

import streamlit as st

from src.lib.config import load_config


def check_password() -> bool:
    """Returns True if user entered correct password.

    Handles password verification and session state management for authentication.
    """

    def password_entered() -> None:
        """Check if entered password is correct."""
        config = load_config()
        if st.session_state["password"] == config.admin_dashboard_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    # First run or not logged in
    if "password_correct" not in st.session_state:
        _render_login_form(password_entered)
        return False

    # Password incorrect
    if not st.session_state["password_correct"]:
        _render_login_form(password_entered, show_error=True)
        return False

    # Password correct
    return True


def _render_login_form(callback: callable, show_error: bool = False) -> None:
    """Render the login form UI.

    Args:
        callback: Function to call when password is entered
        show_error: Whether to show error message
    """
    st.title("🔒 Admin Dashboard Login")
    st.text_input("Password", type="password", on_change=callback, key="password")
    st.info("Enter the admin dashboard password from your .env configuration")

    if show_error:
        st.error("😕 Password incorrect")
