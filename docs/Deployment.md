# Deployment

## Current state: none

LucidPM runs locally only, on Mark's dev machine, against a local SQL Server Express instance. There is no staging or production deployment, no CI/CD pipeline, and no Docker/infrastructure-as-code in this repo.

## Forward-looking plan

Moving LucidPM (and its sibling app, Portfolio Manager) to Azure is planned but not started. The full plan — hosting target, Azure SQL migration, managed identity, Blob Storage for documents, Key Vault for secrets, and the architect gap analysis against the app's current local-Windows-authentication/local-disk assumptions — lives in `Undelivered Handoffs/Azure Planning`.

As of the 2026-08-16 foundation session: Azure CLI is installed locally; no Azure subscription exists yet. Next step is Mark creating one in the Azure portal, then resuming at the plan's POC-A step (`az login`, create the resource group).

## Known blockers for cloud hosting

The current app makes several assumptions that don't hold in a typical cloud host and will need to be addressed before deployment is realistic:

- Windows trusted authentication to a local named SQL Server instance (`Trusted_Connection=yes` to `localhost\SQLEXPRESS`)
- Local disk paths for document storage (`C:\Dell Inspirion\TenantCRM\LeaseDocuments\...`, hardcoded)
- An interactive Windows file-picker endpoint (`/api/pick-files`)

None of these are addressed by this foundation session — see `Undelivered Handoffs/Azure Planning` for the plan to resolve them.
