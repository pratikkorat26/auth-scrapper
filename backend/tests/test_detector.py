from app.services.detector import choose_primary_component, detect_auth_component


def test_detector_finds_login_form_component() -> None:
    html = """
    <html>
      <body>
        <form id="login-form">
          <input type="email" name="email" />
          <input type="password" name="password" />
          <button type="submit">Sign in</button>
        </form>
      </body>
    </html>
    """

    result = detect_auth_component(html)

    assert result.found is True
    assert result.status == "found"
    assert result.components
    assert result.components[0].type == "traditional"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")


def test_detector_marks_sso_surface_as_oauth_component() -> None:
    html = """
    <section aria-label="Sign in">
      <button type="button">Continue with Google</button>
      <button type="button">Continue with Apple</button>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "partial_auth_surface"
    assert result.components
    assert result.components[0].type == "oauth"
    assert result.components[0].providers == ["Apple", "Google"]


def test_detector_marks_passwordless_surface() -> None:
    html = """
    <section>
      <button type="button">Continue with passkey</button>
      <button type="button">Email me a magic link</button>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "partial_auth_surface"
    assert result.components[0].type == "passwordless"


def test_detector_avoids_search_form_false_positive() -> None:
    html = """
    <form action="/search" class="search-form">
      <input type="text" name="q" placeholder="Search products" />
      <button type="submit">Search</button>
    </form>
    """

    result = detect_auth_component(html)

    assert result.status == "not_found"
    assert result.components == []


def test_choose_primary_component_prefers_traditional() -> None:
    html = """
    <div>
      <section aria-label="Sign in">
        <button type="button">Continue with Google</button>
      </section>
      <form>
        <input type="email" name="email" />
        <input type="password" name="password" />
        <button type="submit">Sign in</button>
      </form>
    </div>
    """

    result = detect_auth_component(html)
    primary = choose_primary_component(result.components)

    assert primary is not None
    assert primary.type == "traditional"


def test_detector_dedupes_wrapper_around_login_form() -> None:
    html = """
    <div class="login-shell">
      <div class="auth-panel">
        <form id="login-form">
          <input type="email" name="email" />
          <input type="password" name="password" />
          <button type="submit">Sign in</button>
        </form>
      </div>
    </div>
    """

    result = detect_auth_component(html)

    assert len(result.components) == 1
    assert result.components[0].type == "traditional"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")


def test_detector_dedupes_nested_dialog_around_form() -> None:
    html = """
    <div role="dialog" aria-modal="true" aria-label="Log in">
      <section class="login-content">
        <form>
          <input type="email" name="email" />
          <input type="password" name="password" />
          <button type="submit">Sign in</button>
        </form>
      </section>
    </div>
    """

    result = detect_auth_component(html)

    assert len(result.components) == 1
    assert result.components[0].type == "traditional"


def test_detector_keeps_sibling_auth_surfaces_separate() -> None:
    html = """
    <main>
      <form id="login-form">
        <input type="email" name="email" />
        <input type="password" name="password" />
        <button type="submit">Sign in</button>
      </form>
      <section aria-label="Sign in with provider">
        <button type="button">Continue with Google</button>
      </section>
    </main>
    """

    result = detect_auth_component(html)
    component_types = sorted(component.type for component in result.components)

    assert component_types == ["oauth", "traditional"]


def test_detector_dedupes_sso_wrapper_and_nested_button_cluster() -> None:
    html = """
    <section class="social-login">
      <div class="oauth-buttons">
        <button type="button">Continue with Google</button>
        <button type="button">Continue with Apple</button>
      </div>
    </section>
    """

    result = detect_auth_component(html)

    assert len(result.components) == 1
    assert result.components[0].type == "oauth"
    assert result.components[0].providers == ["Apple", "Google"]


def test_detector_marks_email_first_surface_as_multi_step() -> None:
    html = """
    <section class="auth-card">
      <input type="email" name="email" placeholder="Email" />
      <a href="/signin/password">Sign in with password</a>
      <button type="button">Continue</button>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "partial_auth_surface"
    assert result.components[0].type == "multi_step"
    assert result.snippet is not None
    assert "Sign in with password" in result.snippet


def test_detector_rejects_challenge_only_surface() -> None:
    html = """
    <section>
      <h2>Verify you are human</h2>
      <div class="captcha">captcha</div>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "blocked_or_inconclusive"
    assert result.components[0].type == "challenge"


def test_detector_prefers_form_over_broad_wrapper() -> None:
    html = """
    <section class="marketing-shell">
      <div class="copy">Welcome back</div>
      <div class="auth-card">
        <form id="login-form">
          <input type="email" name="email" />
          <input type="password" name="password" />
          <button type="submit">Login</button>
        </form>
      </div>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "found"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")


def test_detector_handles_composite_github_style_auth_page() -> None:
    html = """
    <div class="authentication-body authentication-body--with-form new-session">
      <div id="js-flash-container" class="flash-container">
        <template class="js-flash-template">
          <div class="flash flash-full">{{ message }}</div>
        </template>
      </div>
      <form action="/session" method="post">
        <input type="hidden" name="authenticity_token" value="token" />
        <label for="login_field">Username or email address</label>
        <input type="text" name="login" id="login_field" autocomplete="username" required="required" />
        <label for="password">Password</label>
        <input type="password" name="password" id="password" autocomplete="current-password" required="required" />
        <a id="forgot-password" href="/password_reset">Forgot password?</a>
        <input class="form-control" type="text" name="required_field_c700" hidden="hidden" />
        <input class="form-control" type="hidden" name="timestamp" value="1774942121483" />
        <input type="submit" value="Sign in" class="btn btn-primary btn-block js-sign-in-button" />
      </form>
      <webauthn-status class="js-webauthn-login-emu-control">
        <form hidden="hidden" class="js-conditional-webauthn-placeholder">
          <input type="hidden" name="webauthn_response" class="js-conditional-webauthn-response" />
        </form>
        <div class="js-webauthn-login-section">
          <button type="button" class="js-webauthn-confirm-button">Continue with passkey</button>
        </div>
      </webauthn-status>
      <form action="/sessions/social/google/initiate" method="get">
        <button type="submit">Continue with Google</button>
      </form>
      <form action="/sessions/social/apple/initiate" method="get">
        <button type="submit">Continue with Apple</button>
      </form>
    </div>
    """

    result = detect_auth_component(html)

    assert result.status == "found"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")
    assert "type=\"password\"" in result.snippet
    component_types = {component.type for component in result.components}
    assert {"oauth", "passwordless", "traditional"} <= component_types
    assert result.components[0].type == "traditional"


def test_detector_marks_visible_passkey_surface_as_passwordless() -> None:
    html = """
    <webauthn-status>
      <div class="js-webauthn-login-section">
        <button type="button">Continue with passkey</button>
      </div>
    </webauthn-status>
    """

    result = detect_auth_component(html)

    assert result.status == "partial_auth_surface"
    assert result.components
    assert result.components[0].type == "passwordless"


def test_detector_ignores_hidden_webauthn_placeholder_without_visible_trigger() -> None:
    html = """
    <section class="auth-shell">
      <form hidden="hidden" class="js-conditional-webauthn-placeholder">
        <input type="hidden" name="webauthn_response" />
      </form>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "not_found"
    assert result.components == []


def test_detector_ignores_flash_and_template_noise_for_primary_snippet() -> None:
    html = """
    <div class="authentication-body">
      <div class="flash-container">
        <template class="js-flash-template">
          <div class="flash flash-full">Dismiss this message</div>
        </template>
      </div>
      <form id="login-form">
        <input type="email" name="email" />
        <input type="password" name="password" />
        <button type="submit">Sign in</button>
      </form>
    </div>
    """

    result = detect_auth_component(html)

    assert result.status == "found"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")
    assert "flash flash-full" not in result.snippet


def test_detector_handles_facebook_style_login_shell() -> None:
    html = """
    <div class="fb_content clearfix">
      <div class="login_shell main_wrapper">
        <div class="global_banner message">Welcome back</div>
        <div class="login_panel">
          <form id="login_form">
            <input type="text" name="email" placeholder="Email address or phone number" />
            <input type="password" name="pass" placeholder="Password" />
            <button type="submit" name="login">Log in</button>
            <a href="/recover">Forgotten password?</a>
          </form>
          <div class="provider_row">
            <button type="button">Continue with Facebook</button>
          </div>
        </div>
      </div>
    </div>
    """

    result = detect_auth_component(html)

    assert result.status == "found"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")
    assert "type=\"password\"" in result.snippet
    assert {component.type for component in result.components} >= {"traditional", "oauth"}


def test_detector_handles_flipkart_style_login_modal_shell() -> None:
    html = """
    <div class="modal shell wrapper">
      <section class="login_card">
        <div class="intro_copy">Login</div>
        <div class="form_shell">
          <input type="text" name="credential" placeholder="Enter Email/Mobile number" />
          <button type="button">Request OTP</button>
          <a href="/account/password">Sign in with password</a>
        </div>
      </section>
    </div>
    """

    result = detect_auth_component(html)

    assert result.status == "partial_auth_surface"
    assert result.snippet is not None
    assert "Request OTP" in result.snippet
    assert result.components
    assert result.components[0].type == "multi_step"


def test_detector_prefers_visible_login_form_over_challenge_text_in_wrapper() -> None:
    html = """
    <section class="challenge wrapper">
      <div class="notice">Verify you are human</div>
      <form id="visible-login">
        <input type="email" name="email" />
        <input type="password" name="password" />
        <button type="submit">Sign in</button>
      </form>
    </section>
    """

    result = detect_auth_component(html)

    assert result.status == "found"
    assert result.snippet is not None
    assert result.snippet.startswith("<form")
