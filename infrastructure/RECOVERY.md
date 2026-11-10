# Backup and recovery runbook

The active data stores are Cloud SQL `main-postgres-sg` and Cloud Storage
`cs5224-ansera-app-objects-sg`, both in `asia-southeast1`. Terraform now
retains up to 14 scheduled Cloud SQL backups, enables seven days of
point-in-time recovery (PITR) logs, and sets Singapore as the backup location.
The object bucket retains deleted
or overwritten objects for seven days with Cloud Storage soft delete. Existing
invoice and receipt lifecycle rules still apply; an object deleted by a rule
enters the soft-delete window. These protections add backup/log/soft-deleted
storage charges. They protect against accidental deletion and corruption;
same-region copies do not establish recovery from a whole-region outage.

Enabling PITR on the existing Cloud SQL instance restarts it and closes database
connections. Apply the Terraform change during a short write pause, then wait
for the instance to return to `RUNNABLE`, a successful backup, and a recent
latest recovery time before claiming a recovery target.

## Verify and rehearse

Run from the repository root. The read-only check inspects the actual SQL
backup/PITR settings, successful backups, latest recovery time, bucket
location, and soft-delete window. Its default recovery-point threshold is five
minutes; a failure must be reported, not rounded into a pass.

```powershell
python evaluation/run_recovery.py check --output evaluation/results/recovery-check.json
```

The object drill uploads a uniquely named test object, deletes it, restores
its generation, compares SHA-256 hashes, and deletes the live test object. It
does not touch application invoices or receipts. A soft-deleted test generation
remains for the seven-day retention window.

```powershell
python evaluation/run_recovery.py objects --allow-live --output evaluation/results/recovery-objects.json
```

The SQL drill creates a uniquely named PITR clone at a point five minutes before
the drill starts, checks that it is runnable and contains the application database, times
clone readiness, then deletes only that disposable clone. It temporarily bills
for another Cloud SQL instance. It does not prove application cutover or verify
individual rows, so record the full-service RTO separately if the report
claims one.

```powershell
python evaluation/run_recovery.py sql-clone --allow-live --output evaluation/results/recovery-sql-clone.json
```

The scripts never print credentials or customer records. Review the JSON
results before using any RPO or RTO number in the report.

## Recover an object

Find the deleted generation and restore it. For an overwritten object, select
the generation that contains the wanted content. Check the restored bytes and
the application view before closing the incident.

```powershell
gcloud storage ls 'gs://cs5224-ansera-app-objects-sg/**' --soft-deleted --long --project=cs5224-ansera
gcloud storage restore 'gs://cs5224-ansera-app-objects-sg/OBJECT#GENERATION' --project=cs5224-ansera
```

## Recover SQL without overwriting the primary

Identify the latest available recovery time and create a new instance at the
chosen point. A PITR clone does not modify the source. Inspect the restored
application database and run the application smoke tests against the clone
before routing production services to it.

```powershell
gcloud sql instances get-latest-recovery-time main-postgres-sg --project=cs5224-ansera
gcloud sql instances clone main-postgres-sg RECOVERY_INSTANCE --point-in-time='YYYY-MM-DDTHH:MM:SSZ' --project=cs5224-ansera
gcloud sql databases list --instance=RECOVERY_INSTANCE --project=cs5224-ansera
```

Set `recovery_sql_connection_name` in the private `infrastructure/terraform.tfvars`
to `cs5224-ansera:asia-southeast1:RECOVERY_INSTANCE`, inspect `terraform plan`,
and apply it. Terraform then updates the Cloud SQL socket and `POSTGRES_HOST`
for configuration-service, messaging-service, processing-service, and
notification-job. Pause writes before cutover, verify login, sandbox, order and
payment reads, then resume writes. The original instance remains available for
investigation. Return the variable to `""` only after the intended primary is
verified; that change routes the services back. Do not use a backup restore
command that overwrites the live SQL instance during a drill.

The SQL clone readiness time excludes application revision rollout and smoke
checks. A full RTO is measured from incident declaration until the application
passes those checks. The five-minute timestamp is a point-in-time RPO probe if
the clone succeeds, not a guarantee for every future incident. Cloud SQL's
`get-latest-recovery-time` command is documented for unavailable/deleted
instances and briefly returned no window while the initial post-PITR backup
and log window were being established. The 9 November drill successfully
cloned a two-minute-old point; see `../evaluation/EVIDENCE.md`.
