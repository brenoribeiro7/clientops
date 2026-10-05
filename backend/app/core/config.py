from __future__ import annotations

import base64
import binascii
import ipaddress
from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    DEMO = "demo"
    PRODUCTION = "production"


def _split_csv(value: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in value.split(",") if item.strip())
    if not values:
        raise ValueError("a lista não pode ser vazia")
    return values


def _validate_hmac_key(value: SecretStr) -> SecretStr:
    try:
        decoded = base64.b64decode(value.get_secret_value(), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("deve ser base64 válido") from error
    if len(decoded) != 32:
        raise ValueError("deve codificar exatamente 32 bytes")
    return value


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    APP_ENV: AppEnvironment
    DATABASE_URL: SecretStr
    CSRF_HMAC_KEY: SecretStr
    RATE_LIMIT_HMAC_KEY: SecretStr
    PUBLIC_BASE_URL: str
    TRUSTED_ORIGINS: str
    TRUSTED_HOSTS: str
    TRUSTED_PROXY_CIDRS: str
    PRIVATE_STORAGE_ROOT: str
    LOG_LEVEL: str = "INFO"
    SESSION_IDLE_SECONDS: int = 1800
    SESSION_ABSOLUTE_SECONDS: int = 43200
    SESSION_TOUCH_SECONDS: int = 60
    QUOTE_TOKEN_TTL_SECONDS: int = 2592000

    @field_validator("CSRF_HMAC_KEY", "RATE_LIMIT_HMAC_KEY")
    @classmethod
    def validate_hmac_key(cls, value: SecretStr) -> SecretStr:
        return _validate_hmac_key(value)

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("deve usar postgresql+psycopg")
        return value

    @field_validator("PRIVATE_STORAGE_ROOT")
    @classmethod
    def validate_storage_root(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("deve ser um caminho absoluto")
        return value.rstrip("/") or "/"

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("nível de log inválido")
        return normalized

    @field_validator("SESSION_IDLE_SECONDS", "SESSION_ABSOLUTE_SECONDS", "SESSION_TOUCH_SECONDS")
    @classmethod
    def validate_positive_duration(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("deve ser positivo")
        return value

    @field_validator("QUOTE_TOKEN_TTL_SECONDS")
    @classmethod
    def validate_quote_token_ttl(cls, value: int) -> int:
        if value != 2592000:
            raise ValueError("deve permanecer em 2592000 segundos nesta versão")
        return value

    @property
    def trusted_origins(self) -> tuple[str, ...]:
        return _split_csv(self.TRUSTED_ORIGINS)

    @property
    def trusted_hosts(self) -> tuple[str, ...]:
        return _split_csv(self.TRUSTED_HOSTS)

    @property
    def trusted_proxy_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        networks = tuple(
            ipaddress.ip_network(item, strict=False)
            for item in _split_csv(self.TRUSTED_PROXY_CIDRS)
        )
        forbidden = {ipaddress.ip_network("0.0.0.0/0"), ipaddress.ip_network("::/0")}
        if any(network in forbidden for network in networks):
            raise ValueError("TRUSTED_PROXY_CIDRS não pode confiar em toda a Internet")
        return networks

    @model_validator(mode="after")
    def validate_origin_policy(self) -> Self:
        parsed = urlsplit(self.PUBLIC_BASE_URL)
        if not parsed.scheme or not parsed.hostname or parsed.path not in {"", "/"}:
            raise ValueError("PUBLIC_BASE_URL deve ser uma origem sem path, query ou fragment")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError(
                "PUBLIC_BASE_URL deve ser uma origem sem credenciais, query ou fragment"
            )
        if self.APP_ENV in {AppEnvironment.PRODUCTION, AppEnvironment.DEMO}:
            if parsed.scheme != "https":
                raise ValueError("PUBLIC_BASE_URL deve usar HTTPS neste ambiente")
            if self.LOG_LEVEL == "DEBUG":
                raise ValueError("DEBUG é proibido neste ambiente")
            if self.trusted_origins != (self.PUBLIC_BASE_URL.rstrip("/"),):
                raise ValueError("TRUSTED_ORIGINS deve conter somente a origem canônica")
        for origin in self.trusted_origins:
            if "*" in origin:
                raise ValueError("origens wildcard são proibidas")
        for host in self.trusted_hosts:
            if "*" in host:
                raise ValueError("hosts wildcard são proibidos")
        _ = self.trusted_proxy_networks
        if self.SESSION_TOUCH_SECONDS > self.SESSION_IDLE_SECONDS:
            raise ValueError("SESSION_TOUCH_SECONDS não pode exceder SESSION_IDLE_SECONDS")
        return self


class MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    MIGRATION_DATABASE_URL: SecretStr

    @field_validator("MIGRATION_DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("deve usar postgresql+psycopg")
        return value
