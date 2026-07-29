from django.db import models

from apps.core.models import TimeStampedModel


class DietPlan(TimeStampedModel):
    patient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="diet_plans")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    is_active = models.BooleanField(default=True)
    hydration_recommendation_ml = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class DietPlanMeal(TimeStampedModel):
    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH = "lunch", "Lunch"
        DINNER = "dinner", "Dinner"
        SNACK = "snack", "Snack"

    diet_plan = models.ForeignKey(DietPlan, on_delete=models.CASCADE, related_name="meals")
    meal_type = models.CharField(max_length=20, choices=MealType.choices)
    description = models.TextField()


class FoodAvoidanceItem(TimeStampedModel):
    diet_plan = models.ForeignKey(DietPlan, on_delete=models.CASCADE, related_name="foods_to_avoid")
    food_name = models.CharField(max_length=150)
    reason = models.TextField(blank=True)
