from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0146_runtime_reconciliation_audit_fields"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="operationgatewaypublication",
            name="operation_gateway_publication_target",
        ),
    ]
