from rest_framework import serializers

from apps.accounts.serializers import BriefUserSerializer
from apps.core.serializers import PatientOwnedModelSerializer
from apps.diet import services
from apps.diet.models import DietPlan, DietPlanMeal, FoodAvoidanceItem


class DietPlanMealSerializer(serializers.ModelSerializer):
    class Meta:
        model = DietPlanMeal
        fields = ["id", "meal_type", "description"]


class FoodAvoidanceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodAvoidanceItem
        fields = ["id", "food_name", "reason"]


class DietPlanSerializer(PatientOwnedModelSerializer):
    created_by = BriefUserSerializer(read_only=True)
    meals = DietPlanMealSerializer(many=True, required=False)
    foods_to_avoid = FoodAvoidanceItemSerializer(many=True, required=False)

    class Meta:
        model = DietPlan
        fields = [
            "id",
            "patient",
            "patient_id",
            "created_by",
            "is_active",
            "hydration_recommendation_ml",
            "notes",
            "meals",
            "foods_to_avoid",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_active", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        meals = validated_data.pop("meals", [])
        foods_to_avoid = validated_data.pop("foods_to_avoid", [])
        return services.create_diet_plan(meals=meals, foods_to_avoid=foods_to_avoid, **validated_data)

    def update(self, instance, validated_data):
        meals = validated_data.pop("meals", None)
        foods_to_avoid = validated_data.pop("foods_to_avoid", None)
        validated_data.pop("patient", None)  # cannot reassign an existing plan to a different patient
        return services.update_diet_plan(
            plan=instance, meals=meals, foods_to_avoid=foods_to_avoid, **validated_data
        )
