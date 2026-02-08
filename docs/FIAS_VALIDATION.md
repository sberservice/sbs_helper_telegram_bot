# FIAS Address Validation

## Overview

The **FIAS check** (`fias_check`) is a validation rule type that verifies whether
an address extracted from a ticket text exists in the
[ФИАС](https://fias.nalog.ru/) (Федеральная информационная адресная система)
database.

The check uses a **provider pattern** so the underlying API can be swapped
without touching the validation logic.  The default (and currently only built-in)
provider is [DaData](https://dadata.ru/api/suggest/address/).

---

## Quick Start

### 1. Get a DaData API key

1. Register at <https://dadata.ru/>.
2. Confirm your email.
3. Copy your API key from <https://dadata.ru/profile/>.

### 2. Set the environment variable

Add to your `.env` (or host environment):

```dotenv
DADATA_API_KEY=your_dadata_api_key_here
```

### 3. Create a validation rule (via admin panel or SQL)

| Field           | Value |
|-----------------|-------|
| **rule_name**   | `Проверка адреса ФИАС` |
| **rule_type**   | `fias_check` |
| **pattern**     | `Адрес установки POS-терминала:\s*([\s\S]*?)(?=Тип пакета:\|$)` |
| **error_message** | `Адрес установки POS-терминала не найден в базе ФИАС` |
| **priority**    | `50` |

> The **pattern** is a regular expression.  The **first capture group** `(…)`
> must contain the address to validate.  Everything else in the regex is
> context used to locate the address inside the ticket text.

SQL example:

```sql
INSERT INTO ticket_validator_validation_rules
  (rule_name, pattern, rule_type, error_message, priority, active, created_timestamp)
VALUES
  (
    'Проверка адреса ФИАС',
    'Адрес установки POS-терминала:\\s*([\\s\\S]*?)(?=Тип пакета:|$)',
    'fias_check',
    'Адрес установки POS-терминала не найден в базе ФИАС',
    50,
    1,
    UNIX_TIMESTAMP()
  );
```

Then associate it with the appropriate ticket type(s) via the admin panel
or the `ticket_validator_ticket_type_rules` table.

### 4. Test it

Send a ticket containing a valid address and then one with a bogus address to
your bot.  The FIAS check should pass / fail accordingly.

---

## How It Works

```
Ticket text
   │
   ▼
┌──────────────────────┐
│  Regex extraction    │  ← pattern's 1st capture group
│  (address string)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  FIAS Provider       │  ← DaData by default
│  validate_address()  │
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     │ suggestions│
     │  empty?    │
     └─────┬─────┘
       Yes │  No
       ▼       ▼
     FAIL    PASS
```

1. The `fias_check` rule type calls `validate_fias_address()` in
   [validators.py](../src/sbs_helper_telegram_bot/ticket_validator/validators.py).
2. The function extracts the address from the ticket using the regex pattern.
3. The extracted address is sent to the active FIAS provider's
   `validate_address()` method.
4. If the provider returns **at least one suggestion**, the rule passes.
5. If the suggestions list is **empty**, the rule fails.

### Fail-Open Policy

If the API is unreachable, the key is invalid, or the daily quota is exceeded,
the provider returns `is_valid=True` (fail-open) so that external service
problems don't block every ticket.  The `error_message` field will describe
what happened, and a warning is logged.

---

## Architecture — Provider Pattern

```
                    ┌───────────────────┐
                    │  BaseFIASProvider  │   (abstract)
                    │  ─────────────────│
                    │  validate_address()│
                    │  is_configured()   │
                    └────────┬──────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
   ┌──────────────────┐         ┌───────────────────────┐
   │ DaDataFIASProvider│         │ YourCustomProvider     │
   │ (built-in)        │         │ (add your own)         │
   └──────────────────┘         └───────────────────────┘
```

All provider classes live in
[fias_providers.py](../src/sbs_helper_telegram_bot/ticket_validator/fias_providers.py).

### Adding a New Provider

1. Create a class that inherits from `BaseFIASProvider`.
2. Set `provider_name` to a unique string.
3. Implement `validate_address(address) → FIASValidationResult`.
4. Register it in `_PROVIDER_REGISTRY`:

```python
# fias_providers.py

class MyCustomProvider(BaseFIASProvider):
    provider_name = "my_custom"

    def validate_address(self, address: str) -> FIASValidationResult:
        # ... call your API ...
        return FIASValidationResult(is_valid=True, ...)

_PROVIDER_REGISTRY["my_custom"] = MyCustomProvider
```

5. Set the env var to use it:

```dotenv
FIAS_PROVIDER=my_custom
```

### Selecting a Provider at Runtime

```python
from .fias_providers import get_fias_provider

provider = get_fias_provider()           # auto-selects from env
provider = get_fias_provider("dadata")   # explicit
```

The factory function `get_fias_provider()` checks (in order):

1. The `provider_name` argument.
2. The `FIAS_PROVIDER` environment variable.
3. Falls back to `"dadata"`.

The returned instance is cached as a singleton.

---

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DADATA_API_KEY` | **Yes** (for DaData) | — | Your DaData API key |
| `DADATA_API_URL` | No | `https://suggestions.dadata.ru/suggestions/api/4_1/rs` | Override the base URL |
| `FIAS_PROVIDER` | No | `dadata` | Which provider to use |

### Module Settings (`settings.py`)

| Constant | Value | Description |
|----------|-------|-------------|
| `FIAS_PROVIDER` | `"dadata"` | Default provider name |
| `FIAS_DEFAULT_ADDRESS_PATTERN` | (see source) | Suggested regex for POS-terminal address |

---

## DaData API Details

* **Endpoint:** `POST https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address`
* **Auth header:** `Authorization: Token <API_KEY>`
* **Request body:**
  ```json
  { "query": "москва хабар", "count": 1 }
  ```
* **Response:**
  ```json
  {
    "suggestions": [
      {
        "value": "г Москва, ул Хабаровская, д ...",
        "data": { "fias_id": "...", "fias_level": "8", ... }
      }
    ]
  }
  ```

### Rate Limits (Free Tier)

| Limit | Value |
|-------|-------|
| Requests per day | **10 000** |
| Requests per second (per IP) | 30 |
| New connections per minute (per IP) | 60 |

### HTTP Error Codes

| Code | Meaning | Bot behaviour |
|------|---------|---------------|
| 200 | OK | Check suggestions |
| 403 | Bad key / quota exceeded | Fail-open + log error |
| 429 | Rate limit | Fail-open + log warning |
| 5xx | Server error | Fail-open + log error |

Full API docs: <https://dadata.ru/api/suggest/address/>

---

## Testing

All FIAS-related tests are in
[tests/test_ticket_validator.py](../tests/test_ticket_validator.py).
They use `unittest.mock` to mock the HTTP layer — no real API calls are made
during testing.

### Test Classes

| Class | What it tests |
|-------|---------------|
| `TestFIASValidationResult` | The data class |
| `TestDaDataFIASProvider` | DaData provider (mocked HTTP) |
| `TestGetFIASProvider` | Factory / singleton |
| `TestValidateFIASAddress` | Address extraction + validation |
| `TestFIASCheckRuleType` | Integration with `validate_ticket()` |

Run only the FIAS tests:

```bash
pytest tests/test_ticket_validator.py -k fias -v
```

---

## Files Changed / Added

| File | Change |
|------|--------|
| `src/…/ticket_validator/fias_providers.py` | **New** — Provider pattern + DaData implementation |
| `src/…/ticket_validator/validators.py` | Added `FIAS_CHECK` to `RuleType`, `validate_fias_address()`, dispatcher branch |
| `src/…/ticket_validator/settings.py` | Added `FIAS_PROVIDER`, `FIAS_DEFAULT_ADDRESS_PATTERN` |
| `src/…/ticket_validator/messages.py` | Added `fias_check` to admin rule type selection message |
| `.env.example` | Added `DADATA_API_KEY` and related vars |
| `tests/test_ticket_validator.py` | Added 24 FIAS unit tests |
| `docs/FIAS_VALIDATION.md` | **New** — This document |
