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
