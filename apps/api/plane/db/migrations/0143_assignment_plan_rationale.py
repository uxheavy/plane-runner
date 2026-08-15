from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0142_runtime_provider_attempts"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignmentcontract",
            name="plan_rationale",
            field=models.TextField(blank=True, default=""),
        ),
    ]
