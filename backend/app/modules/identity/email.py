from email_validator import EmailNotValidError, validate_email


class InvalidIdentityEmail(ValueError):
    pass


def normalize_identity_email(value: str) -> str:
    candidate = value.strip()
    try:
        result = validate_email(
            candidate,
            allow_smtputf8=False,
            check_deliverability=False,
        )
    except EmailNotValidError as error:
        raise InvalidIdentityEmail("e-mail inválido") from error
    ascii_email = result.ascii_email
    if ascii_email is None:
        raise InvalidIdentityEmail("e-mail inválido")
    local, separator, domain = ascii_email.rpartition("@")
    normalized = f"{local.lower()}{separator}{domain.lower()}"
    if not separator or len(normalized.encode("ascii")) > 254:
        raise InvalidIdentityEmail("e-mail inválido")
    return normalized
