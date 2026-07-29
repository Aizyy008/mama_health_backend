from django.db import transaction

from apps.diet.models import DietPlan, DietPlanMeal, FoodAvoidanceItem


@transaction.atomic
def create_diet_plan(*, patient, created_by, meals=None, foods_to_avoid=None, **fields):
    """Deactivates (not deletes) any previously active plan — only one
    active plan per patient at a time, full history preserved."""
    DietPlan.objects.filter(patient=patient, is_active=True).update(is_active=False)
    plan = DietPlan.objects.create(patient=patient, created_by=created_by, is_active=True, **fields)
    DietPlanMeal.objects.bulk_create(
        [DietPlanMeal(diet_plan=plan, **meal) for meal in (meals or [])]
    )
    FoodAvoidanceItem.objects.bulk_create(
        [FoodAvoidanceItem(diet_plan=plan, **food) for food in (foods_to_avoid or [])]
    )
    _notify_diet_updated(plan)
    return plan


@transaction.atomic
def update_diet_plan(*, plan, meals=None, foods_to_avoid=None, **fields):
    for field, value in fields.items():
        setattr(plan, field, value)
    plan.save()

    if meals is not None:
        plan.meals.all().delete()
        DietPlanMeal.objects.bulk_create([DietPlanMeal(diet_plan=plan, **meal) for meal in meals])
    if foods_to_avoid is not None:
        plan.foods_to_avoid.all().delete()
        FoodAvoidanceItem.objects.bulk_create(
            [FoodAvoidanceItem(diet_plan=plan, **food) for food in foods_to_avoid]
        )
    _notify_diet_updated(plan)
    return plan


def _notify_diet_updated(plan: DietPlan):
    from apps.notifications import services as notification_services

    notification_services.notify(
        recipient=plan.patient,
        notification_type="diet",
        title="Your diet plan was updated",
        body="Your doctor has updated your diet plan. Open the app to see the latest recommendations.",
        data={"diet_plan_id": plan.id},
        channels=["push"],
    )
