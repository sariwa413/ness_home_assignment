"""Credential-based sign-in form."""

from __future__ import annotations

from src.pages.base_page import BasePage


class LoginPage(BasePage):
    USERNAME_INPUT = "#userid"
    CONTINUE_BUTTON = "#signin-continue-btn"
    PASSWORD_INPUT = "#pass"
    SUBMIT_BUTTON = "#sgnBt"

    def open(self) -> "LoginPage":
        self.goto(f"{self.config.base_url}/signin/")
        return self

    def sign_in(self, username: str, password: str) -> None:
        self.page.fill(self.USERNAME_INPUT, username)
        self.click(self.page.locator(self.CONTINUE_BUTTON))
        self.page.fill(self.PASSWORD_INPUT, password)
        self.click(self.page.locator(self.SUBMIT_BUTTON))
        self.page.wait_for_load_state("domcontentloaded")
