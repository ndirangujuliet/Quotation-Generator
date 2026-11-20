/* ==========================================================================
   Quotation Generator - database schema (SQL Server)

   How to use:
   1. Open this file in SQL Server Management Studio (SSMS).
   2. Connect to your SQL Server instance.
   3. Click Execute.

   Safe to run more than once: it only creates what is missing and never
   deletes or changes existing data.
   ========================================================================== */

IF DB_ID(N'quotation') IS NULL
    CREATE DATABASE quotation;
GO

USE quotation;
GO

/* ---------- customers ---------- */
IF OBJECT_ID(N'dbo.customers', N'U') IS NULL
CREATE TABLE dbo.customers (
    id       INT IDENTITY(1,1) PRIMARY KEY,
    name     NVARCHAR(200) NOT NULL,
    kra_pin  NVARCHAR(30)  NULL,
    address  NVARCHAR(300) NULL,
    email    NVARCHAR(150) NULL,
    phone    NVARCHAR(50)  NULL
);
GO

/* ---------- products (catalogue) ---------- */
IF OBJECT_ID(N'dbo.products', N'U') IS NULL
CREATE TABLE dbo.products (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    name          NVARCHAR(200) NOT NULL,
    unit_price    DECIMAL(18,2) NOT NULL DEFAULT 0,
    tax_category  NVARCHAR(30)  NULL
);
GO

/* ---------- quotes ---------- */
IF OBJECT_ID(N'dbo.quotes', N'U') IS NULL
CREATE TABLE dbo.quotes (
    id                INT IDENTITY(1,1) PRIMARY KEY,
    quote_no          NVARCHAR(30)  NOT NULL,
    customer_id       INT NOT NULL REFERENCES dbo.customers(id),
    issue_date        DATE NOT NULL,
    valid_until       DATE NOT NULL,
    currency          NVARCHAR(10)  NOT NULL,
    vat_rate          DECIMAL(7,4)  NOT NULL,
    discount_percent  DECIMAL(7,4)  NOT NULL DEFAULT 0,
    discount_total    DECIMAL(18,2) NOT NULL DEFAULT 0,
    subtotal          DECIMAL(18,2) NOT NULL DEFAULT 0,
    total_vat         DECIMAL(18,2) NOT NULL DEFAULT 0,
    grand_total       DECIMAL(18,2) NOT NULL DEFAULT 0,
    terms             NVARCHAR(MAX) NULL
);
GO

/* ---------- quote lines ---------- */
IF OBJECT_ID(N'dbo.quote_items', N'U') IS NULL
CREATE TABLE dbo.quote_items (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    quote_id       INT NOT NULL REFERENCES dbo.quotes(id),
    description    NVARCHAR(300) NOT NULL,
    qty            DECIMAL(18,2) NOT NULL,
    unit_price     DECIMAL(18,2) NOT NULL,
    tax_category   NVARCHAR(30)  NULL,
    line_net       DECIMAL(18,2) NOT NULL DEFAULT 0,
    line_discount  DECIMAL(18,2) NOT NULL DEFAULT 0,
    line_vat       DECIMAL(18,2) NOT NULL DEFAULT 0
);
GO

/* ---------- company settings (always exactly one row, id = 1) ---------- */
IF OBJECT_ID(N'dbo.company_settings', N'U') IS NULL
CREATE TABLE dbo.company_settings (
    id                  INT PRIMARY KEY,
    name                NVARCHAR(200) NOT NULL,
    email               NVARCHAR(150) NULL,
    phone               NVARCHAR(50)  NULL,
    address             NVARCHAR(300) NULL,
    kra_pin             NVARCHAR(30)  NULL,
    vat_rate            DECIMAL(7,4)  NOT NULL,
    default_currency    NVARCHAR(10)  NOT NULL,
    default_valid_days  INT NOT NULL,
    default_terms       NVARCHAR(MAX) NULL,
    logo_file           NVARCHAR(260) NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.company_settings WHERE id = 1)
    INSERT INTO dbo.company_settings (id, name, vat_rate, default_currency, default_valid_days)
    VALUES (1, N'My Company', 16, N'KES', 30);
GO

/* ---------- users ---------- */
IF OBJECT_ID(N'dbo.users', N'U') IS NULL
CREATE TABLE dbo.users (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    username         NVARCHAR(100) NOT NULL UNIQUE,
    full_name        NVARCHAR(150) NOT NULL,
    password_hash    NVARCHAR(255) NOT NULL,
    role             NVARCHAR(30)  NOT NULL,
    is_active        BIT NOT NULL DEFAULT 1,
    failed_attempts  INT NOT NULL DEFAULT 0,
    locked_until     DATETIME2 NULL,
    last_login       DATETIME2 NULL
);
GO
