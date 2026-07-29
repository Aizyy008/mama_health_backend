from django.contrib import admin

from apps.diet.models import DietPlan, DietPlanMeal, FoodAvoidanceItem


class DietPlanMealInline(admin.TabularInline):
    model = DietPlanMeal
    extra = 0


class FoodAvoidanceItemInline(admin.TabularInline):
    model = FoodAvoidanceItem
    extra = 0


@admin.register(DietPlan)
class DietPlanAdmin(admin.ModelAdmin):
    list_display = ["patient", "created_by", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["patient__email"]
    inlines = [DietPlanMealInline, FoodAvoidanceItemInline]
