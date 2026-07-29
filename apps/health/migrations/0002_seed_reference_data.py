from django.db import migrations

# Generic, commonly-used size comparisons — placeholder seed data the admin
# can edit via Django admin. Not per-patient; a single shared reference table.
BABY_SIZE_BY_WEEK = {
    4: ("a poppy seed", 0.1, 0.1),
    5: ("a sesame seed", 0.2, 0.1),
    6: ("a lentil", 0.5, 0.2),
    7: ("a blueberry", 1.3, 1.0),
    8: ("a raspberry", 1.6, 1.0),
    9: ("a grape", 2.3, 2.0),
    10: ("a kumquat", 3.1, 4.0),
    11: ("a fig", 4.1, 7.0),
    12: ("a lime", 5.4, 14.0),
    13: ("a lemon", 7.4, 23.0),
    14: ("a peach", 8.7, 43.0),
    15: ("an apple", 10.1, 70.0),
    16: ("an avocado", 11.6, 100.0),
    17: ("a pear", 13.0, 140.0),
    18: ("a bell pepper", 14.2, 190.0),
    19: ("a tomato", 15.3, 240.0),
    20: ("a banana", 25.6, 300.0),
    21: ("a carrot", 26.7, 360.0),
    22: ("a papaya", 27.8, 430.0),
    23: ("a large mango", 28.9, 500.0),
    24: ("an ear of corn", 30.0, 600.0),
    25: ("a cauliflower head", 34.6, 660.0),
    26: ("a lettuce head", 35.6, 760.0),
    27: ("a cucumber", 36.6, 875.0),
    28: ("an eggplant", 37.6, 1005.0),
    29: ("a butternut squash", 38.6, 1150.0),
    30: ("a large cabbage", 39.9, 1319.0),
    31: ("a coconut", 41.1, 1502.0),
    32: ("a jicama", 42.4, 1702.0),
    33: ("a pineapple", 43.7, 1918.0),
    34: ("a cantaloupe", 45.0, 2146.0),
    35: ("a honeydew melon", 46.2, 2383.0),
    36: ("a head of romaine lettuce", 47.4, 2622.0),
    37: ("a bunch of Swiss chard", 48.6, 2859.0),
    38: ("a leek", 49.8, 3083.0),
    39: ("a mini watermelon", 50.7, 3288.0),
    40: ("a small pumpkin", 51.2, 3462.0),
    41: ("a jackfruit", 51.7, 3597.0),
    42: ("a large watermelon", 51.5, 3685.0),
}

COMMON_SYMPTOMS = [
    "Nausea",
    "Vomiting",
    "Fatigue",
    "Headache",
    "Back pain",
    "Swelling (feet/ankles)",
    "Heartburn",
    "Constipation",
    "Dizziness",
    "Shortness of breath",
    "Leg cramps",
    "Insomnia",
    "Mood swings",
    "Frequent urination",
    "Braxton Hicks contractions",
]


def seed_reference_data(apps, schema_editor):
    BabySizeReference = apps.get_model("health", "BabySizeReference")
    SymptomType = apps.get_model("health", "SymptomType")

    BabySizeReference.objects.bulk_create(
        [
            BabySizeReference(week=week, size_comparison=comparison, length_cm=length_cm, weight_grams=weight_g)
            for week, (comparison, length_cm, weight_g) in BABY_SIZE_BY_WEEK.items()
        ],
        ignore_conflicts=True,
    )
    SymptomType.objects.bulk_create(
        [SymptomType(name=name) for name in COMMON_SYMPTOMS], ignore_conflicts=True
    )


def remove_reference_data(apps, schema_editor):
    BabySizeReference = apps.get_model("health", "BabySizeReference")
    SymptomType = apps.get_model("health", "SymptomType")
    BabySizeReference.objects.filter(week__in=BABY_SIZE_BY_WEEK.keys()).delete()
    SymptomType.objects.filter(name__in=COMMON_SYMPTOMS).delete()


class Migration(migrations.Migration):
    dependencies = [("health", "0001_initial")]

    operations = [migrations.RunPython(seed_reference_data, remove_reference_data)]
