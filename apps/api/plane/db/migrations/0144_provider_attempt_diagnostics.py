from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0143_assignment_plan_rationale"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimeproviderattempt",
            name="event_ref",
            field=models.CharField(blank=True, default="", editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="runtimeproviderattempt",
            name="reason_phase",
            field=models.CharField(blank=True, default="", editable=False, max_length=32),
        ),
        migrations.AddField(
            model_name="runtimeproviderattempt",
            name="reason_subreason",
            field=models.CharField(blank=True, default="", editable=False, max_length=64),
        ),
    ]
