from app.ai.redaction import redact_secrets


def test_literal_password_is_redacted_and_restorable():
    source = 'DB_PASSWORD = "hunter2-secret"\nprint(DB_PASSWORD)\n'
    result = redact_secrets(source)
    assert "hunter2-secret" not in result.text
    assert 'DB_PASSWORD = "<REDACTED_1>"' in result.text
    assert result.count == 1
    assert result.restore(result.text) == source


def test_json_style_and_comparison_secrets():
    source = '{"api_key": "abcd1234efgh"}\nif password == "letmein1":\n    pass\n'
    result = redact_secrets(source)
    assert "abcd1234efgh" not in result.text and "letmein1" not in result.text
    assert result.count == 2
    assert result.restore(result.text) == source


def test_known_token_formats():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdefghijk"
    source = f'a = "AKIAIOSFODNN7EXAMPLE"\nb = "ghp_{"x" * 36}"\ntoken = "{jwt}"\n'
    result = redact_secrets(source)
    for secret in ("AKIAIOSFODNN7EXAMPLE", "ghp_" + "x" * 36, jwt):
        assert secret not in result.text
    assert result.count == 3
    assert result.restore(result.text) == source


def test_private_key_block_keeps_line_count():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\nDEFghi\n-----END RSA PRIVATE KEY-----"
    source = f'KEY = """{pem}"""\nx = 1\n'
    result = redact_secrets(source)
    assert "MIIabc" not in result.text
    assert result.text.count("\n") == source.count("\n")
    assert result.restore(result.text) == source


def test_url_credentials_and_bearer_tokens():
    source = (
        'url = "postgresql://admin:s3cretPass@db.example.com/app"\n'
        'h = {"Authorization": "Bearer abcdefghijklmnop1234"}\n'
    )
    result = redact_secrets(source)
    assert "s3cretPass" not in result.text and "abcdefghijklmnop1234" not in result.text
    assert "postgresql://admin:<REDACTED_1>@db.example.com/app" in result.text
    assert result.restore(result.text) == source


def test_ordinary_code_is_left_alone():
    code = (
        'password = request.form["pw"]\n'
        'token = os.environ["TOKEN"]\n'
        'if user == "admin":\n    pass\n'
        'link = "https://example.com:8080/path"\n'
    )
    result = redact_secrets(code)
    assert result.text == code and result.count == 0


def test_redaction_is_idempotent_and_numbers_secrets():
    source = 'a_password = "aaaa1111"\nb_secret = "bbbb2222"\n'
    first = redact_secrets(source)
    assert "<REDACTED_1>" in first.text and "<REDACTED_2>" in first.text
    second = redact_secrets(first.text)
    assert second.count == 0 and second.text == first.text


def test_restore_ignores_unknown_placeholders():
    result = redact_secrets('pwd = "secret99"\n')
    assert result.restore("x = <REDACTED_9>") == "x = <REDACTED_9>"
