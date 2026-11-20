# QuoteGen

QuoteGen is a Flask web application for creating and managing customer quotations. It supports customer and product selection, configurable company details, VAT-aware totals, discounts, user accounts, and printable quote pages.

## Features

- Create and view quotations
- Calculate discounts and VAT on the server
- Support `STANDARD`, `ZERO_RATED`, and `EXEMPT` tax categories
- Manage customers and products stored in SQL Server
- First-run administrator setup
- Admin user management, account activation, and password resets
- Company settings, default quote terms, currency, VAT rate, and logo upload
- CSRF protection, password hashing, login lockout, and secure session cookies
- Responsive light/dark styling and print-friendly quote pages

## Project structure

```text
QuoteGen/
├── app.py              # Flask routes, authentication, forms, and views
├── calc.py             # Quote validation and monetary calculations
├── config.py           # Environment-based application configuration
├── db.py               # SQL Server connection and transaction helpers
├── repository.py       # Database queries and persistence operations
├── requirements.txt    # Python dependencies
├── static/             # CSS and uploaded logo files
├── templates/          # Jinja2 HTML templates
└── tests/              # Pytest tests
```

## Requirements

- Python 3.10 or newer
- Microsoft SQL Server
- An installed SQL Server ODBC driver (the default is `ODBC Driver 17 for SQL Server`)
- A database containing the tables used by the application, including:
  `users`, `customers`, `products`, `quotes`, `quote_items`, and
  `company_settings`

The application uses `pyodbc` in `db.py`. Ensure it is installed in the environment even though the current `requirements.txt` does not list it.

## Installation

From the project directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyodbc
```

If PowerShell prevents script activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Configuration

Set these environment variables before starting the application:

| Variable | Default | Description |
| --- | --- | --- |
| `SECRET_KEY` | `change-this-in-production` | Flask session and CSRF signing key |
| `SQL_DRIVER` | `ODBC Driver 17 for SQL Server` | Installed SQL Server ODBC driver |
| `SQL_SERVER` | `localhost` | SQL Server host |
| `SQL_DATABASE` | `quotation` | Database name |
| `SQL_USER` | empty | SQL login; leave empty for Windows authentication |
| `SQL_PASSWORD` | empty | SQL login password |

For production, always set a strong `SECRET_KEY` and use a properly configured database certificate instead of relying on local-development settings.

Example using Windows authentication:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-value"
$env:SQL_SERVER = "localhost"
$env:SQL_DATABASE = "quotation"
$env:SQL_DRIVER = "ODBC Driver 17 for SQL Server"
```

## Running the application

Start the development server with:

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). On the first run, open `/setup` to create the initial administrator account.

The application expects the `company_settings` table to already contain the row with `id = 1`.

## Testing

Run the test suite with:

```powershell
pytest
```

The current tests cover quote calculation, VAT categories, discounts, and invalid input handling.

## Quote calculation rules

1. Each line is rounded to two decimal places.
2. The discount is applied before VAT.
3. VAT is charged only on `STANDARD` lines.
4. `ZERO_RATED` and `EXEMPT` lines carry no VAT.
5. Quote totals are calculated on the server; browser-submitted totals are not trusted.
