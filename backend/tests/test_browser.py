from app.services import browser


class FakeCandidate:
    def __init__(self, page, stage, visible=True):
        self.page = page
        self.stage = stage
        self.visible = visible

    async def is_visible(self):
        return self.visible

    async def click(self, timeout=0):
        self.page.clicked_stages.append(self.stage)
        if self.stage == "auth_trigger":
            self.page.checkpoint = "dialog"
        elif self.stage == "account_trigger":
            self.page.checkpoint = "provider_cluster"


class FakeLocator:
    def __init__(self, page, stage, count=1, visible=True):
        self.page = page
        self.stage = stage
        self._count = count
        self.visible = visible

    async def count(self):
        return self._count

    def nth(self, index):
        return FakeCandidate(self.page, self.stage, self.visible)


class FakePage:
    def __init__(self):
        self.checkpoint = None
        self.clicked_stages = []

    async def wait_for_load_state(self, state, timeout=0):
        return None


def test_attempt_auth_reveal_stops_after_auth_trigger(monkeypatch):
    page = FakePage()
    snapshots = []

    monkeypatch.setattr(browser, "_auth_reveal_locators", lambda page: [FakeLocator(page, "auth_trigger")])
    monkeypatch.setattr(browser, "_account_reveal_locators", lambda page: [FakeLocator(page, "account_trigger")])
    monkeypatch.setattr(browser, "_page_auth_checkpoint", lambda page: _async_return(page.checkpoint))
    monkeypatch.setattr(browser, "_advance_identity_step", lambda page, snapshots: _async_return(False))
    monkeypatch.setattr(browser, "_record_snapshot", lambda page, snapshots, stage, interaction_used, typing_used: _async_return(None))

    interaction_used, typing_used = __import__("asyncio").run(browser._attempt_auth_reveal(page, 5000, snapshots))

    assert interaction_used is True
    assert typing_used is False
    assert page.clicked_stages == ["auth_trigger"]


def test_attempt_auth_reveal_uses_account_trigger_after_auth_trigger_misses(monkeypatch):
    page = FakePage()
    snapshots = []

    monkeypatch.setattr(browser, "_auth_reveal_locators", lambda page: [FakeLocator(page, "auth_trigger", count=0)])
    monkeypatch.setattr(browser, "_account_reveal_locators", lambda page: [FakeLocator(page, "account_trigger")])
    monkeypatch.setattr(browser, "_page_auth_checkpoint", lambda page: _async_return(page.checkpoint))
    monkeypatch.setattr(browser, "_advance_identity_step", lambda page, snapshots: _async_return(False))
    monkeypatch.setattr(browser, "_record_snapshot", lambda page, snapshots, stage, interaction_used, typing_used: _async_return(None))

    interaction_used, typing_used = __import__("asyncio").run(browser._attempt_auth_reveal(page, 5000, snapshots))

    assert interaction_used is True
    assert typing_used is False
    assert page.clicked_stages == ["account_trigger"]


def test_attempt_auth_reveal_uses_identity_step_when_clicks_do_not_reveal(monkeypatch):
    page = FakePage()
    snapshots = []

    async def fake_advance_identity_step(page, snapshots):
        page.checkpoint = "email_first"
        return True

    monkeypatch.setattr(browser, "_auth_reveal_locators", lambda page: [FakeLocator(page, "auth_trigger", count=0)])
    monkeypatch.setattr(browser, "_account_reveal_locators", lambda page: [FakeLocator(page, "account_trigger", count=0)])
    monkeypatch.setattr(browser, "_page_auth_checkpoint", lambda page: _async_return(page.checkpoint))
    monkeypatch.setattr(browser, "_advance_identity_step", fake_advance_identity_step)
    monkeypatch.setattr(browser, "_record_snapshot", lambda page, snapshots, stage, interaction_used, typing_used: _async_return(None))

    interaction_used, typing_used = __import__("asyncio").run(browser._attempt_auth_reveal(page, 5000, snapshots))

    assert interaction_used is True
    assert typing_used is True
    assert page.checkpoint == "email_first"


async def _async_return(value):
    return value
