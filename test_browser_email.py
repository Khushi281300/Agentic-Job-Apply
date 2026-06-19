"""Verify browser automation and email config work."""
import asyncio
import sys


async def test_browser():
    """Test Playwright browser automation."""
    print("--- Browser Automation ---")
    try:
        from job_agent_services.automation.browser import PlaywrightBrowser
        browser = PlaywrightBrowser(headless=True)
        await browser.start()
        await browser.navigate("https://example.com")
        content = await browser.get_page_content()
        title_ok = "Example Domain" in content
        
        # Test form detection
        form_html = await browser.get_form_html()
        
        # Test screenshot
        await browser.screenshot("data/screenshots/test.png")
        
        await browser.stop()
        print(f"  Page loaded: {'PASS' if title_ok else 'FAIL'}")
        print(f"  Screenshot saved: data/screenshots/test.png")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_email_config():
    """Test email sender configuration."""
    print("\n--- Email Application ---")
    try:
        from job_agent_agents.config import Settings
        from job_agent_services.email.sender import SMTPEmailSender
        from job_agent_services.email.applicant import EmailApplicantService

        settings = Settings()
        host = settings.email_app.smtp_host
        from_email = settings.email_app.from_email
        display = settings.email_app.display_name
        password = settings.email_app.password

        print(f"  SMTP Host: {host}")
        print(f"  From: {from_email}")
        print(f"  Display Name: {display}")
        print(f"  Password set: {bool(password) and password != 'PASTE_YOUR_APP_PASSWORD_HERE'}")

        if not host:
            print("  SKIP: No SMTP host configured")
            return False

        sender = SMTPEmailSender(
            smtp_host=host,
            smtp_port=settings.email_app.smtp_port,
            username=settings.email_app.username,
            password=password,
            from_email=from_email,
            display_name=display,
            use_tls=settings.email_app.use_tls,
        )
        applicant = EmailApplicantService(
            sender=sender,
            max_per_hour=settings.email_app.max_per_hour,
            signature_html=settings.email_app.signature_html,
        )
        print(f"  EmailApplicantService: INITIALIZED")
        print(f"  send_application method: {hasattr(applicant, 'send_application')}")

        # Test SMTP connectivity (only if real password is set)
        if password and password != "PASTE_YOUR_APP_PASSWORD_HERE":
            available = await sender.is_available()
            print(f"  SMTP reachable: {'YES' if available else 'NO'}")
        else:
            print("  SMTP connectivity: SKIP (set APP PASSWORD in .env first)")

        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_apply_agent_wiring():
    """Test that ApplicationAgent correctly wires to both paths."""
    print("\n--- Apply Agent Wiring ---")
    try:
        from job_agent_agents.apply import ApplicationAgent
        import inspect
        
        source = inspect.getsource(ApplicationAgent._apply_via_email)
        has_send_application = "send_application" in source
        has_old_apply = ".apply(" in source and "send_application" not in source
        
        print(f"  Uses send_application(): {'PASS' if has_send_application else 'FAIL'}")
        if has_old_apply:
            print(f"  WARNING: Still has old .apply() call")
        
        source_browser = inspect.getsource(ApplicationAgent._apply_via_browser)
        has_playwright = "PlaywrightBrowser" in source_browser
        print(f"  Uses PlaywrightBrowser: {'PASS' if has_playwright else 'FAIL'}")
        
        return has_send_application and has_playwright
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def main():
    browser_ok = await test_browser()
    email_ok = await test_email_config()
    wiring_ok = await test_apply_agent_wiring()

    print("\n" + "=" * 40)
    print(f"Browser: {'PASS' if browser_ok else 'FAIL'}")
    print(f"Email:   {'PASS' if email_ok else 'NEEDS APP PASSWORD'}")
    print(f"Wiring:  {'PASS' if wiring_ok else 'FAIL'}")
    print("=" * 40)

    if not all([browser_ok, wiring_ok]):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
