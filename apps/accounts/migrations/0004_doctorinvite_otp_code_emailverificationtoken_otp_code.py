from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_passwordresetotp"),
    ]

    operations = [
        migrations.RenameField(
            model_name="doctorinvite",
            old_name="token",
            new_name="otp_code",
        ),
        migrations.AlterField(
            model_name="doctorinvite",
            name="otp_code",
            field=models.CharField(max_length=6),
        ),
        migrations.RenameField(
            model_name="emailverificationtoken",
            old_name="token",
            new_name="otp_code",
        ),
        migrations.AlterField(
            model_name="emailverificationtoken",
            name="otp_code",
            field=models.CharField(max_length=6),
        ),
    ]
