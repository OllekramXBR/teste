"""Tests for accounts and sessions.

Two things matter here beyond the happy path. First, that enforcement is off
until it is switched on, because turning a login on by surprise would lock the
owner out of a library that has never had one. Second, the details that make a
password store worth having: a per-user salt, a constant-time comparison, and a
wrong password that is indistinguishable from an unknown user.
"""

from __future__ import annotations

import pytest

from app import auth, storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATABASE_PATH", tmp_path / "test.db")
    storage.init_db()
    auth.init()
    return tmp_path


class TestPasswords:
    def test_a_password_verifies_against_its_own_hash(self):
        stored = auth.hash_password("uma senha longa")
        assert auth.verify_password("uma senha longa", stored) is True

    def test_a_wrong_password_does_not(self):
        stored = auth.hash_password("uma senha longa")
        assert auth.verify_password("outra senha longa", stored) is False

    def test_the_same_password_hashes_differently_every_time(self):
        # A shared salt would let one rainbow table cover every account, and
        # would show at a glance which users picked the same password.
        assert auth.hash_password("mesma senha") != auth.hash_password("mesma senha")

    def test_the_plain_password_is_nowhere_in_the_hash(self):
        assert "segredo123" not in auth.hash_password("segredo123")

    def test_the_work_factor_travels_with_the_hash(self):
        # So it can be raised later without invalidating what is already stored.
        assert str(auth.ITERATIONS) in auth.hash_password("qualquer senha")

    @pytest.mark.parametrize("junk", ["", "not-a-hash", "pbkdf2_sha256$abc", "md5$1$aa$bb"])
    def test_a_malformed_stored_hash_fails_closed(self, junk):
        assert auth.verify_password("qualquer coisa", junk) is False


class TestAccounts:
    def test_a_user_can_be_created_and_signed_in(self, db):
        auth.create_user("marcelo", "senha muito boa")
        assert auth.authenticate("marcelo", "senha muito boa")["username"] == "marcelo"

    def test_the_username_is_case_insensitive(self, db):
        auth.create_user("Marcelo", "senha muito boa")
        assert auth.authenticate("marcelo", "senha muito boa")["id"]

    def test_a_duplicate_username_is_refused(self, db):
        auth.create_user("marcelo", "senha muito boa")
        with pytest.raises(auth.AuthError):
            auth.create_user("MARCELO", "outra senha boa")

    def test_a_wrong_password_is_refused(self, db):
        auth.create_user("marcelo", "senha muito boa")
        with pytest.raises(auth.AuthError):
            auth.authenticate("marcelo", "senha errada")

    def test_an_unknown_user_gives_the_same_answer_as_a_wrong_password(self, db):
        # Different messages would let someone enumerate which accounts exist.
        auth.create_user("marcelo", "senha muito boa")
        with pytest.raises(auth.AuthError) as unknown:
            auth.authenticate("ninguem", "senha muito boa")
        with pytest.raises(auth.AuthError) as wrong:
            auth.authenticate("marcelo", "senha errada")
        assert str(unknown.value) == str(wrong.value)

    def test_short_passwords_are_refused(self, db):
        with pytest.raises(auth.AuthError):
            auth.create_user("marcelo", "curta")

    def test_short_usernames_are_refused(self, db):
        with pytest.raises(auth.AuthError):
            auth.create_user("ab", "senha muito boa")


class TestSessions:
    def test_a_session_identifies_its_user(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        token = auth.start_session(user["id"])
        assert auth.user_for_token(token)["username"] == "marcelo"

    def test_two_sessions_are_never_the_same_token(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        assert auth.start_session(user["id"]) != auth.start_session(user["id"])

    def test_signing_out_revokes_that_session(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        token = auth.start_session(user["id"])
        auth.end_session(token)
        assert auth.user_for_token(token) is None

    def test_signing_out_leaves_other_sessions_alone(self, db):
        # The tablet on stage should not be signed out because a laptop was.
        user = auth.create_user("marcelo", "senha muito boa")
        stage, laptop = auth.start_session(user["id"]), auth.start_session(user["id"])
        auth.end_session(laptop)
        assert auth.user_for_token(stage) is not None

    def test_an_unknown_token_is_nobody(self, db):
        assert auth.user_for_token("made-up") is None

    def test_no_token_is_nobody(self, db):
        assert auth.user_for_token(None) is None

    def test_an_expired_session_stops_working(self, db, monkeypatch):
        user = auth.create_user("marcelo", "senha muito boa")
        monkeypatch.setattr(auth, "SESSION_DAYS", -1)
        assert auth.user_for_token(auth.start_session(user["id"])) is None


class TestEnforcement:
    def test_it_is_off_unless_explicitly_required(self, monkeypatch):
        # The default has to stay open: this app has run without a login behind
        # a private network, and enabling one by surprise locks its owner out.
        monkeypatch.setattr(auth, "AUTH_MODE", "open")
        assert auth.enabled() is False

    def test_it_turns_on_when_asked(self, monkeypatch):
        monkeypatch.setattr(auth, "AUTH_MODE", "required")
        assert auth.enabled() is True

    def test_an_unrecognised_value_does_not_lock_anyone_out(self, monkeypatch):
        monkeypatch.setattr(auth, "AUTH_MODE", "yes-please")
        assert auth.enabled() is False


class TestProfile:
    def test_the_display_name_can_be_set(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        assert auth.set_display_name(user["id"], "Marcelo Rocha")["displayName"] == "Marcelo Rocha"

    def test_a_password_change_needs_the_old_one(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        with pytest.raises(auth.AuthError):
            auth.change_password(user["id"], "senha errada", "senha nova boa")

    def test_after_changing_only_the_new_password_works(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        auth.change_password(user["id"], "senha muito boa", "senha nova boa")
        assert auth.authenticate("marcelo", "senha nova boa")["id"] == user["id"]
        with pytest.raises(auth.AuthError):
            auth.authenticate("marcelo", "senha muito boa")

    def test_changing_the_password_drops_every_session(self, db):
        # If the change was made because somebody else got in, leaving their
        # session alive would defeat the point of changing it.
        user = auth.create_user("marcelo", "senha muito boa")
        tablet = auth.start_session(user["id"])
        laptop = auth.start_session(user["id"])
        auth.change_password(user["id"], "senha muito boa", "senha nova boa")
        assert auth.user_for_token(tablet) is None
        assert auth.user_for_token(laptop) is None

    def test_a_short_replacement_is_refused_before_anything_changes(self, db):
        user = auth.create_user("marcelo", "senha muito boa")
        with pytest.raises(auth.AuthError):
            auth.change_password(user["id"], "senha muito boa", "curta")
        assert auth.authenticate("marcelo", "senha muito boa")["id"] == user["id"]

    def test_listing_users_never_exposes_a_hash(self, db):
        auth.create_user("marcelo", "senha muito boa")
        listed = auth.list_users()
        assert set(listed[0]) == {"id", "username", "displayName"}


class TestWhatIsReachableWhenClosed:
    """The exact list of doors left open when accounts are enforced.

    Registration has to stay open or enabling this before anybody has an account
    locks the owner out of their own library — and that is a state with no way
    back that does not involve editing the server's environment by hand.
    """

    def test_registration_stays_open_so_the_first_account_can_exist(self):
        from app.main import PUBLIC_PREFIXES

        assert any("/api/auth/register".startswith(prefix) for prefix in PUBLIC_PREFIXES)

    def test_signing_in_stays_open(self):
        from app.main import PUBLIC_PREFIXES

        assert any("/api/auth/login".startswith(prefix) for prefix in PUBLIC_PREFIXES)

    def test_health_stays_open_for_the_container_check(self):
        from app.main import PUBLIC_PATHS

        assert "/api/health" in PUBLIC_PATHS

    @pytest.mark.parametrize(
        "path",
        ["/api/songs", "/api/setlists", "/api/library/search", "/api/songs/abc/audio"],
    )
    def test_everything_that_holds_music_is_closed(self, path):
        from app.main import PUBLIC_PATHS, PUBLIC_PREFIXES

        assert path not in PUBLIC_PATHS
        assert not any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)

    @pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/redoc"])
    def test_the_api_documentation_is_closed_too(self, path):
        # It is not under /api/, so a prefix check misses it — and it describes
        # every endpoint this server has, which is a map of the building.
        from app.main import PRIVATE_WHEN_CLOSED

        assert path.startswith(PRIVATE_WHEN_CLOSED)
