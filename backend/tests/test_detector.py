from app.services.detector import detect_auth_component


def test_detector_finds_login_form() -> None:
    html = """
    <html>
      <body>
        <form id="login-form">
          <input type="text" name="username" />
          <input type="password" name="password" />
          <button type="submit">Sign in</button>
        </form>
      </body>
    </html>
    """

    result = detect_auth_component(html)

    assert result.found is True
    assert "password_input" in result.signals
    assert "submit_button" in result.signals


def test_detector_finds_password_only_candidate() -> None:
    html = """
    <div class="auth-panel">
      <div>
        <label>Password</label>
        <input type="password" />
      </div>
    </div>
    """

    result = detect_auth_component(html)

    assert result.found is True
    assert "password_input" in result.signals


def test_detector_returns_not_found_when_no_auth_component_exists() -> None:
    html = """
    <html>
      <body>
        <section>
          <h1>Welcome</h1>
          <p>This page has no login form.</p>
        </section>
      </body>
    </html>
    """

    result = detect_auth_component(html)

    assert result.found is False
    assert result.snippet is None

